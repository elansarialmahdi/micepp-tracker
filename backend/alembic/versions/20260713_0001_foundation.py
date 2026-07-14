"""Create the foundation migration baseline.

Revision ID: 20260713_0001
Revises:
Create Date: 2026-07-13
"""

from collections.abc import Sequence

revision: str = "20260713_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record a baseline before functional tables arrive in sprint 2."""


def downgrade() -> None:
    """Remove the baseline revision marker."""
