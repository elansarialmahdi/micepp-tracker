"""Add platform categories and services.

Revision ID: 20260713_0004
Revises: 20260713_0003
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0004"
down_revision: str | None = "20260713_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_id", "normalized_name", name="uq_categories_platform_name"),
    )
    op.create_index("ix_categories_archived_at", "categories", ["archived_at"])
    op.create_index("ix_categories_platform_id", "categories", ["platform_id"])

    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("normalized_name", sa.String(length=300), nullable=False),
        sa.Column("vendor", sa.String(length=300), nullable=True),
        sa.Column("product", sa.String(length=300), nullable=True),
        sa.Column("version", sa.String(length=200), nullable=True),
        sa.Column("normalized_version", sa.String(length=200), nullable=True),
        sa.Column("cpe_uri", sa.String(length=2048), nullable=True),
        sa.Column("cpe_match_confidence", sa.Float(), nullable=True),
        sa.Column("cpe_match_method", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_details", sa.JSON(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('manual', 'excel', 'scan', 'api')", name="ck_services_source"
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "archived_at",
        "category_id",
        "created_at",
        "name",
        "normalized_name",
        "normalized_version",
        "platform_id",
        "source",
    ):
        op.create_index(f"ix_services_{column}", "services", [column])


def downgrade() -> None:
    for column in (
        "source",
        "platform_id",
        "normalized_version",
        "normalized_name",
        "name",
        "created_at",
        "category_id",
        "archived_at",
    ):
        op.drop_index(f"ix_services_{column}", table_name="services")
    op.drop_table("services")
    op.drop_index("ix_categories_platform_id", table_name="categories")
    op.drop_index("ix_categories_archived_at", table_name="categories")
    op.drop_table("categories")
