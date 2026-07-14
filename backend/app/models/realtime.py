from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RealtimeProtectionSetting(Base):
    __tablename__ = "realtime_protection_settings"
    __table_args__ = (
        UniqueConstraint("setting_key", name="uq_realtime_protection_setting_key"),
        CheckConstraint("interval_seconds >= 60", name="ck_realtime_interval"),
        CheckConstraint("batch_size >= 1 AND batch_size <= 100", name="ck_realtime_batch_size"),
        CheckConstraint(
            "max_concurrency >= 1 AND max_concurrency <= 10",
            name="ck_realtime_max_concurrency",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    setting_key: Mapped[str] = mapped_column(String(30), default="global")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    batch_size: Mapped[int] = mapped_column(Integer, default=25)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=2)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProtectionJob(Base):
    __tablename__ = "protection_jobs"
    __table_args__ = (
        CheckConstraint("trigger IN ('manual', 'scheduled')", name="ck_protection_jobs_trigger"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'skipped')",
            name="ck_protection_jobs_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    trigger: Mapped[str] = mapped_column(String(20), index=True)
    requested_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    total_services: Mapped[int] = mapped_column(Integer, default=0)
    processed_services: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_services: Mapped[int] = mapped_column(Integer, default=0)
    failed_services: Mapped[int] = mapped_column(Integer, default=0)
    new_notifications: Mapped[int] = mapped_column(Integer, default=0)
    current_batch: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
