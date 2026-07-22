"""Attach treatments to services instead of individual vulnerabilities.

Revision ID: 20260721_0016
Revises: 20260721_0015
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0016"
down_revision: str | None = "20260721_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vulnerability_treatments",
        sa.Column("service_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE vulnerability_treatments AS treatment "
            "SET service_id = finding.service_id "
            "FROM service_vulnerabilities AS finding "
            "WHERE finding.id = treatment.service_vulnerability_id"
        )
    )
    op.alter_column("vulnerability_treatments", "service_id", nullable=False)
    op.create_foreign_key(
        "fk_vulnerability_treatments_service_id",
        "vulnerability_treatments",
        "services",
        ["service_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_vulnerability_treatments_service_id",
        "vulnerability_treatments",
        ["service_id"],
    )
    op.drop_index(
        "ix_vulnerability_treatments_service_vulnerability_id",
        table_name="vulnerability_treatments",
    )
    op.drop_constraint(
        "vulnerability_treatments_service_vulnerability_id_fkey",
        "vulnerability_treatments",
        type_="foreignkey",
    )
    op.drop_column("vulnerability_treatments", "service_vulnerability_id")


def downgrade() -> None:
    op.add_column(
        "vulnerability_treatments",
        sa.Column("service_vulnerability_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE vulnerability_treatments AS treatment "
            "SET service_vulnerability_id = ("
            "SELECT finding.id FROM service_vulnerabilities AS finding "
            "WHERE finding.service_id = treatment.service_id "
            "ORDER BY finding.detected_at LIMIT 1)"
        )
    )
    op.alter_column("vulnerability_treatments", "service_vulnerability_id", nullable=False)
    op.create_foreign_key(
        "vulnerability_treatments_service_vulnerability_id_fkey",
        "vulnerability_treatments",
        "service_vulnerabilities",
        ["service_vulnerability_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_vulnerability_treatments_service_vulnerability_id",
        "vulnerability_treatments",
        ["service_vulnerability_id"],
    )
    op.drop_index(
        "ix_vulnerability_treatments_service_id",
        table_name="vulnerability_treatments",
    )
    op.drop_constraint(
        "fk_vulnerability_treatments_service_id",
        "vulnerability_treatments",
        type_="foreignkey",
    )
    op.drop_column("vulnerability_treatments", "service_id")
