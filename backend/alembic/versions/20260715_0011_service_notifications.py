"""Aggregate vulnerability notifications by service.

Revision ID: 20260715_0011
Revises: 20260714_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260715_0011"
down_revision: str | None = "20260714_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM notifications
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY service_id
                           ORDER BY created_at DESC, id DESC
                       ) AS position
                FROM notifications
                WHERE type = 'vulnerability.detected'
                  AND service_id IS NOT NULL
            ) AS ranked
            WHERE ranked.position > 1
        )
        """
    )
    predicate = sa.text("type = 'vulnerability.detected' AND service_id IS NOT NULL")
    op.create_index(
        "uq_notifications_vulnerability_service",
        "notifications",
        ["service_id"],
        unique=True,
        postgresql_where=predicate,
        sqlite_where=predicate,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_notifications_vulnerability_service",
        table_name="notifications",
    )
