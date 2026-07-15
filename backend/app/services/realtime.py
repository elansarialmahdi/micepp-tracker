from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.models.realtime import ProtectionJob, RealtimeProtectionSetting
from app.models.service import Service
from app.services.audit import record_audit
from app.services.vulnerabilities import check_service

LOCK_KEY = "micepp:realtime-protection:global-lock"


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or UTC)


async def get_or_create_settings(db: AsyncSession, settings: Settings) -> RealtimeProtectionSetting:
    item = await db.scalar(
        select(RealtimeProtectionSetting).where(RealtimeProtectionSetting.setting_key == "global")
    )
    if item is None:
        item = RealtimeProtectionSetting(
            setting_key="global",
            enabled=False,
            interval_seconds=max(
                settings.realtime_default_interval_seconds,
                settings.realtime_min_interval_seconds,
            ),
            batch_size=settings.realtime_batch_size,
            max_concurrency=settings.realtime_max_concurrency,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
    return item


async def active_job(db: AsyncSession) -> ProtectionJob | None:
    return await db.scalar(
        select(ProtectionJob)
        .where(ProtectionJob.status.in_(["queued", "running"]))
        .order_by(ProtectionJob.created_at.desc())
    )


async def latest_job(db: AsyncSession) -> ProtectionJob | None:
    return await db.scalar(select(ProtectionJob).order_by(ProtectionJob.created_at.desc()).limit(1))


def stale_job_after_seconds(job: ProtectionJob, settings: Settings) -> int:
    if job.status == "queued" and job.started_at is None:
        return max(60, settings.realtime_scheduler_poll_seconds * 2)
    return max(180, settings.realtime_scheduler_poll_seconds * 3)


async def recover_stale_job(
    db: AsyncSession,
    settings: Settings,
    redis: Redis | None = None,
) -> None:
    job = await active_job(db)
    if job is None:
        if redis is not None and await redis.get(LOCK_KEY) is not None:
            await redis.delete(LOCK_KEY)
        return
    activity = aware(job.heartbeat_at or job.started_at or job.created_at)
    stale_before = datetime.now(UTC) - timedelta(
        seconds=stale_job_after_seconds(job, settings)
    )
    if activity and activity < stale_before:
        job.status = "failed"
        job.completed_at = datetime.now(UTC)
        job.error_summary = [
            {
                "code": "PROTECTION_WORKER_INTERRUPTED",
                "message": "La vérification interrompue peut être relancée.",
            }
        ]
        await db.commit()
        if redis is not None:
            # A stopped worker cannot release its lock in the normal finally block.
            await redis.delete(LOCK_KEY)


async def acquire_lock(redis: Redis, settings: Settings) -> str | None:
    token = secrets.token_urlsafe(24)
    acquired = await redis.set(
        LOCK_KEY,
        token,
        ex=settings.realtime_lock_ttl_seconds,
        nx=True,
    )
    return token if acquired else None


async def release_lock(redis: Redis, token: str) -> None:
    if await redis.get(LOCK_KEY) == token:
        await redis.delete(LOCK_KEY)


async def refresh_lock(redis: Redis, token: str, settings: Settings) -> None:
    if await redis.get(LOCK_KEY) != token:
        raise RuntimeError("Le verrou distribué de protection a été perdu.")
    await redis.expire(LOCK_KEY, settings.realtime_lock_ttl_seconds)


async def execute_protection_job(
    db: AsyncSession,
    redis: Redis,
    job: ProtectionJob,
    settings: Settings,
) -> ProtectionJob:
    job_id = job.id
    if job.status in {"succeeded", "partial", "failed", "skipped"}:
        return job
    token = await acquire_lock(redis, settings)
    if token is None:
        job.status = "skipped"
        job.completed_at = datetime.now(UTC)
        job.error_summary = [
            {"code": "GLOBAL_LOCK_BUSY", "message": "Une exécution est déjà active."}
        ]
        await db.commit()
        return job
    now = datetime.now(UTC)
    try:
        protection = await get_or_create_settings(db, settings)
        batch_size = protection.batch_size
        job.status = "running"
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.total_services = int(
            await db.scalar(select(func.count(Service.id)).where(Service.archived_at.is_(None)))
            or 0
        )
        job.processed_services = 0
        job.succeeded_services = 0
        job.failed_services = 0
        job.new_notifications = 0
        job.error_summary = []
        await db.commit()

        last_id = None
        batch_number = 0
        processed = succeeded = failed = notifications = 0
        errors: list[dict[str, Any]] = []
        session_factory = async_sessionmaker(db.bind, expire_on_commit=False, autoflush=False)
        concurrency = max(1, min(protection.max_concurrency, 10))
        semaphore = asyncio.Semaphore(concurrency)

        async def check_with_retry(service_id: Any) -> tuple[bool, int, str | None]:
            async with semaphore:
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        async with session_factory() as service_db:
                            service = await service_db.scalar(
                                select(Service)
                                .where(Service.id == service_id, Service.archived_at.is_(None))
                                .options(selectinload(Service.platform))
                            )
                            if service is None:
                                return True, 0, None
                            result = await check_service(service_db, service, settings)
                            return True, int(result.get("new_notifications", 0)), None
                    except Exception as exc:
                        last_error = exc
                        if attempt < 2:
                            await asyncio.sleep(2**attempt)
                return False, 0, str(last_error)[:200] if last_error else "Erreur inconnue"

        while True:
            statement = (
                select(Service)
                .where(Service.archived_at.is_(None))
                .options(selectinload(Service.platform))
                .order_by(Service.id)
                .limit(batch_size)
            )
            if last_id is not None:
                statement = statement.where(Service.id > last_id)
            services = list((await db.scalars(statement)).all())
            if not services:
                break
            service_ids = [service.id for service in services]
            batch_last_id = service_ids[-1]
            await refresh_lock(redis, token, settings)
            batch_number += 1
            job.current_batch = batch_number
            async def checked_service(service_id: Any) -> tuple[Any, bool, int, str | None]:
                successful, new_notifications, error_message = await check_with_retry(
                    service_id
                )
                return service_id, successful, new_notifications, error_message

            pending = {
                asyncio.create_task(checked_service(service_id))
                for service_id in service_ids
            }
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    timeout=15,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    job = await db.get(ProtectionJob, job_id)
                    assert job is not None
                    job.heartbeat_at = datetime.now(UTC)
                    await db.commit()
                    await refresh_lock(redis, token, settings)
                    continue
                for completed in done:
                    (
                        service_id,
                        successful,
                        new_notifications,
                        error_message,
                    ) = await completed
                    if successful:
                        succeeded += 1
                        notifications += new_notifications
                    else:
                        failed += 1
                        if len(errors) < 50:
                            errors.append(
                                {
                                    "service_id": str(service_id),
                                    "code": "SERVICE_CHECK_FAILED",
                                    "message": error_message,
                                }
                            )
                    processed += 1
                    job = await db.get(ProtectionJob, job_id)
                    assert job is not None
                    job.processed_services = processed
                    job.succeeded_services = succeeded
                    job.failed_services = failed
                    job.new_notifications = notifications
                    job.error_summary = errors
                    job.current_batch = batch_number
                    job.heartbeat_at = datetime.now(UTC)
                    await db.commit()
            last_id = batch_last_id

        job.completed_at = datetime.now(UTC)
        if job.failed_services == 0:
            job.status = "succeeded"
        elif job.succeeded_services:
            job.status = "partial"
        else:
            job.status = "failed"
        protection = await get_or_create_settings(db, settings)
        protection.last_run_at = job.completed_at
        protection.next_run_at = (
            job.completed_at + timedelta(seconds=protection.interval_seconds)
            if protection.enabled
            else None
        )
        record_audit(
            db,
            action="realtime.run.complete",
            entity_type="protection_job",
            entity_id=job.id,
            summary=(
                f"Protection périodique : {job.succeeded_services} service(s) vérifié(s), "
                f"{job.failed_services} échec(s)"
            ),
            after_data={
                "status": job.status,
                "processed": job.processed_services,
                "new_notifications": job.new_notifications,
            },
        )
        await db.commit()
        return job
    except Exception:
        await db.rollback()
        job = await db.get(ProtectionJob, job_id)
        assert job is not None
        job.status = "failed"
        job.completed_at = datetime.now(UTC)
        job.error_summary = [
            {"code": "PROTECTION_JOB_FAILED", "message": "L’exécution globale a échoué."}
        ]
        await db.commit()
        raise
    finally:
        await release_lock(redis, token)


async def create_due_job(
    db: AsyncSession,
    settings: Settings,
    redis: Redis | None = None,
) -> ProtectionJob | None:
    protection = await get_or_create_settings(db, settings)
    now = datetime.now(UTC)
    if not protection.enabled or (
        aware(protection.next_run_at) and aware(protection.next_run_at) > now
    ):
        return None
    await recover_stale_job(db, settings, redis)
    active = await active_job(db)
    if active:
        return None
    slot = int(now.timestamp() // protection.interval_seconds)
    key = f"scheduled:{slot}"
    existing = await db.scalar(select(ProtectionJob).where(ProtectionJob.idempotency_key == key))
    if existing:
        return None
    total_services = int(
        await db.scalar(select(func.count(Service.id)).where(Service.archived_at.is_(None)))
        or 0
    )
    job = ProtectionJob(
        trigger="scheduled",
        status="queued",
        total_services=total_services,
        idempotency_key=key,
        error_summary=[],
    )
    db.add(job)
    protection.next_run_at = now + timedelta(seconds=protection.interval_seconds)
    await db.commit()
    await db.refresh(job)
    return job
