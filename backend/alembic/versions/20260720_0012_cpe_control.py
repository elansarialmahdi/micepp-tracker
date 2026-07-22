"""Allow automatic vulnerability lookup to be disabled per service.

Revision ID: 20260720_0012
Revises: 20260715_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260720_0012"
down_revision: str | None = "20260715_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "services",
        sa.Column("cpe_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("services", "cpe_enabled")
