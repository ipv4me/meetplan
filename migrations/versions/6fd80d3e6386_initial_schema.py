"""Initial schema

Revision ID: 6fd80d3e6386
Revises:
Create Date: 2026-06-27 17:09:47.828878

"""
from alembic import op
import sqlalchemy as sa


revision = "6fd80d3e6386"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name):
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade():
    if _has_table("user_availability"):
        op.drop_table("user_availability")


def downgrade():
    if not _has_table("user_availability") and _has_table("users"):
        op.create_table(
            "user_availability",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("start_time", sa.Time(), nullable=False),
            sa.Column("end_time", sa.Time(), nullable=False),
            sa.Column("is_busy", sa.Boolean(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
