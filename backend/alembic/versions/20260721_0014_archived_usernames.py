"""Allow an archived user's username to be reused.

Revision ID: 20260721_0014
Revises: 20260720_0013
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0014"
down_revision: str | None = "20260720_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
        sqlite_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.create_index("ix_users_username", "users", ["username"], unique=True)
