from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.routes.auth import dashboard_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.imports import router as imports_router
from app.api.routes.inventory import router as inventory_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.platforms import router as platforms_router
from app.api.routes.realtime import router as realtime_router
from app.api.routes.scans import router as scans_router
from app.api.routes.vulnerabilities import router as vulnerabilities_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError, app_error_handler, validation_error_handler
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import create_database_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.app_log_level, resolved_settings.app_env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.database_engine = create_database_engine(resolved_settings)
        app.state.session_factory = create_session_factory(app.state.database_engine)
        app.state.redis = Redis.from_url(resolved_settings.redis_url, decode_responses=True)
        yield
        await app.state.redis.aclose()
        await app.state.database_engine.dispose()

    docs_enabled = resolved_settings.app_env != "production"
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(platforms_router)
    app.include_router(realtime_router)
    app.include_router(scans_router)
    app.include_router(vulnerabilities_router)
    app.include_router(inventory_router)
    app.include_router(imports_router)
    app.include_router(notifications_router)
    return app


app = create_app()
