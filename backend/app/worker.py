import asyncio
from uuid import UUID

from celery import Celery
from redis.asyncio import Redis

from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.services.scans import execute_scan

settings = get_settings()
celery_app = Celery("micepp-scanner", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=settings.max_scan_duration_seconds,
    worker_concurrency=2,
    task_routes={
        "micepp.execute_scan": {"queue": "scans"},
        "micepp.execute_protection": {"queue": "protection"},
        "micepp.check_service": {"queue": "protection"},
        "micepp.realtime_scheduler_tick": {"queue": "protection"},
    },
    beat_schedule={
        "realtime-protection-due-check": {
            "task": "micepp.realtime_scheduler_tick",
            "schedule": settings.realtime_scheduler_poll_seconds,
        }
    },
)


async def _run(scan_job_id: UUID) -> None:
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as db:
            from app.models.scan import ScanJob

            job = await db.get(ScanJob, scan_job_id)
            if job is not None and job.status == "queued":
                await execute_scan(db, job, settings)
    finally:
        await engine.dispose()


@celery_app.task(name="micepp.execute_scan")
def execute_scan_task(scan_job_id: str) -> None:
    asyncio.run(_run(UUID(scan_job_id)))


async def _run_service_check(service_id: UUID) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.service import Service
    from app.services.vulnerabilities import check_service

    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as db:
            service = await db.scalar(
                select(Service)
                .where(Service.id == service_id, Service.archived_at.is_(None))
                .options(selectinload(Service.platform))
            )
            if service is not None:
                await check_service(db, service, settings)
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="micepp.check_service",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def check_service_task(_task, service_id: str) -> None:  # type: ignore[no-untyped-def]
    asyncio.run(_run_service_check(UUID(service_id)))


async def _run_protection(job_id: UUID) -> None:
    from app.models.realtime import ProtectionJob
    from app.services.realtime import execute_protection_job

    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with factory() as db:
            job = await db.get(ProtectionJob, job_id)
            if job is not None:
                if job.status == "failed" and job.retry_count < 3:
                    job.status = "queued"
                    job.retry_count += 1
                    await db.commit()
                await execute_protection_job(db, redis, job, settings)
    finally:
        await redis.aclose()
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="micepp.execute_protection",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def execute_protection_task(_task, job_id: str) -> None:  # type: ignore[no-untyped-def]
    asyncio.run(_run_protection(UUID(job_id)))


async def _scheduler_tick() -> None:
    from app.services.realtime import create_due_job

    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as db:
            job = await create_due_job(db, settings)
            if job is not None:
                execute_protection_task.delay(str(job.id))
    finally:
        await engine.dispose()


@celery_app.task(name="micepp.realtime_scheduler_tick")
def realtime_scheduler_tick_task() -> None:
    asyncio.run(_scheduler_tick())
