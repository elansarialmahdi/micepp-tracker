import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.models.auth import User
from app.models.realtime import ProtectionJob, RealtimeProtectionSetting
from app.services.realtime import (
    LOCK_KEY,
    acquire_lock,
    create_due_job,
    execute_protection_job,
    recover_stale_job,
    release_lock,
)
from tests.conftest import AuthTestContext, FakeRedis


@dataclass
class RealtimeTestContext:
    client: TestClient
    headers: dict[str, str]
    settings: object


@pytest.fixture
def realtime_context(auth_context: AuthTestContext) -> RealtimeTestContext:
    async def enable_admin() -> UUID:
        engine = create_async_engine(auth_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            user = await db.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            user.must_change_password = False
            await db.commit()
            result = user.id
        await engine.dispose()
        return result

    user_id = asyncio.run(enable_admin())
    token, _ = create_access_token(user_id, auth_context.settings)
    headers = {"Authorization": f"Bearer {token}"}
    platform = auth_context.client.post(
        "/v1/platforms",
        headers=headers,
        json={"name": "Protection", "target_type": "none"},
    )
    for service in (
        {"name": "NGINX", "vendor": "F5", "product": "nginx", "version": "1.20.0"},
        {
            "name": "PostgreSQL",
            "vendor": "PostgreSQL",
            "product": "postgresql",
            "version": "16.0",
        },
    ):
        response = auth_context.client.post(
            f"/v1/platforms/{platform.json()['id']}/services",
            headers=headers,
            json=service,
        )
        assert response.status_code == 201
    return RealtimeTestContext(auth_context.client, headers, auth_context.settings)


def test_settings_countdown_source_and_manual_pipeline(
    realtime_context: RealtimeTestContext,
) -> None:
    initial = realtime_context.client.get(
        "/v1/settings/realtime-protection", headers=realtime_context.headers
    )
    assert initial.status_code == 200
    assert initial.json()["enabled"] is False

    configured = realtime_context.client.patch(
        "/v1/settings/realtime-protection",
        headers=realtime_context.headers,
        json={"enabled": True, "interval_seconds": 120, "batch_size": 1},
    )
    assert configured.status_code == 200
    assert configured.json()["next_run_at"] is not None

    run = realtime_context.client.post(
        "/v1/settings/realtime-protection/run-now", headers=realtime_context.headers
    )
    assert run.status_code == 202, run.text
    assert run.json()["status"] == "succeeded"
    assert run.json()["total_services"] == 2
    assert run.json()["processed_services"] == 2
    assert run.json()["current_batch"] == 2

    current = realtime_context.client.get(
        "/v1/settings/realtime-protection/current-job", headers=realtime_context.headers
    )
    assert current.status_code == 200
    assert current.json()["id"] == run.json()["id"]


def test_scheduler_is_idempotent_and_advances_next_run(
    realtime_context: RealtimeTestContext,
) -> None:
    async def schedule() -> tuple[ProtectionJob | None, ProtectionJob | None, int]:
        settings = realtime_context.settings
        engine = create_async_engine(settings.database_url)  # type: ignore[attr-defined]
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            item = RealtimeProtectionSetting(
                setting_key="global",
                enabled=True,
                interval_seconds=60,
                batch_size=25,
                max_concurrency=2,
                next_run_at=datetime.now(UTC) - timedelta(seconds=1),
            )
            db.add(item)
            await db.commit()
            first = await create_due_job(db, settings)  # type: ignore[arg-type]
            second = await create_due_job(db, settings)  # type: ignore[arg-type]
            jobs = len((await db.scalars(select(ProtectionJob))).all())
        await engine.dispose()
        return first, second, jobs

    first, second, jobs = asyncio.run(schedule())
    assert first is not None
    assert first.total_services == 2
    assert second is None
    assert jobs == 1


def test_distributed_lock_rejects_a_second_owner(
    realtime_context: RealtimeTestContext,
) -> None:
    async def lock() -> tuple[str | None, str | None, str | None]:
        redis = FakeRedis()
        settings = realtime_context.settings
        first = await acquire_lock(redis, settings)  # type: ignore[arg-type]
        second = await acquire_lock(redis, settings)  # type: ignore[arg-type]
        assert first is not None
        await release_lock(redis, first)  # type: ignore[arg-type]
        third = await acquire_lock(redis, settings)  # type: ignore[arg-type]
        return first, second, third

    first, second, third = asyncio.run(lock())
    assert first is not None
    assert second is None
    assert third is not None


def test_stale_queued_job_is_failed_quickly(
    realtime_context: RealtimeTestContext,
) -> None:
    async def recover() -> tuple[str, list, str | None]:
        settings = realtime_context.settings
        redis = FakeRedis()
        await redis.set(LOCK_KEY, "orphaned-worker", ex=3600, nx=True)
        engine = create_async_engine(settings.database_url)  # type: ignore[attr-defined]
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            job = ProtectionJob(
                trigger="scheduled",
                status="queued",
                created_at=datetime.now(UTC) - timedelta(minutes=5),
                error_summary=[],
            )
            db.add(job)
            await db.commit()
            await recover_stale_job(db, settings, redis)  # type: ignore[arg-type]
            await db.refresh(job)
            result = job.status, job.error_summary, await redis.get(LOCK_KEY)
        await engine.dispose()
        return result

    status, errors, lock = asyncio.run(recover())
    assert status == "failed"
    assert errors[0]["code"] == "PROTECTION_WORKER_INTERRUPTED"
    assert lock is None


def test_orphaned_lock_without_active_job_is_removed(
    realtime_context: RealtimeTestContext,
) -> None:
    async def recover() -> str | None:
        settings = realtime_context.settings
        redis = FakeRedis()
        await redis.set(LOCK_KEY, "orphaned-worker", ex=3600, nx=True)
        engine = create_async_engine(settings.database_url)  # type: ignore[attr-defined]
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            await recover_stale_job(db, settings, redis)  # type: ignore[arg-type]
        await engine.dispose()
        return await redis.get(LOCK_KEY)

    assert asyncio.run(recover()) is None


def test_pipeline_keeps_partial_progress_when_one_service_fails(
    realtime_context: RealtimeTestContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def simulated_check(_db, service, _settings):  # type: ignore[no-untyped-def]
        if service.name == "PostgreSQL":
            raise RuntimeError("NVD indisponible")
        return {"new_notifications": 1}

    monkeypatch.setattr("app.services.realtime.check_service", simulated_check)

    async def execute() -> ProtectionJob:
        settings = realtime_context.settings
        engine = create_async_engine(settings.database_url)  # type: ignore[attr-defined]
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            job = ProtectionJob(trigger="manual", status="queued", error_summary=[])
            db.add(job)
            await db.commit()
            result = await execute_protection_job(
                db,
                FakeRedis(),
                job,
                settings,  # type: ignore[arg-type]
            )
        await engine.dispose()
        return result

    job = asyncio.run(execute())
    assert job.status == "partial"
    assert job.processed_services == 2
    assert job.succeeded_services == 1
    assert job.failed_services == 1
    assert job.new_notifications == 1
    assert job.error_summary[0]["code"] == "SERVICE_CHECK_FAILED"
