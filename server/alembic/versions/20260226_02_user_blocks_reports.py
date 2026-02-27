"""Add userblock and userreport tables

Revision ID: 20260226_02
Revises: 20260226_01
Create Date: 2026-02-26 19:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260226_02"
down_revision = "20260226_01"
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "userblock"):
        op.create_table(
            "userblock",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("blocker_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("blocked_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if not _table_exists(inspector, "userreport"):
        op.create_table(
            "userreport",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("reported_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("reason", sa.String(length=64), nullable=False),
            sa.Column("details", sa.String(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("userreport", "userblock"):
        if _table_exists(inspector, table):
            op.drop_table(table)
