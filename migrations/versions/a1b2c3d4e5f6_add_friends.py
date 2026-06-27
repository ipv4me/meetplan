"""Add friends and invite tokens

Revision ID: a1b2c3d4e5f6
Revises: 6fd80d3e6386
Create Date: 2026-06-27 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "6fd80d3e6386"
branch_labels = None
depends_on = None


def _has_table(name):
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _has_column(table, column):
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    if _has_table("users") and not _has_column("users", "invite_token"):
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.add_column(sa.Column("invite_token", sa.String(length=32), nullable=True))
            batch_op.create_index("ix_users_invite_token", ["invite_token"], unique=True)

    if not _has_table("friendships"):
        op.create_table(
            "friendships",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("requester_id", sa.Integer(), nullable=False),
            sa.Column("addressee_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["addressee_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
        )


def downgrade():
    if _has_table("friendships"):
        op.drop_table("friendships")
    if _has_table("users") and _has_column("users", "invite_token"):
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.drop_index("ix_users_invite_token")
            batch_op.drop_column("invite_token")
