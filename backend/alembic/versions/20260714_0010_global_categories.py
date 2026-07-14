"""Make service categories global across platforms.

Revision ID: 20260714_0010
Revises: 20260713_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260714_0010"
down_revision: str | None = "20260713_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reattach services to one canonical category before removing duplicates.
    op.execute(
        """
        WITH canonical AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY normalized_name
                       ORDER BY (archived_at IS NULL) DESC, created_at, id
                   ) AS keep_id
            FROM categories
        )
        UPDATE services AS service
        SET category_id = canonical.keep_id
        FROM canonical
        WHERE service.category_id = canonical.id
          AND canonical.id <> canonical.keep_id
        """
    )
    op.execute(
        """
        WITH duplicates AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY normalized_name
                       ORDER BY (archived_at IS NULL) DESC, created_at, id
                   ) AS position
            FROM categories
        )
        DELETE FROM categories
        USING duplicates
        WHERE categories.id = duplicates.id AND duplicates.position > 1
        """
    )
    op.drop_constraint("uq_categories_platform_name", "categories", type_="unique")
    op.drop_constraint("categories_platform_id_fkey", "categories", type_="foreignkey")
    op.drop_index("ix_categories_platform_id", table_name="categories")
    op.drop_column("categories", "platform_id")
    op.create_unique_constraint("uq_categories_normalized_name", "categories", ["normalized_name"])


def downgrade() -> None:
    op.drop_constraint("uq_categories_normalized_name", "categories", type_="unique")
    op.add_column("categories", sa.Column("platform_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE categories AS category
        SET platform_id = source.platform_id
        FROM (
            SELECT DISTINCT ON (category_id) category_id, platform_id
            FROM services
            WHERE category_id IS NOT NULL
            ORDER BY category_id, created_at
        ) AS source
        WHERE category.id = source.category_id
        """
    )
    op.execute("DELETE FROM categories WHERE platform_id IS NULL")
    op.alter_column("categories", "platform_id", nullable=False)
    op.create_index("ix_categories_platform_id", "categories", ["platform_id"])
    op.create_foreign_key(
        "categories_platform_id_fkey",
        "categories",
        "platforms",
        ["platform_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_categories_platform_name",
        "categories",
        ["platform_id", "normalized_name"],
    )
