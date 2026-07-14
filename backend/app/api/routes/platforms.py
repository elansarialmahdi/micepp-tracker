import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_permissions
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.platform import Platform, PlatformTargetType
from app.models.service import Service
from app.models.vulnerability import ServiceVulnerability
from app.repositories.platforms import get_platform, list_platforms
from app.schemas.platform import (
    PlatformCreate,
    PlatformListResponse,
    PlatformResponse,
    PlatformSort,
    PlatformUpdate,
)
from app.services.audit import record_audit, request_audit_context
from app.services.platforms import InvalidPlatformTarget, normalize_platform_target

router = APIRouter(prefix="/v1/platforms", tags=["platforms"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
PlatformReader = Annotated[User, Depends(require_permissions("platform.read"))]
PlatformCreator = Annotated[User, Depends(require_permissions("platform.create"))]
PlatformEditor = Annotated[User, Depends(require_permissions("platform.update"))]
PlatformArchiver = Annotated[User, Depends(require_permissions("platform.archive"))]
logger = logging.getLogger("micepp.platforms")


async def attach_platform_counts(db: AsyncSession, platforms: list[Platform]) -> None:
    ids = [platform.id for platform in platforms]
    if not ids:
        return
    service_rows = await db.execute(
        select(Service.platform_id, func.count(Service.id))
        .where(Service.platform_id.in_(ids), Service.archived_at.is_(None))
        .group_by(Service.platform_id)
    )
    threat_rows = await db.execute(
        # One threatened service counts as one threat, regardless of its CVE count.
        select(Service.platform_id, func.count(func.distinct(Service.id)))
        .join(ServiceVulnerability, ServiceVulnerability.service_id == Service.id)
        .where(
            Service.platform_id.in_(ids),
            Service.archived_at.is_(None),
            ServiceVulnerability.resolved_at.is_(None),
            ServiceVulnerability.ignored_at.is_(None),
            ServiceVulnerability.match_state.in_(("confirmed", "probable")),
        )
        .group_by(Service.platform_id)
    )
    service_counts = dict(service_rows.all())
    threat_counts = dict(threat_rows.all())
    for platform in platforms:
        platform.service_count = int(service_counts.get(platform.id, 0))
        platform.threat_count = int(threat_counts.get(platform.id, 0))


def normalized_target(
    target_type: PlatformTargetType | str, target_value: str | None
) -> tuple[str | None, str | None]:
    try:
        return normalize_platform_target(target_type, target_value)
    except InvalidPlatformTarget as exc:
        raise AppError(422, "PLATFORM_TARGET_INVALID", str(exc)) from exc


def require_platform(platform: Platform | None) -> Platform:
    if platform is None:
        raise AppError(404, "PLATFORM_NOT_FOUND", "La plateforme demandée est introuvable.")
    return platform


@router.get("", response_model=PlatformListResponse)
async def platforms_index(
    db: DBSession,
    _user: PlatformReader,
    q: str | None = Query(default=None, max_length=200),
    target_type: PlatformTargetType | None = None,
    include_archived: bool = False,
    sort: PlatformSort = "-created_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
) -> PlatformListResponse:
    items, total = await list_platforms(
        db,
        q=q,
        target_type=target_type,
        include_archived=include_archived,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    await attach_platform_counts(db, items)
    return PlatformListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=PlatformResponse, status_code=status.HTTP_201_CREATED)
async def platforms_create(
    payload: PlatformCreate,
    request: Request,
    db: DBSession,
    user: PlatformCreator,
) -> Platform:
    target_value, normalized = normalized_target(payload.target_type, payload.target_value)
    platform = Platform(
        name=payload.name,
        target_type=payload.target_type.value,
        target_value=target_value,
        normalized_target=normalized,
        description=payload.description,
        created_by=user.id,
    )
    db.add(platform)
    await db.flush()
    record_audit(
        db,
        actor_user_id=user.id,
        action="platform.create",
        entity_type="platform",
        entity_id=platform.id,
        platform_id=platform.id,
        summary=f"Plateforme créée : {platform.name}",
        after_data={"name": platform.name, "target_type": platform.target_type},
        **request_audit_context(request),
    )
    await db.commit()
    await db.refresh(platform)
    logger.info(
        "platform_created",
        extra={"user_id": str(user.id), "action": "platform.create", "result": "succeeded"},
    )
    return platform


@router.get("/{platform_id}", response_model=PlatformResponse)
async def platforms_show(
    platform_id: UUID,
    db: DBSession,
    _user: PlatformReader,
) -> Platform:
    platform = require_platform(await get_platform(db, platform_id))
    await attach_platform_counts(db, [platform])
    return platform


@router.patch("/{platform_id}", response_model=PlatformResponse)
async def platforms_update(
    platform_id: UUID,
    payload: PlatformUpdate,
    request: Request,
    db: DBSession,
    user: PlatformEditor,
) -> Platform:
    platform = require_platform(await get_platform(db, platform_id))
    if platform.archived_at:
        raise AppError(409, "PLATFORM_ARCHIVED", "Cette plateforme a été supprimée.")
    before = {
        "name": platform.name,
        "target_type": platform.target_type,
        "target_value": platform.target_value,
        "description": platform.description,
    }
    fields = payload.model_fields_set
    target_type = payload.target_type or PlatformTargetType(platform.target_type)
    target_value_input = payload.target_value if "target_value" in fields else platform.target_value
    if "target_type" in fields or "target_value" in fields:
        target_value, normalized = normalized_target(target_type, target_value_input)
        platform.target_type = target_type.value
        platform.target_value = target_value
        platform.normalized_target = normalized
    if "name" in fields and payload.name is not None:
        platform.name = payload.name
    if "description" in fields:
        platform.description = payload.description
    after = {
        "name": platform.name,
        "target_type": platform.target_type,
        "target_value": platform.target_value,
        "description": platform.description,
    }
    record_audit(
        db,
        actor_user_id=user.id,
        action="platform.update",
        entity_type="platform",
        entity_id=platform.id,
        platform_id=platform.id,
        summary=f"Plateforme modifiée : {platform.name}",
        before_data=before,
        after_data=after,
        **request_audit_context(request),
    )
    await db.commit()
    await db.refresh(platform)
    logger.info(
        "platform_updated",
        extra={"user_id": str(user.id), "action": "platform.update", "result": "succeeded"},
    )
    return platform


@router.delete("/{platform_id}", response_model=PlatformResponse)
async def platforms_archive(
    platform_id: UUID,
    request: Request,
    db: DBSession,
    user: PlatformArchiver,
) -> Platform:
    platform = require_platform(await get_platform(db, platform_id))
    if platform.archived_at is None:
        platform.archived_at = datetime.now(UTC)
        record_audit(
            db,
            actor_user_id=user.id,
            action="platform.archive",
            entity_type="platform",
            entity_id=platform.id,
            platform_id=platform.id,
            summary=f"Plateforme supprimée : {platform.name}",
            before_data={"archived_at": None},
            after_data={"archived_at": platform.archived_at.isoformat()},
            **request_audit_context(request),
        )
        await db.commit()
        await db.refresh(platform)
        logger.info(
            "platform_archived",
            extra={"user_id": str(user.id), "action": "platform.archive", "result": "succeeded"},
        )
    return platform
