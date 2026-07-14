from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlatformTargetType(StrEnum):
    URL = "url"
    IP = "ip"
    NONE = "none"


class Platform(Base):
    __tablename__ = "platforms"
    __table_args__ = (
        CheckConstraint("target_type IN ('url', 'ip', 'none')", name="ck_platforms_target_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    target_type: Mapped[str] = mapped_column(String(10), index=True)
    target_value: Mapped[str | None] = mapped_column(String(2048))
    normalized_target: Mapped[str | None] = mapped_column(String(2048), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_inventory_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_vulnerability_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    creator = relationship("User", back_populates="platforms")
    services = relationship("Service", back_populates="platform")
