from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import Platform, PlatformTargetType
from app.schemas.platform import PlatformSort


def _apply_filters(
    statement: Select,  # type: ignore[type-arg]
    q: str | None,
    target_type: PlatformTargetType | None,
    include_archived: bool,
) -> Select:  # type: ignore[type-arg]
    if not include_archived:
        statement = statement.where(Platform.archived_at.is_(None))
    if q:
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            Platform.name.ilike(pattern, escape="\\")
            | Platform.normalized_target.ilike(pattern, escape="\\")
        )
    if target_type:
        statement = statement.where(Platform.target_type == target_type.value)
    return statement


async def list_platforms(
    db: AsyncSession,
    *,
    q: str | None,
    target_type: PlatformTargetType | None,
    include_archived: bool,
    sort: PlatformSort,
    page: int,
    page_size: int,
) -> tuple[list[Platform], int]:
    filtered = _apply_filters(select(Platform), q, target_type, include_archived)
    count_statement = _apply_filters(
        select(func.count(Platform.id)), q, target_type, include_archived
    )
    sort_columns = {
        "created_at": Platform.created_at.asc(),
        "-created_at": Platform.created_at.desc(),
        "name": Platform.name.asc(),
        "-name": Platform.name.desc(),
    }
    statement = (
        filtered.order_by(sort_columns[sort], Platform.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.scalars(statement)).all())
    total = int((await db.scalar(count_statement)) or 0)
    return items, total


async def get_platform(db: AsyncSession, platform_id: UUID) -> Platform | None:
    return await db.get(Platform, platform_id)
