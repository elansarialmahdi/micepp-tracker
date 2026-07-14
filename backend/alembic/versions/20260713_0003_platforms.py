"""Add platforms.

Revision ID: 20260713_0003
Revises: 20260713_0002
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0003"
down_revision: str | None = "20260713_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platforms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("target_type", sa.String(length=10), nullable=False),
        sa.Column("target_value", sa.String(length=2048), nullable=True),
        sa.Column("normalized_target", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_inventory_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_vulnerability_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("target_type IN ('url', 'ip', 'none')", name="ck_platforms_target_type"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platforms_archived_at", "platforms", ["archived_at"])
    op.create_index("ix_platforms_created_at", "platforms", ["created_at"])
    op.create_index("ix_platforms_created_by", "platforms", ["created_by"])
    op.create_index("ix_platforms_name", "platforms", ["name"])
    op.create_index("ix_platforms_normalized_target", "platforms", ["normalized_target"])
    op.create_index("ix_platforms_target_type", "platforms", ["target_type"])


def downgrade() -> None:
    op.drop_index("ix_platforms_target_type", table_name="platforms")
    op.drop_index("ix_platforms_normalized_target", table_name="platforms")
    op.drop_index("ix_platforms_name", table_name="platforms")
    op.drop_index("ix_platforms_created_by", table_name="platforms")
    op.drop_index("ix_platforms_created_at", table_name="platforms")
    op.drop_index("ix_platforms_archived_at", table_name="platforms")
    op.drop_table("platforms")
