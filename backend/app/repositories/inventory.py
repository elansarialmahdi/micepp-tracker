from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.service import Category, Service
from app.models.vulnerability import ServiceVulnerability
from app.schemas.service import ServiceSort


async def list_categories(
    db: AsyncSession, platform_id: UUID, *, used_only: bool = False
) -> list[Category]:
    statement = select(Category).where(Category.archived_at.is_(None))
    if used_only:
        category_is_used = exists(
            select(Service.id).where(
                Service.category_id == Category.id,
                Service.platform_id == platform_id,
                Service.archived_at.is_(None),
            )
        )
        statement = statement.where(category_is_used)
    statement = statement.order_by(Category.normalized_name, Category.id)
    return list((await db.scalars(statement)).all())


async def get_category(db: AsyncSession, category_id: UUID) -> Category | None:
    return await db.get(Category, category_id)


def _service_filters(
    statement: Select,  # type: ignore[type-arg]
    platform_id: UUID,
    q: str | None,
    category_id: UUID | None,
    uncategorized: bool,
    include_archived: bool,
    vulnerable: bool | None = None,
) -> Select:  # type: ignore[type-arg]
    statement = statement.where(Service.platform_id == platform_id)
    if not include_archived:
        statement = statement.where(Service.archived_at.is_(None))
    if q:
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(
                Service.name.ilike(pattern, escape="\\"),
                Service.version.ilike(pattern, escape="\\"),
                Service.vendor.ilike(pattern, escape="\\"),
                Service.product.ilike(pattern, escape="\\"),
            )
        )
    if uncategorized:
        statement = statement.where(Service.category_id.is_(None))
    elif category_id:
        statement = statement.where(Service.category_id == category_id)
    active_vulnerability = exists(
        select(ServiceVulnerability.id).where(
            ServiceVulnerability.service_id == Service.id,
            ServiceVulnerability.resolved_at.is_(None),
            ServiceVulnerability.ignored_at.is_(None),
            ServiceVulnerability.match_state.in_(("confirmed", "probable")),
        )
    )
    if vulnerable is True:
        statement = statement.where(active_vulnerability)
    elif vulnerable is False:
        statement = statement.where(~active_vulnerability)
    return statement


async def list_services(
    db: AsyncSession,
    *,
    platform_id: UUID,
    q: str | None,
    category_id: UUID | None,
    uncategorized: bool,
    include_archived: bool,
    vulnerable: bool | None,
    sort: ServiceSort,
    page: int,
    page_size: int,
) -> tuple[list[Service], int]:
    filtered = _service_filters(
        select(Service).options(selectinload(Service.category)),
        platform_id,
        q,
        category_id,
        uncategorized,
        include_archived,
        vulnerable,
    )
    count_statement = _service_filters(
        select(func.count(Service.id)),
        platform_id,
        q,
        category_id,
        uncategorized,
        include_archived,
        vulnerable,
    )
    ordering = {
        "name": Service.normalized_name.asc(),
        "-name": Service.normalized_name.desc(),
        "created_at": Service.created_at.asc(),
        "-created_at": Service.created_at.desc(),
        "version": Service.normalized_version.asc().nulls_last(),
        "-version": Service.normalized_version.desc().nulls_last(),
    }
    statement = (
        filtered.order_by(ordering[sort], Service.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.scalars(statement)).all())
    total = int((await db.scalar(count_statement)) or 0)
    return items, total


async def get_service(db: AsyncSession, service_id: UUID) -> Service | None:
    statement = (
        select(Service).where(Service.id == service_id).options(selectinload(Service.category))
    )
    return (await db.scalars(statement)).one_or_none()


async def find_duplicate_services(
    db: AsyncSession,
    platform_id: UUID,
    keys: set[tuple[str, str | None]],
    exclude_id: UUID | None = None,
) -> set[tuple[str, str | None]]:
    if not keys:
        return set()
    names = {name for name, _ in keys}
    statement = select(Service).where(
        Service.platform_id == platform_id,
        Service.archived_at.is_(None),
        Service.normalized_name.in_(names),
    )
    if exclude_id:
        statement = statement.where(Service.id != exclude_id)
    existing = (await db.scalars(statement)).all()
    return {
        (service.normalized_name, service.normalized_version)
        for service in existing
        if (service.normalized_name, service.normalized_version) in keys
    }
