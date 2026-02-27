"""Add supportticket table

Revision ID: 20260226_01
Revises: 20260218_01
Create Date: 2026-02-26 18:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260226_01"
down_revision = "20260218_01"
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "supportticket"):
        op.create_table(
            "supportticket",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
            sa.Column("subject", sa.String(), nullable=False),
            sa.Column("body", sa.String(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "supportticket"):
        op.drop_table("supportticket")
