"""Add savedworld table

Revision ID: 20261013_01
Revises: 20260226_02
Create Date: 2026-10-13 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20261013_01"
down_revision = "20260226_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "savedworld" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "savedworld",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("narrative", sa.String(), nullable=False, server_default=""),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "savedworld" in sa.inspect(bind).get_table_names():
        op.drop_table("savedworld")
