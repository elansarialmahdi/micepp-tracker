from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.schemas.health import ComponentHealth, ReadinessResponse


async def build_readiness(
    engine: AsyncEngine,
    redis_client: Redis,
    settings: Settings,
) -> ReadinessResponse:
    checks: dict[str, ComponentHealth] = {}

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        checks["postgresql"] = ComponentHealth(status="up")
        if revision == settings.expected_database_revision:
            checks["migrations"] = ComponentHealth(status="up")
        else:
            checks["migrations"] = ComponentHealth(
                status="down",
                detail="database revision is not current",
            )
    except Exception:
        checks["postgresql"] = ComponentHealth(status="down", detail="connection failed")
        checks["migrations"] = ComponentHealth(status="down", detail="revision unavailable")

    try:
        await redis_client.ping()
        checks["redis"] = ComponentHealth(status="up")
    except Exception:
        checks["redis"] = ComponentHealth(status="down", detail="connection failed")

    is_ready = all(check.status == "up" for check in checks.values())
    return ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
