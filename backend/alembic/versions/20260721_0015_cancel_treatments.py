"""Allow vulnerability treatments to be cancelled.

Revision ID: 20260721_0015
Revises: 20260721_0014
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0015"
down_revision: str | None = "20260721_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_vulnerability_treatments_status",
        "vulnerability_treatments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_vulnerability_treatments_status",
        "vulnerability_treatments",
        "status IN ('assigned', 'submitted', 'confirmed', 'cancelled')",
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE vulnerability_treatments "
            "SET status = 'assigned' WHERE status = 'cancelled'"
        )
    )
    op.drop_constraint(
        "ck_vulnerability_treatments_status",
        "vulnerability_treatments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_vulnerability_treatments_status",
        "vulnerability_treatments",
        "status IN ('assigned', 'submitted', 'confirmed')",
    )
