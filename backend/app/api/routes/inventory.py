import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import delete, distinct, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_permissions
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.platform import Platform
from app.models.service import Category, Service, ServiceSource
from app.models.vulnerability import CPECandidate, ServiceVulnerability
from app.repositories.inventory import (
    find_duplicate_services,
    get_category,
    get_service,
    list_categories,
    list_services,
)
from app.repositories.platforms import get_platform
from app.schemas.service import (
    AICategorizationRequest,
    AICategorizationResponse,
    AICategorizationSuggestion,
    AICategorizationConfirmRequest,
    AICategorizationConfirmResponse,
    AICategorizationConfirmedItem,
    AICategorizationPreviewResponse,
    AICategorizationPreviewSuggestion,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ServiceBulkCreate,
    ServiceCreate,
    ServiceListResponse,
    ServiceResponse,
    ServiceSort,
    ServiceUpdate,
)
from app.services.audit import record_audit, request_audit_context
from app.services.automatic_checks import enqueue_service_checks
from app.services.categorization import (
    CategorizationFailed,
    CategorizationUnavailable,
    ServiceToCategorize,
    categorize_with_ai,
)
from app.services.inventory import normalized_name, normalized_version
from app.services.rate_limit import enforce_expensive_limit

router = APIRouter(prefix="/v1", tags=["inventory"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
ServiceReader = Annotated[User, Depends(require_permissions("service.read"))]
ServiceCreator = Annotated[User, Depends(require_permissions("service.create"))]
ServiceEditor = Annotated[User, Depends(require_permissions("service.update"))]
ServiceArchiver = Annotated[User, Depends(require_permissions("service.archive"))]
logger = logging.getLogger("micepp.inventory")


def required_platform(platform: Platform | None, *, active: bool = False) -> Platform:
    if platform is None:
        raise AppError(404, "PLATFORM_NOT_FOUND", "La plateforme demandée est introuvable.")
    if active and platform.archived_at is not None:
        raise AppError(409, "PLATFORM_ARCHIVED", "Cette plateforme a été supprimée.")
    return platform


def required_category(category: Category | None) -> Category:
    if category is None:
        raise AppError(404, "CATEGORY_NOT_FOUND", "La catégorie demandée est introuvable.")
    return category


def required_service(service: Service | None) -> Service:
    if service is None:
        raise AppError(404, "SERVICE_NOT_FOUND", "Le service demandé est introuvable.")
    return service


async def category_for_platform(
    db: AsyncSession, platform_id: UUID, category_id: UUID | None
) -> Category | None:
    if category_id is None:
        return None
    category = await get_category(db, category_id)
    if category is None or category.archived_at is not None:
        raise AppError(
            422,
            "CATEGORY_UNAVAILABLE",
            "La catégorie demandée n’est pas disponible.",
        )
    return category


@router.get("/platforms/{platform_id}/categories", response_model=list[CategoryResponse])
async def categories_index(
    platform_id: UUID,
    db: DBSession,
    _user: ServiceReader,
    used_only: bool = False,
) -> list[Category]:
    required_platform(await get_platform(db, platform_id))
    return await list_categories(db, platform_id, used_only=used_only)


@router.post(
    "/platforms/{platform_id}/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def categories_create(
    platform_id: UUID,
    payload: CategoryCreate,
    request: Request,
    db: DBSession,
    user: ServiceCreator,
) -> Category:
    required_platform(await get_platform(db, platform_id), active=True)
    category = Category(
        name=payload.name,
        normalized_name=normalized_name(payload.name),
        description=payload.description,
    )
    db.add(category)
    try:
        await db.flush()
        record_audit(
            db,
            actor_user_id=user.id,
            action="category.create",
            entity_type="category",
            entity_id=category.id,
            platform_id=platform_id,
            summary=f"Catégorie créée : {category.name}",
            after_data={"name": category.name, "description": category.description},
            **request_audit_context(request),
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(
            409,
            "CATEGORY_DUPLICATE",
            "Une catégorie portant ce nom existe déjà.",
        ) from exc
    await db.refresh(category)
    logger.info(
        "category_created",
        extra={"user_id": str(user.id), "action": "category.create", "result": "succeeded"},
    )
    return category


@router.post(
    "/platforms/{platform_id}/categories/ai-categorize/preview",
    response_model=AICategorizationPreviewResponse,
)
async def categories_ai_preview(
    platform_id: UUID,
    payload: AICategorizationRequest,
    request: Request,
    db: DBSession,
    user: ServiceCreator,
) -> AICategorizationPreviewResponse:
    required_platform(await get_platform(db, platform_id), active=True)
    settings = request.app.state.settings
    await enforce_expensive_limit(
        request,
        scope="ai-categorization",
        user_id=user.id,
        limit=settings.ai_categorization_rate_limit,
        window_seconds=settings.expensive_rate_window_seconds,
    )
    existing = await list_categories(db, platform_id)
    try:
        assignments = await categorize_with_ai(
            [
                ServiceToCategorize(
                    key=item.key,
                    name=item.name,
                    version=item.version,
                    vendor=item.vendor,
                    product=item.product,
                )
                for item in payload.items
            ],
            [category.name for category in existing],
            settings,
        )
    except CategorizationUnavailable as exc:
        raise AppError(503, "AI_CATEGORIZATION_UNAVAILABLE", str(exc)) from exc
    except CategorizationFailed as exc:
        raise AppError(502, "AI_CATEGORIZATION_FAILED", str(exc)) from exc

    existing_by_name = {category.normalized_name: category for category in existing}
    return AICategorizationPreviewResponse(
        items=[
            AICategorizationPreviewSuggestion(
                key=assignment.key,
                category_name=assignment.category_name,
                existing_category_id=(
                    existing_by_name[normalized_name(assignment.category_name)].id
                    if normalized_name(assignment.category_name) in existing_by_name
                    else None
                ),
                confidence=assignment.confidence,
                reason=assignment.reason,
            )
            for assignment in assignments
        ]
    )


@router.post(
    "/platforms/{platform_id}/categories/ai-categorize/confirm",
    response_model=AICategorizationConfirmResponse,
)
async def categories_ai_confirm(
    platform_id: UUID,
    payload: AICategorizationConfirmRequest,
    request: Request,
    db: DBSession,
    user: ServiceCreator,
) -> AICategorizationConfirmResponse:
    required_platform(await get_platform(db, platform_id), active=True)
    existing = await list_categories(db, platform_id)
    categories = {category.normalized_name: category for category in existing}
    confirmed: list[tuple[str, Category]] = []
    context = request_audit_context(request)
    for item in payload.items:
        if not item.selected:
            continue
        key = normalized_name(item.category_name)
        category = categories.get(key)
        if category is None:
            category = Category(
                name=item.category_name,
                normalized_name=key,
                description="Catégorie confirmée après suggestion IA.",
            )
            db.add(category)
            await db.flush()
            categories[key] = category
            record_audit(
                db,
                actor_user_id=user.id,
                action="category.create.ai.confirmed",
                entity_type="category",
                entity_id=category.id,
                platform_id=platform_id,
                summary=f"Catégorie IA confirmée : {category.name}",
                after_data={"name": category.name, "confirmed": True},
                **context,
            )
        confirmed.append((item.key, category))
    await db.commit()
    for _, category in confirmed:
        await db.refresh(category)
    return AICategorizationConfirmResponse(
        items=[
            AICategorizationConfirmedItem(key=key, category=category)
            for key, category in confirmed
        ]
    )


@router.post(
    "/platforms/{platform_id}/categories/ai-categorize",
    response_model=AICategorizationResponse,
)
async def categories_ai_categorize(
    platform_id: UUID,
    payload: AICategorizationRequest,
    request: Request,
    db: DBSession,
    user: ServiceCreator,
) -> AICategorizationResponse:
    required_platform(await get_platform(db, platform_id), active=True)
    settings = request.app.state.settings
    await enforce_expensive_limit(
        request,
        scope="ai-categorization",
        user_id=user.id,
        limit=settings.ai_categorization_rate_limit,
        window_seconds=settings.expensive_rate_window_seconds,
    )
    existing = await list_categories(db, platform_id)
    try:
        assignments = await categorize_with_ai(
            [
                ServiceToCategorize(
                    key=item.key,
                    name=item.name,
                    version=item.version,
                    vendor=item.vendor,
                    product=item.product,
                )
                for item in payload.items
            ],
            [category.name for category in existing],
            settings,
        )
    except CategorizationUnavailable as exc:
        raise AppError(503, "AI_CATEGORIZATION_UNAVAILABLE", str(exc)) from exc
    except CategorizationFailed as exc:
        raise AppError(502, "AI_CATEGORIZATION_FAILED", str(exc)) from exc

    categories = {category.normalized_name: category for category in existing}
    created_keys: set[str] = set()
    context = request_audit_context(request)
    for assignment in assignments:
        key = normalized_name(assignment.category_name)
        if key in categories:
            continue
        category = Category(
            name=assignment.category_name,
            normalized_name=key,
            description="Catégorie créée automatiquement par Gemini.",
        )
        db.add(category)
        categories[key] = category
        created_keys.add(key)
        await db.flush()
        record_audit(
            db,
            actor_user_id=user.id,
            action="category.create.ai",
            entity_type="category",
            entity_id=category.id,
            platform_id=platform_id,
            summary=f"Catégorie créée par IA : {category.name}",
            after_data={"name": category.name, "provider": "gemini"},
            **context,
        )
    await db.commit()
    for category in categories.values():
        await db.refresh(category)
    return AICategorizationResponse(
        items=[
            AICategorizationSuggestion(
                key=assignment.key,
                category=categories[normalized_name(assignment.category_name)],
                category_created=normalized_name(assignment.category_name) in created_keys,
                confidence=assignment.confidence,
                reason=assignment.reason,
            )
            for assignment in assignments
        ]
    )


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def categories_update(
    category_id: UUID,
    payload: CategoryUpdate,
    request: Request,
    db: DBSession,
    user: ServiceEditor,
) -> Category:
    category = required_category(await get_category(db, category_id))
    if category.archived_at:
        raise AppError(409, "CATEGORY_ARCHIVED", "Cette catégorie a été supprimée.")
    before = {"name": category.name, "description": category.description}
    if "name" in payload.model_fields_set and payload.name is not None:
        category.name = payload.name
        category.normalized_name = normalized_name(payload.name)
    if "description" in payload.model_fields_set:
        category.description = payload.description
    record_audit(
        db,
        actor_user_id=user.id,
        action="category.update",
        entity_type="category",
        entity_id=category.id,
        platform_id=None,
        summary=f"Catégorie modifiée : {category.name}",
        before_data=before,
        after_data={"name": category.name, "description": category.description},
        **request_audit_context(request),
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "CATEGORY_DUPLICATE", "Cette catégorie existe déjà.") from exc
    await db.refresh(category)
    logger.info(
        "category_updated",
        extra={"user_id": str(user.id), "action": "category.update", "result": "succeeded"},
    )
    return category


@router.delete("/categories/{category_id}", response_model=CategoryResponse)
async def categories_archive(
    category_id: UUID,
    request: Request,
    db: DBSession,
    user: ServiceArchiver,
) -> Category:
    category = required_category(await get_category(db, category_id))
    if category.archived_at is None:
        category.archived_at = datetime.now(UTC)
        record_audit(
            db,
            actor_user_id=user.id,
            action="category.archive",
            entity_type="category",
            entity_id=category.id,
            platform_id=None,
            summary=f"Catégorie supprimée : {category.name}",
            after_data={"archived_at": category.archived_at.isoformat()},
            **request_audit_context(request),
        )
        await db.commit()
        await db.refresh(category)
        logger.info(
            "category_archived",
            extra={"user_id": str(user.id), "action": "category.archive", "result": "succeeded"},
        )
    return category


@router.get("/platforms/{platform_id}/services", response_model=ServiceListResponse)
async def services_index(
    platform_id: UUID,
    db: DBSession,
    _user: ServiceReader,
    q: str | None = Query(default=None, max_length=300),
    category_id: UUID | None = None,
    uncategorized: bool = False,
    include_archived: bool = False,
    vulnerable: bool | None = None,
    sort: ServiceSort = "name",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ServiceListResponse:
    required_platform(await get_platform(db, platform_id))
    if category_id:
        await category_for_platform(db, platform_id, category_id)
    items, total = await list_services(
        db,
        platform_id=platform_id,
        q=q,
        category_id=category_id,
        uncategorized=uncategorized,
        include_archived=include_archived,
        vulnerable=vulnerable,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    item_ids = [item.id for item in items]
    if item_ids:
        rows = await db.execute(
            select(ServiceVulnerability.service_id, func.count(ServiceVulnerability.id))
            .where(
                ServiceVulnerability.service_id.in_(item_ids),
                ServiceVulnerability.resolved_at.is_(None),
                ServiceVulnerability.ignored_at.is_(None),
                ServiceVulnerability.match_state.in_(("confirmed", "probable")),
            )
            .group_by(ServiceVulnerability.service_id)
        )
        counts = dict(rows.all())
        for item in items:
            item.active_vulnerability_count = int(counts.get(item.id, 0))
    vulnerable_total = int(
        (
            await db.scalar(
                select(func.count(distinct(Service.id)))
                .join(ServiceVulnerability, ServiceVulnerability.service_id == Service.id)
                .where(
                    Service.platform_id == platform_id,
                    Service.archived_at.is_(None),
                    ServiceVulnerability.resolved_at.is_(None),
                    ServiceVulnerability.ignored_at.is_(None),
                    ServiceVulnerability.match_state.in_(("confirmed", "probable")),
                )
            )
        )
        or 0
    )
    checked_services = int(
        (
            await db.scalar(
                select(func.count(Service.id)).where(
                    Service.platform_id == platform_id,
                    Service.archived_at.is_(None),
                    Service.last_checked_at.is_not(None),
                )
            )
        )
        or 0
    )
    all_services = int(
        (
            await db.scalar(
                select(func.count(Service.id)).where(
                    Service.platform_id == platform_id, Service.archived_at.is_(None)
                )
            )
        )
        or 0
    )
    return ServiceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        vulnerable_total=vulnerable_total,
        safe_total=max(0, checked_services - vulnerable_total),
        unverified_total=max(0, all_services - checked_services),
    )


async def create_services(
    db: AsyncSession,
    platform_id: UUID,
    items: list[ServiceCreate],
    user: User,
    request: Request,
) -> list[Service]:
    required_platform(await get_platform(db, platform_id), active=True)
    categories: dict[UUID, Category] = {}
    for category_id in {item.category_id for item in items if item.category_id}:
        category = await category_for_platform(db, platform_id, category_id)
        assert category is not None
        categories[category_id] = category

    keys = {(normalized_name(item.name), normalized_version(item.version)) for item in items}
    if len(keys) != len(items):
        raise AppError(409, "SERVICE_DUPLICATE", "Le formulaire contient des services en double.")
    duplicates = await find_duplicate_services(db, platform_id, keys)
    if duplicates:
        raise AppError(
            409,
            "SERVICE_DUPLICATE",
            "Un ou plusieurs services existent déjà sur cette plateforme.",
        )

    services = [
        Service(
            platform_id=platform_id,
            category_id=item.category_id,
            category=categories.get(item.category_id) if item.category_id else None,
            name=item.name,
            normalized_name=normalized_name(item.name),
            vendor=item.vendor,
            product=item.product,
            version=item.version,
            normalized_version=normalized_version(item.version),
            source=ServiceSource.MANUAL.value,
            source_details=None,
            created_by=user.id,
        )
        for item in items
    ]
    db.add_all(services)
    await db.flush()
    context = request_audit_context(request)
    for service in services:
        record_audit(
            db,
            actor_user_id=user.id,
            action="service.create",
            entity_type="service",
            entity_id=service.id,
            platform_id=platform_id,
            summary=f"Service créé : {service.name}",
            after_data={"name": service.name, "version": service.version},
            **context,
        )
    await db.commit()
    enqueue_service_checks([service.id for service in services], request.app.state.settings)
    logger.info(
        "services_created",
        extra={"user_id": str(user.id), "action": "service.create", "result": "succeeded"},
    )
    return services


@router.post(
    "/platforms/{platform_id}/services",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def services_create(
    platform_id: UUID,
    payload: ServiceCreate,
    request: Request,
    db: DBSession,
    user: ServiceCreator,
) -> Service:
    return (await create_services(db, platform_id, [payload], user, request))[0]


@router.post(
    "/platforms/{platform_id}/services/bulk",
    response_model=list[ServiceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def services_bulk_create(
    platform_id: UUID,
    payload: ServiceBulkCreate,
    request: Request,
    db: DBSession,
    user: ServiceCreator,
) -> list[Service]:
    return await create_services(db, platform_id, payload.items, user, request)


@router.get("/services/{service_id}", response_model=ServiceResponse)
async def services_show(
    service_id: UUID,
    db: DBSession,
    _user: ServiceReader,
) -> Service:
    return required_service(await get_service(db, service_id))


@router.patch("/services/{service_id}", response_model=ServiceResponse)
async def services_update(
    service_id: UUID,
    payload: ServiceUpdate,
    request: Request,
    db: DBSession,
    user: ServiceEditor,
) -> Service:
    service = required_service(await get_service(db, service_id))
    if service.archived_at:
        raise AppError(409, "SERVICE_ARCHIVED", "Ce service a été supprimé.")
    required_platform(await get_platform(db, service.platform_id), active=True)
    before = {
        "name": service.name,
        "version": service.version,
        "vendor": service.vendor,
        "product": service.product,
        "category_id": str(service.category_id) if service.category_id else None,
    }
    fields = payload.model_fields_set
    name = payload.name if "name" in fields and payload.name is not None else service.name
    version = payload.version if "version" in fields else service.version
    key = (normalized_name(name), normalized_version(version))
    if await find_duplicate_services(db, service.platform_id, {key}, exclude_id=service.id):
        raise AppError(409, "SERVICE_DUPLICATE", "Ce service existe déjà sur la plateforme.")
    if "category_id" in fields:
        category = await category_for_platform(db, service.platform_id, payload.category_id)
        service.category_id = payload.category_id
        service.category = category
    service.name = name
    for field in ("version", "vendor", "product"):
        if field in fields:
            setattr(service, field, getattr(payload, field))
    service.normalized_name = normalized_name(name)
    service.normalized_version = normalized_version(version)
    identity_changed = any(
        before[field] != getattr(service, field)
        for field in ("name", "version", "vendor", "product")
    )
    if identity_changed:
        service.cpe_uri = None
        service.cpe_match_confidence = None
        service.cpe_match_method = None
        service.last_checked_at = None
        await db.execute(
            update(ServiceVulnerability)
            .where(
                ServiceVulnerability.service_id == service.id,
                ServiceVulnerability.resolved_at.is_(None),
            )
            .values(resolved_at=datetime.now(UTC))
        )
        await db.execute(delete(CPECandidate).where(CPECandidate.service_id == service.id))
    record_audit(
        db,
        actor_user_id=user.id,
        action="service.update",
        entity_type="service",
        entity_id=service.id,
        platform_id=service.platform_id,
        summary=f"Service modifié : {service.name}",
        before_data=before,
        after_data={
            "name": service.name,
            "version": service.version,
            "vendor": service.vendor,
            "product": service.product,
            "category_id": str(service.category_id) if service.category_id else None,
        },
        **request_audit_context(request),
    )
    await db.commit()
    await db.refresh(service)
    await db.refresh(service, attribute_names=["category"])
    logger.info(
        "service_updated",
        extra={"user_id": str(user.id), "action": "service.update", "result": "succeeded"},
    )
    return service


@router.delete("/services/{service_id}", response_model=ServiceResponse)
async def services_archive(
    service_id: UUID,
    request: Request,
    db: DBSession,
    user: ServiceArchiver,
) -> Service:
    service = required_service(await get_service(db, service_id))
    if service.archived_at is None:
        service.archived_at = datetime.now(UTC)
        record_audit(
            db,
            actor_user_id=user.id,
            action="service.archive",
            entity_type="service",
            entity_id=service.id,
            platform_id=service.platform_id,
            summary=f"Service supprimé : {service.name}",
            after_data={"archived_at": service.archived_at.isoformat()},
            **request_audit_context(request),
        )
        await db.commit()
        await db.refresh(service)
        await db.refresh(service, attribute_names=["category"])
        logger.info(
            "service_archived",
            extra={"user_id": str(user.id), "action": "service.archive", "result": "succeeded"},
        )
    return service
