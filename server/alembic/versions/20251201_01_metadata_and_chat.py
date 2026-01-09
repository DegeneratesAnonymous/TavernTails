"""Add campaign metadata JSON and chat message table

Revision ID: 20251201_01
Revises: 
Create Date: 2025-12-01 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20251201_01"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _column_exists(inspector, "campaign", "metadata_json"):
        with op.batch_alter_table("campaign") as batch_op:
            batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))

    if not _table_exists(inspector, "chatmessage"):
        op.create_table(
            "chatmessage",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.String(length=64), index=True),
            sa.Column("campaign_id", sa.String(length=16), index=True),
            sa.Column("sender_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("sender_name", sa.String(length=120), nullable=True),
            sa.Column("role", sa.String(length=32), nullable=False, server_default="player"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
        )
        op.create_index("ix_chatmessage_session_id", "chatmessage", ["session_id"])
        op.create_index("ix_chatmessage_campaign_id", "chatmessage", ["campaign_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "chatmessage"):
        op.drop_index("ix_chatmessage_session_id", table_name="chatmessage")
        op.drop_index("ix_chatmessage_campaign_id", table_name="chatmessage")
        op.drop_table("chatmessage")

    if _column_exists(inspector, "campaign", "metadata_json"):
        with op.batch_alter_table("campaign") as batch_op:
            batch_op.drop_column("metadata_json")
