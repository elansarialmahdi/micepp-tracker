from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class NotificationPlatform(Base):
    __tablename__ = "notification_platforms"
    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    platform_id: Mapped[UUID] = mapped_column(
        ForeignKey("platforms.id", ondelete="CASCADE"), primary_key=True
    )


class NotificationUserState(Base):
    __tablename__ = "notification_user_states"
    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notification = relationship("Notification", back_populates="user_states")
    user = relationship("User", back_populates="notification_states")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_notifications_severity",
        ),
        Index(
            "uq_notifications_vulnerability_service",
            "service_id",
            unique=True,
            postgresql_where=text(
                "type = 'vulnerability.detected' AND service_id IS NOT NULL"
            ),
            sqlite_where=text("type = 'vulnerability.detected' AND service_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    vulnerability_id: Mapped[UUID | None] = mapped_column(nullable=True)
    service_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    platforms = relationship("Platform", secondary="notification_platforms", lazy="selectin")
    service = relationship("Service", lazy="selectin")
    user_states = relationship("NotificationUserState", back_populates="notification")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(150), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[UUID | None] = mapped_column(index=True)
    platform_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platforms.id", ondelete="SET NULL"), index=True
    )
    summary: Mapped[str] = mapped_column(String(500))
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    actor = relationship("User", back_populates="audit_events")


class HistoryVisibilityState(Base):
    __tablename__ = "history_visibility_states"
    __table_args__ = (
        UniqueConstraint("user_id", "platform_id", name="uq_history_visibility_user_platform"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platforms.id", ondelete="CASCADE"), index=True
    )
    hidden_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="history_visibility_states")


@event.listens_for(AuditEvent, "before_update", propagate=True)
def prevent_audit_update(*_args) -> None:  # type: ignore[no-untyped-def]
    raise RuntimeError("Audit events are immutable")


@event.listens_for(AuditEvent, "before_delete", propagate=True)
def prevent_audit_delete(*_args) -> None:  # type: ignore[no-untyped-def]
    raise RuntimeError("Audit events are immutable")
