"""Add periodic protection settings and jobs.

Revision ID: 20260713_0009
Revises: 20260713_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0009"
down_revision: str | None = "20260713_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "realtime_protection_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("setting_key", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("max_concurrency", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.Uuid()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("interval_seconds >= 60", name="ck_realtime_interval"),
        sa.CheckConstraint("batch_size >= 1 AND batch_size <= 100", name="ck_realtime_batch_size"),
        sa.CheckConstraint(
            "max_concurrency >= 1 AND max_concurrency <= 10",
            name="ck_realtime_max_concurrency",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("setting_key", name="uq_realtime_protection_setting_key"),
    )
    op.create_index(
        "ix_realtime_protection_settings_next_run_at",
        "realtime_protection_settings",
        ["next_run_at"],
    )
    op.create_table(
        "protection_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("requested_by", sa.Uuid()),
        sa.Column("idempotency_key", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total_services", sa.Integer(), nullable=False),
        sa.Column("processed_services", sa.Integer(), nullable=False),
        sa.Column("succeeded_services", sa.Integer(), nullable=False),
        sa.Column("failed_services", sa.Integer(), nullable=False),
        sa.Column("new_notifications", sa.Integer(), nullable=False),
        sa.Column("current_batch", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("trigger IN ('manual', 'scheduled')", name="ck_protection_jobs_trigger"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'skipped')",
            name="ck_protection_jobs_status",
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for column in ("created_at", "requested_by", "status", "trigger"):
        op.create_index(f"ix_protection_jobs_{column}", "protection_jobs", [column])


def downgrade() -> None:
    op.drop_table("protection_jobs")
    op.drop_table("realtime_protection_settings")
