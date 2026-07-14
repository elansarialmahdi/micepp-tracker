from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import AuditEvent, Notification
from app.models.platform import Platform


def request_audit_context(request: Request) -> dict[str, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",", 1)[0].strip() if forwarded else None
    if ip is None and request.client:
        ip = request.client.host
    return {
        "ip": ip,
        "request_id": getattr(request.state, "request_id", None),
    }


def record_audit(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    summary: str,
    actor_user_id: UUID | None = None,
    entity_id: UUID | None = None,
    platform_id: UUID | None = None,
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        platform_id=platform_id,
        summary=summary,
        before_data=before_data,
        after_data=after_data,
        event_metadata=metadata or {},
        ip=ip,
        request_id=request_id,
    )
    db.add(event)
    return event


def create_notification(
    db: AsyncSession,
    *,
    type: str,
    title: str,
    message: str,
    severity: str = "info",
    platforms: list[Platform] | None = None,
    service_id: UUID | None = None,
    vulnerability_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> Notification:
    notification = Notification(
        type=type,
        title=title,
        message=message,
        severity=severity,
        platforms=platforms or [],
        service_id=service_id,
        vulnerability_id=vulnerability_id,
        event_metadata=metadata or {},
    )
    db.add(notification)
    return notification
