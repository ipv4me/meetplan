"""Calendar details visible by default; global hide option

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-28 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    if not _has_column("users", "hide_calendar_details_from_friends"):
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "hide_calendar_details_from_friends",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
    if _has_column("friendships", "requester_shares_details"):
        op.execute("UPDATE friendships SET requester_shares_details = 1")
    if _has_column("friendships", "addressee_shares_details"):
        op.execute("UPDATE friendships SET addressee_shares_details = 1")


def downgrade():
    if _has_column("users", "hide_calendar_details_from_friends"):
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.drop_column("hide_calendar_details_from_friends")
