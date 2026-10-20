"""Integrity: unordered friendships, unique meeting/participant keys

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-20 23:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _index_names(table):
    bind = op.get_bind()
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(table) if idx.get("name")}


def _table_names():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _dedupe_reverse_friendships(conn):
    rows = conn.execute(text(
        "SELECT id, requester_id, addressee_id, status, created_at FROM friendships"
    )).fetchall()
    by_pair = {}
    drop_ids = []
    for row in rows:
        fid, a, b, status, created = row
        key = (min(a, b), max(a, b))
        if key not in by_pair:
            by_pair[key] = row
            continue
        prev = by_pair[key]
        prev_score = (1 if prev[3] == "accepted" else 0, prev[4] or 0)
        cur_score = (1 if status == "accepted" else 0, created or 0)
        if cur_score >= prev_score:
            drop_ids.append(prev[0])
            by_pair[key] = row
        else:
            drop_ids.append(fid)
    for did in drop_ids:
        conn.execute(text("DELETE FROM friendships WHERE id = :id"), {"id": did})


def _dedupe_meeting_requests(conn):
    dupes = conn.execute(text(
        "SELECT event_id FROM meeting_requests GROUP BY event_id HAVING COUNT(*) > 1"
    )).fetchall()
    for (event_id,) in dupes:
        ids = [
            r[0]
            for r in conn.execute(
                text("SELECT id FROM meeting_requests WHERE event_id = :eid ORDER BY id"),
                {"eid": event_id},
            ).fetchall()
        ]
        for rid in ids[1:]:
            conn.execute(text("DELETE FROM meeting_requests WHERE id = :id"), {"id": rid})


def _dedupe_participants(conn):
    dupes = conn.execute(text(
        "SELECT event_id, user_id FROM event_participants "
        "GROUP BY event_id, user_id HAVING COUNT(*) > 1"
    )).fetchall()
    for event_id, user_id in dupes:
        ids = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT id FROM event_participants "
                    "WHERE event_id = :e AND user_id = :u ORDER BY id"
                ),
                {"e": event_id, "u": user_id},
            ).fetchall()
        ]
        for pid in ids[1:]:
            conn.execute(text("DELETE FROM event_participants WHERE id = :id"), {"id": pid})


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name
    tables = _table_names()

    if "friendships" in tables:
        _dedupe_reverse_friendships(conn)
        if "uq_friendship_unordered" not in _index_names("friendships"):
            if dialect == "postgresql":
                op.execute(text(
                    "CREATE UNIQUE INDEX uq_friendship_unordered ON friendships "
                    "(LEAST(requester_id, addressee_id), GREATEST(requester_id, addressee_id))"
                ))
            else:
                op.execute(text(
                    "CREATE UNIQUE INDEX uq_friendship_unordered ON friendships "
                    "(min(requester_id, addressee_id), max(requester_id, addressee_id))"
                ))

    if "meeting_requests" in tables:
        _dedupe_meeting_requests(conn)
        if "uq_meeting_requests_event_id" not in _index_names("meeting_requests"):
            op.create_index(
                "uq_meeting_requests_event_id",
                "meeting_requests",
                ["event_id"],
                unique=True,
            )

    if "event_participants" in tables:
        _dedupe_participants(conn)
        if "uq_event_participant" not in _index_names("event_participants"):
            op.create_index(
                "uq_event_participant",
                "event_participants",
                ["event_id", "user_id"],
                unique=True,
            )

    if "users" in tables:
        cols = {c["name"] for c in sa.inspect(conn).get_columns("users")}
        if "invite_token" in cols and "ix_users_invite_token" not in _index_names("users"):
            op.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_invite_token "
                "ON users (invite_token)"
            ))


def downgrade():
    for name, table in (
        ("uq_friendship_unordered", "friendships"),
        ("uq_meeting_requests_event_id", "meeting_requests"),
        ("uq_event_participant", "event_participants"),
        ("ix_users_invite_token", "users"),
    ):
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass
