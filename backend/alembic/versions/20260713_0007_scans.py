"""Add asynchronous scan jobs and detected services.

Revision ID: 20260713_0007
Revises: 20260713_0006
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0007"
down_revision: str | None = "20260713_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(length=2048), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("scan_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=False),
        sa.Column("authorization_confirmed", sa.Boolean(), nullable=False),
        sa.Column("resolved_addresses", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("sanitized_error", sa.String(length=500), nullable=True),
        sa.Column("raw_result_reference", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_scan_jobs_progress"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_scan_jobs_status",
        ),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("created_at", "platform_id", "requested_by", "status"):
        op.create_index(f"ix_scan_jobs_{column}", "scan_jobs", [column])
    op.create_table(
        "detected_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_job_id", sa.Uuid(), nullable=False),
        sa.Column("detected_name", sa.String(length=300), nullable=False),
        sa.Column("detected_version", sa.String(length=200), nullable=True),
        sa.Column("detected_vendor", sa.String(length=300), nullable=True),
        sa.Column("detected_product", sa.String(length=300), nullable=True),
        sa.Column("detected_cpe", sa.String(length=2048), nullable=True),
        sa.Column("source_detector", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("protocol", sa.String(length=30), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("category_suggestion", sa.String(length=200), nullable=True),
        sa.Column("category_confidence", sa.Float(), nullable=True),
        sa.Column("selected_for_import", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["scan_job_id"], ["scan_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detected_services_scan_job_id", "detected_services", ["scan_job_id"])


def downgrade() -> None:
    op.drop_index("ix_detected_services_scan_job_id", table_name="detected_services")
    op.drop_table("detected_services")
    for column in ("status", "requested_by", "platform_id", "created_at"):
        op.drop_index(f"ix_scan_jobs_{column}", table_name="scan_jobs")
    op.drop_table("scan_jobs")
