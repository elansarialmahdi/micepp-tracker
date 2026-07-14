from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ScanJob(Base):
    __tablename__ = "scan_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_scan_jobs_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_scan_jobs_progress"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    platform_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platforms.id", ondelete="SET NULL"), index=True
    )
    requested_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    target: Mapped[str] = mapped_column(String(2048))
    target_type: Mapped[str] = mapped_column(String(20))
    scan_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String(100), default="queued")
    authorization_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_addresses: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    sanitized_error: Mapped[str | None] = mapped_column(String(500))
    raw_result_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    detections = relationship(
        "DetectedService", back_populates="scan_job", cascade="all, delete-orphan", lazy="selectin"
    )


class DetectedService(Base):
    __tablename__ = "detected_services"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scan_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("scan_jobs.id", ondelete="CASCADE"), index=True
    )
    detected_name: Mapped[str] = mapped_column(String(300))
    detected_version: Mapped[str | None] = mapped_column(String(200))
    detected_vendor: Mapped[str | None] = mapped_column(String(300))
    detected_product: Mapped[str | None] = mapped_column(String(300))
    detected_cpe: Mapped[str | None] = mapped_column(String(2048))
    source_detector: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)
    port: Mapped[int | None] = mapped_column(Integer)
    protocol: Mapped[str | None] = mapped_column(String(30))
    detection_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    category_suggestion: Mapped[str | None] = mapped_column(String(200))
    category_confidence: Mapped[float | None] = mapped_column(Float)
    selected_for_import: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan_job = relationship("ScanJob", back_populates="detections")
