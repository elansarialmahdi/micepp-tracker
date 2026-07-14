"""Add NVD CPE cache and vulnerability history.

Revision ID: 20260713_0008
Revises: 20260713_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0008"
down_revision: str | None = "20260713_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cpe_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("cpe_uri", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("vendor", sa.String(300)),
        sa.Column("product", sa.String(300)),
        sa.Column("version", sa.String(200)),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("method", sa.String(100), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "cpe_uri", name="uq_cpe_candidate_service_uri"),
    )
    op.create_index("ix_cpe_candidates_service_id", "cpe_candidates", ["service_id"])
    op.create_table(
        "vulnerabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cve_id", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("modified_at", sa.DateTime(timezone=True)),
        sa.Column("severity", sa.String(20)),
        sa.Column("cvss_score", sa.Float()),
        sa.Column("cvss_version", sa.String(20)),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column(
            "last_sync_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cve_id"),
    )
    op.create_index("ix_vulnerabilities_cve_id", "vulnerabilities", ["cve_id"], unique=True)
    op.create_index("ix_vulnerabilities_severity", "vulnerabilities", ["severity"])
    op.create_table(
        "service_vulnerabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("vulnerability_id", sa.Uuid(), nullable=False),
        sa.Column("match_state", sa.String(20), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("affected_configuration", sa.JSON()),
        sa.Column(
            "detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("ignored_at", sa.DateTime(timezone=True)),
        sa.Column("ignored_by", sa.Uuid()),
        sa.Column("ignore_reason", sa.Text()),
        sa.CheckConstraint(
            "match_state IN ('confirmed', 'probable', 'needs_review', 'not_affected', 'unknown')",
            name="ck_service_vulnerabilities_match_state",
        ),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vulnerability_id"], ["vulnerabilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ignored_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "vulnerability_id", name="uq_service_vulnerability"),
    )
    for column in ("service_id", "vulnerability_id", "match_state", "resolved_at", "ignored_at"):
        op.create_index(f"ix_service_vulnerabilities_{column}", "service_vulnerabilities", [column])
    op.create_table(
        "nvd_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cache_type", sa.String(30), nullable=False),
        sa.Column("cache_key", sa.String(2048), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("etag", sa.String(500)),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_type", "cache_key", name="uq_nvd_cache_type_key"),
    )
    op.create_index("ix_nvd_cache_cache_type", "nvd_cache", ["cache_type"])
    op.create_index("ix_nvd_cache_expires_at", "nvd_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_table("nvd_cache")
    op.drop_table("service_vulnerabilities")
    op.drop_table("vulnerabilities")
    op.drop_table("cpe_candidates")
