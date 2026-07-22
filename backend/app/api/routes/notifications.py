from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import CurrentUser, require_permissions
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
    ActivityPageViewRequest,
    AuditEventListResponse,
    AuditEventResponse,
    NotificationListResponse,
    NotificationPlatformResponse,
    NotificationResponse,
)
from app.services.audit import (
    record_audit,
    request_audit_context,
    request_client_metadata,
)

router = APIRouter(prefix="/v1", tags=["notifications", "history"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
NotificationReader = Annotated[User, Depends(require_permissions("notification.read"))]
NotificationHider = Annotated[User, Depends(require_permissions("notification.hide"))]
HistoryReader = Annotated[User, Depends(require_permissions("history.read"))]
HistoryHider = Annotated[User, Depends(require_permissions("history.hide"))]
HistoryClearer = Annotated[User, Depends(require_permissions("history.clear"))]


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


def audit_event_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
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


def audit_failure_condition():  # type: ignore[no-untyped-def]
    return or_(
        AuditEvent.action.ilike("%.failed"),
        AuditEvent.action.ilike("%.failure"),
        AuditEvent.action.ilike("%denied%"),
    )


@router.get("/notifications", response_model=NotificationListResponse)
async def notifications_index(
    db: DBSession,
    user: NotificationReader,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    hidden: bool = False,
) -> NotificationListResponse:
    ranked_threat_notifications = (
        select(
            Notification.id.label("notification_id"),
            func.row_number()
            .over(
                partition_by=Notification.service_id,
                order_by=(Notification.created_at.desc(), Notification.id.desc()),
            )
            .label("position"),
        )
        .where(
            Notification.type == "vulnerability.detected",
            Notification.service_id.is_not(None),
        )
        .subquery()
    )
    latest_threat_ids = select(ranked_threat_notifications.c.notification_id).where(
        ranked_threat_notifications.c.position == 1
    )
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
        .where(
            or_(
                Notification.type != "vulnerability.detected",
                Notification.service_id.is_(None),
                Notification.id.in_(latest_threat_ids),
            )
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
        items=[audit_event_response(event) for event in events],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/activity", response_model=AuditEventListResponse)
async def activity_index(
    db: DBSession,
    _user: HistoryReader,
    q: str | None = Query(default=None, max_length=200),
    result: Literal["all", "success", "failure"] = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> AuditEventListResponse:
    query = (
        select(AuditEvent)
        .options(selectinload(AuditEvent.actor))
        .where(AuditEvent.entity_type != "http_request")
    )
    hidden_before = await db.scalar(
        select(func.max(HistoryVisibilityState.hidden_before)).where(
            HistoryVisibilityState.platform_id.is_(None)
        )
    )
    if hidden_before is not None:
        query = query.where(AuditEvent.created_at > hidden_before)
    if q and (term := q.strip()):
        pattern = f"%{term}%"
        query = query.outerjoin(User, AuditEvent.actor_user_id == User.id).where(
            or_(
                AuditEvent.summary.ilike(pattern),
                AuditEvent.action.ilike(pattern),
                AuditEvent.entity_type.ilike(pattern),
                AuditEvent.ip.ilike(pattern),
                User.username.ilike(pattern),
                User.display_name.ilike(pattern),
            )
        )

    failure_condition = audit_failure_condition()
    base_count_query = select(func.count()).select_from(query.subquery())
    failure_count_query = select(func.count()).select_from(
        query.where(failure_condition).subquery()
    )
    base_total = await db.scalar(base_count_query) or 0
    failure_total = await db.scalar(failure_count_query) or 0

    if result == "failure":
        query = query.where(failure_condition)
    elif result == "success":
        query = query.where(~failure_condition)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    events = (
        await db.scalars(
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return AuditEventListResponse(
        items=[audit_event_response(event) for event in events],
        total=total,
        page=page,
        page_size=page_size,
        success_total=base_total - failure_total,
        failure_total=failure_total,
    )


@router.post("/activity/page-view", status_code=204)
async def activity_page_view(
    payload: ActivityPageViewRequest,
    request: Request,
    db: DBSession,
    user: CurrentUser,
) -> None:
    path = payload.path.strip()
    if not path.startswith("/"):
        raise AppError(422, "INVALID_PAGE_PATH", "Le chemin de page est invalide.")
    title = payload.title.strip() if payload.title else path
    record_audit(
        db,
        actor_user_id=user.id,
        action="page.view",
        entity_type="page",
        summary=f"Page consultée : {title}",
        metadata={
            "path": path,
            "title": title,
            "result": "success",
            **request_client_metadata(request),
        },
        **request_audit_context(request),
    )
    await db.commit()


@router.post("/activity/hide", status_code=204)
async def activity_hide(db: DBSession, user: HistoryClearer) -> None:
    """Hide existing global activity without deleting immutable audit events."""
    visibility = await db.scalar(
        select(HistoryVisibilityState)
        .where(
            HistoryVisibilityState.user_id == user.id,
            HistoryVisibilityState.platform_id.is_(None),
        )
        .order_by(HistoryVisibilityState.updated_at.desc())
        .limit(1)
    )
    now = datetime.now(UTC)
    if visibility is None:
        db.add(
            HistoryVisibilityState(
                user_id=user.id,
                platform_id=None,
                hidden_before=now,
            )
        )
    else:
        visibility.hidden_before = now
    await db.commit()


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
