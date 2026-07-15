from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import require_permissions
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.notification import (
    AuditEvent,
    HistoryVisibilityState,
    Notification,
    NotificationUserState,
)
from app.repositories.platforms import get_platform
from app.schemas.notification import (
    AuditEventListResponse,
    AuditEventResponse,
    NotificationListResponse,
    NotificationPlatformResponse,
    NotificationResponse,
)
from app.services.audit import record_audit, request_audit_context

router = APIRouter(prefix="/v1", tags=["notifications", "history"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
NotificationReader = Annotated[User, Depends(require_permissions("notification.read"))]
NotificationHider = Annotated[User, Depends(require_permissions("notification.hide"))]
HistoryReader = Annotated[User, Depends(require_permissions("history.read"))]
HistoryHider = Annotated[User, Depends(require_permissions("history.hide"))]


async def notification_state(
    db: AsyncSession, notification_id: UUID, user_id: UUID
) -> NotificationUserState:
    state = await db.get(NotificationUserState, (notification_id, user_id))
    if state is None:
        state = NotificationUserState(notification_id=notification_id, user_id=user_id)
        db.add(state)
    return state


async def required_notification(db: AsyncSession, notification_id: UUID) -> Notification:
    notification = await db.get(Notification, notification_id)
    if notification is None:
        raise AppError(404, "NOTIFICATION_NOT_FOUND", "La notification est introuvable.")
    return notification


def notification_response(
    notification: Notification, state: NotificationUserState | None
) -> NotificationResponse:
    metadata = notification.event_metadata or {}
    threat_identifier = metadata.get("identifier") or metadata.get("cve_id")
    return NotificationResponse(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        message=notification.message,
        severity=notification.severity,
        vulnerability_id=notification.vulnerability_id,
        service_id=notification.service_id,
        service_name=notification.service.name if notification.service else None,
        service_version=notification.service.version if notification.service else None,
        threat_identifier=str(threat_identifier) if threat_identifier else None,
        platform_ids=[platform.id for platform in notification.platforms],
        platforms=[
            NotificationPlatformResponse(id=platform.id, name=platform.name)
            for platform in notification.platforms
        ],
        created_at=notification.created_at,
        read_at=state.read_at if state else None,
        is_read=bool(state and state.read_at),
        metadata=metadata,
    )


@router.get("/notifications", response_model=NotificationListResponse)
async def notifications_index(
    db: DBSession,
    user: NotificationReader,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    hidden: bool = False,
) -> NotificationListResponse:
    visible = (
        select(Notification, NotificationUserState)
        .outerjoin(
            NotificationUserState,
            (NotificationUserState.notification_id == Notification.id)
            & (NotificationUserState.user_id == user.id),
        )
        .where(
            NotificationUserState.hidden_at.is_not(None)
            if hidden
            else NotificationUserState.hidden_at.is_(None)
        )
    )
    total = await db.scalar(select(func.count()).select_from(visible.subquery())) or 0
    rows = (
        await db.execute(
            visible.options(
                selectinload(Notification.platforms),
                selectinload(Notification.service),
            )
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return NotificationListResponse(
        items=[notification_response(item, state) for item, state in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/notifications/hide-all", status_code=204)
async def notifications_hide_all(db: DBSession, user: NotificationHider) -> None:
    ids = (await db.scalars(select(Notification.id))).all()
    now = datetime.now(UTC)
    for notification_id in ids:
        state = await notification_state(db, notification_id, user.id)
        state.hidden_at = now
    await db.commit()


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def notifications_read(
    notification_id: UUID, db: DBSession, user: NotificationReader
) -> NotificationResponse:
    notification = await required_notification(db, notification_id)
    state = await notification_state(db, notification_id, user.id)
    state.read_at = state.read_at or datetime.now(UTC)
    await db.commit()
    await db.refresh(notification, attribute_names=["platforms", "service"])
    return notification_response(notification, state)


@router.post("/notifications/{notification_id}/hide", status_code=204)
async def notifications_hide(notification_id: UUID, db: DBSession, user: NotificationHider) -> None:
    await required_notification(db, notification_id)
    state = await notification_state(db, notification_id, user.id)
    state.hidden_at = datetime.now(UTC)
    await db.commit()


@router.get("/platforms/{platform_id}/history", response_model=AuditEventListResponse)
async def platform_history(
    platform_id: UUID,
    db: DBSession,
    user: HistoryReader,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    hidden: bool = False,
) -> AuditEventListResponse:
    if await get_platform(db, platform_id) is None:
        raise AppError(404, "PLATFORM_NOT_FOUND", "La plateforme est introuvable.")
    visibility = await db.scalar(
        select(HistoryVisibilityState).where(
            HistoryVisibilityState.user_id == user.id,
            HistoryVisibilityState.platform_id == platform_id,
        )
    )
    query = (
        select(AuditEvent)
        .options(selectinload(AuditEvent.actor))
        .where(AuditEvent.platform_id == platform_id)
    )
    if visibility:
        query = query.where(
            AuditEvent.created_at <= visibility.hidden_before
            if hidden
            else AuditEvent.created_at > visibility.hidden_before
        )
    elif hidden:
        query = query.where(False)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    events = (
        await db.scalars(
            query.order_by(AuditEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return AuditEventListResponse(
        items=[
            AuditEventResponse(
                id=event.id,
                actor_user_id=event.actor_user_id,
                actor_name=event.actor.display_name if event.actor else None,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                platform_id=event.platform_id,
                summary=event.summary,
                before_data=event.before_data,
                after_data=event.after_data,
                metadata=event.event_metadata,
                ip=event.ip,
                request_id=event.request_id,
                created_at=event.created_at,
            )
            for event in events
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/platforms/{platform_id}/history/hide", status_code=204)
async def platform_history_hide(
    platform_id: UUID, request: Request, db: DBSession, user: HistoryHider
) -> None:
    if await get_platform(db, platform_id) is None:
        raise AppError(404, "PLATFORM_NOT_FOUND", "La plateforme est introuvable.")
    visibility = await db.scalar(
        select(HistoryVisibilityState).where(
            HistoryVisibilityState.user_id == user.id,
            HistoryVisibilityState.platform_id == platform_id,
        )
    )
    now = datetime.now(UTC)
    if visibility is None:
        visibility = HistoryVisibilityState(
            user_id=user.id, platform_id=platform_id, hidden_before=now
        )
        db.add(visibility)
    else:
        visibility.hidden_before = now
    record_audit(
        db,
        actor_user_id=user.id,
        action="history.hide",
        entity_type="platform_history",
        platform_id=platform_id,
        summary="Historique masqué pour l’utilisateur",
        **request_audit_context(request),
    )
    await db.commit()
