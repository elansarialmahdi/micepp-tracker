from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_permissions
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.realtime import ProtectionJob, RealtimeProtectionSetting
from app.models.service import Service
from app.schemas.realtime import (
    ProtectionJobResponse,
    RealtimeSettingsResponse,
    RealtimeSettingsUpdate,
)
from app.services.audit import record_audit, request_audit_context
from app.services.rate_limit import enforce_expensive_limit
from app.services.realtime import (
    active_job,
    execute_protection_job,
    get_or_create_settings,
    latest_job,
    recover_stale_job,
)

router = APIRouter(prefix="/v1/settings/realtime-protection", tags=["realtime-protection"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
Reader = Annotated[User, Depends(require_permissions("settings.read"))]
Editor = Annotated[User, Depends(require_permissions("settings.update"))]


def settings_response(item: RealtimeProtectionSetting, minimum: int) -> RealtimeSettingsResponse:
    return RealtimeSettingsResponse(
        enabled=item.enabled,
        interval_seconds=item.interval_seconds,
        batch_size=item.batch_size,
        max_concurrency=item.max_concurrency,
        min_interval_seconds=minimum,
        last_run_at=item.last_run_at,
        next_run_at=item.next_run_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=RealtimeSettingsResponse)
async def show_settings(request: Request, db: DBSession, _user: Reader) -> RealtimeSettingsResponse:
    settings = request.app.state.settings
    item = await get_or_create_settings(db, settings)
    return settings_response(item, settings.realtime_min_interval_seconds)


@router.patch("", response_model=RealtimeSettingsResponse)
async def update_settings(
    payload: RealtimeSettingsUpdate,
    request: Request,
    db: DBSession,
    user: Editor,
) -> RealtimeSettingsResponse:
    settings = request.app.state.settings
    item = await get_or_create_settings(db, settings)
    if (
        payload.interval_seconds is not None
        and payload.interval_seconds < settings.realtime_min_interval_seconds
    ):
        raise AppError(
            422,
            "REALTIME_INTERVAL_TOO_SHORT",
            f"L’intervalle minimal est de {settings.realtime_min_interval_seconds} secondes.",
        )
    before = {
        "enabled": item.enabled,
        "interval_seconds": item.interval_seconds,
        "batch_size": item.batch_size,
        "max_concurrency": item.max_concurrency,
    }
    for field in ("enabled", "interval_seconds", "batch_size", "max_concurrency"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)
    item.updated_by = user.id
    item.next_run_at = (
        datetime.now(UTC) + timedelta(seconds=item.interval_seconds) if item.enabled else None
    )
    record_audit(
        db,
        actor_user_id=user.id,
        action="realtime.settings.update",
        entity_type="realtime_protection",
        entity_id=item.id,
        summary=(
            "Protection en temps réel activée"
            if item.enabled
            else "Protection en temps réel désactivée"
        ),
        before_data=before,
        after_data={
            "enabled": item.enabled,
            "interval_seconds": item.interval_seconds,
            "batch_size": item.batch_size,
            "max_concurrency": item.max_concurrency,
        },
        **request_audit_context(request),
    )
    await db.commit()
    await db.refresh(item)
    return settings_response(item, settings.realtime_min_interval_seconds)


@router.post(
    "/run-now",
    response_model=ProtectionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_now(request: Request, db: DBSession, user: Editor) -> ProtectionJob:
    settings = request.app.state.settings
    await recover_stale_job(db, settings)
    await enforce_expensive_limit(
        request,
        scope="realtime-run",
        user_id=user.id,
        limit=settings.realtime_run_rate_limit,
        window_seconds=settings.expensive_rate_window_seconds,
    )
    if await active_job(db):
        raise AppError(
            409,
            "PROTECTION_ALREADY_RUNNING",
            "Une vérification globale est déjà en cours.",
        )
    job = ProtectionJob(
        trigger="manual",
        requested_by=user.id,
        status="queued",
        idempotency_key=f"manual:{request.state.request_id}",
        error_summary=[],
    )
    db.add(job)
    await db.flush()
    record_audit(
        db,
        actor_user_id=user.id,
        action="realtime.run.request",
        entity_type="protection_job",
        entity_id=job.id,
        summary="Vérification globale demandée manuellement",
        **request_audit_context(request),
    )
    await db.commit()
    if settings.app_env == "test" or settings.realtime_tasks_eager:
        await execute_protection_job(db, request.app.state.redis, job, settings)
    else:
        from app.worker import execute_protection_task

        try:
            execute_protection_task.delay(str(job.id))
        except Exception as exc:
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_summary = [
                {
                    "code": "PROTECTION_QUEUE_UNAVAILABLE",
                    "message": "Le worker est temporairement indisponible.",
                }
            ]
            await db.commit()
            raise AppError(
                503,
                "PROTECTION_QUEUE_UNAVAILABLE",
                "Le worker de protection est indisponible.",
            ) from exc
    await db.refresh(job)
    return job


@router.get("/current-job", response_model=ProtectionJobResponse | None)
async def current_job(
    request: Request,
    db: DBSession,
    _user: Reader,
) -> ProtectionJobResponse | None:
    await recover_stale_job(db, request.app.state.settings)
    job = await latest_job(db)
    if job is None:
        return None
    current_service_names: list[str] = []
    if job.status == "running" and job.current_batch > 0:
        protection = await get_or_create_settings(db, request.app.state.settings)
        offset = (job.current_batch - 1) * protection.batch_size
        current_service_names = list(
            (
                await db.scalars(
                    select(Service.name)
                    .where(Service.archived_at.is_(None))
                    .order_by(Service.id)
                    .offset(offset)
                    .limit(protection.batch_size)
                )
            ).all()
        )
    return ProtectionJobResponse.model_validate(job).model_copy(
        update={"current_service_names": current_service_names}
    )
