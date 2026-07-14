"""Add secure service import staging.

Revision ID: 20260713_0006
Revises: 20260713_0005
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0006"
down_revision: str | None = "20260713_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("raw_rows", sa.JSON(), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=True),
        sa.Column("preview_rows", sa.JSON(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('uploaded', 'previewed', 'confirmed')",
            name="ck_service_imports_status",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_imports_created_by", "service_imports", ["created_by"])
    op.create_index("ix_service_imports_expires_at", "service_imports", ["expires_at"])
    op.create_index("ix_service_imports_platform_id", "service_imports", ["platform_id"])
    op.create_index("ix_service_imports_status", "service_imports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_service_imports_status", table_name="service_imports")
    op.drop_index("ix_service_imports_platform_id", table_name="service_imports")
    op.drop_index("ix_service_imports_expires_at", table_name="service_imports")
    op.drop_index("ix_service_imports_created_by", table_name="service_imports")
    op.drop_table("service_imports")
