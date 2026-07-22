from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TreatmentStatus(StrEnum):
    ASSIGNED = "assigned"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class VulnerabilityTreatment(Base):
    __tablename__ = "vulnerability_treatments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('assigned', 'submitted', 'confirmed', 'cancelled')",
            name="ck_vulnerability_treatments_status",
        ),
        Index("ix_vulnerability_treatments_assignee_status", "assigned_to_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    service_id: Mapped[UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True
    )
    assigned_to_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    confirmed_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=TreatmentStatus.ASSIGNED.value, index=True
    )
    assignment_note: Mapped[str | None] = mapped_column(Text)
    completion_note: Mapped[str | None] = mapped_column(Text)
    service_version_before: Mapped[str | None] = mapped_column(String(200))
    new_version: Mapped[str | None] = mapped_column(String(200))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service = relationship("Service", lazy="selectin")
    assignee = relationship("User", foreign_keys=[assigned_to_id], lazy="selectin")
    assigner = relationship("User", foreign_keys=[assigned_by_id], lazy="selectin")
    confirmer = relationship("User", foreign_keys=[confirmed_by_id], lazy="selectin")
