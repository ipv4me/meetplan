"""Add per-friend calendar detail sharing flags

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    if not _has_column("friendships", "requester_shares_details"):
        with op.batch_alter_table("friendships", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("requester_shares_details", sa.Boolean(), nullable=False, server_default=sa.false())
            )
    if not _has_column("friendships", "addressee_shares_details"):
        with op.batch_alter_table("friendships", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("addressee_shares_details", sa.Boolean(), nullable=False, server_default=sa.false())
            )


def downgrade():
    if _has_column("friendships", "addressee_shares_details"):
        with op.batch_alter_table("friendships", schema=None) as batch_op:
            batch_op.drop_column("addressee_shares_details")
    if _has_column("friendships", "requester_shares_details"):
        with op.batch_alter_table("friendships", schema=None) as batch_op:
            batch_op.drop_column("requester_shares_details")
