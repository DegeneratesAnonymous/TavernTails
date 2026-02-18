"""Add gm_user_id and gm_mode to Campaign

Revision ID: 20260218_01
Revises: 20251201_01
Create Date: 2026-02-18 20:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260218_01"
down_revision = "20251201_01"
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Add gm_user_id and gm_mode columns to campaign table
    if _table_exists(inspector, "campaign"):
        with op.batch_alter_table("campaign") as batch_op:
            if not _column_exists(inspector, "campaign", "gm_user_id"):
                batch_op.add_column(sa.Column("gm_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True))
            if not _column_exists(inspector, "campaign", "gm_mode"):
                batch_op.add_column(sa.Column("gm_mode", sa.String(length=16), nullable=False, server_default="ai"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Remove gm_user_id and gm_mode columns from campaign table
    if _table_exists(inspector, "campaign"):
        with op.batch_alter_table("campaign") as batch_op:
            if _column_exists(inspector, "campaign", "gm_mode"):
                batch_op.drop_column("gm_mode")
            if _column_exists(inspector, "campaign", "gm_user_id"):
                batch_op.drop_column("gm_user_id")
