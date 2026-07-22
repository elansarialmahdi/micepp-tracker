from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ServiceSource(StrEnum):
    MANUAL = "manual"
    EXCEL = "excel"
    SCAN = "scan"
    API = "api"


class ServiceImport(Base):
    __tablename__ = "service_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'previewed', 'confirmed')",
            name="ck_service_imports_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    platform_id: Mapped[UUID] = mapped_column(
        ForeignKey("platforms.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    columns: Mapped[list] = mapped_column(JSON)
    raw_rows: Mapped[list] = mapped_column(JSON)
    mapping: Mapped[dict | None] = mapped_column(JSON)
    preview_rows: Mapped[list | None] = mapped_column(JSON)
    row_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC) + timedelta(hours=1),
        nullable=False,
        index=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_categories_normalized_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    services = relationship("Service", back_populates="category")


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'excel', 'scan', 'api')", name="ck_services_source"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    platform_id: Mapped[UUID] = mapped_column(
        ForeignKey("platforms.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), index=True)
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)
    vendor: Mapped[str | None] = mapped_column(String(300))
    product: Mapped[str | None] = mapped_column(String(300))
    version: Mapped[str | None] = mapped_column(String(200))
    normalized_version: Mapped[str | None] = mapped_column(String(200), index=True)
    cpe_uri: Mapped[str | None] = mapped_column(String(2048))
    cpe_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    cpe_match_confidence: Mapped[float | None] = mapped_column(Float)
    cpe_match_method: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20), index=True)
    source_details: Mapped[dict | None] = mapped_column(JSON)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    platform = relationship("Platform", back_populates="services")
    category = relationship("Category", back_populates="services", lazy="selectin")
    creator = relationship("User", back_populates="services")

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None

    @property
    def security_identity(self) -> dict | None:
        return (self.source_details or {}).get("security_identity")
