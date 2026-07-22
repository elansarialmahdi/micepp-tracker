import asyncio
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import create_access_token, hash_password
from app.models.auth import Role, User
from app.models.notification import AuditEvent, Notification
from tests.conftest import AuthTestContext


@dataclass
class PhaseFiveContext:
    client: TestClient
    settings: Settings
    headers: dict[str, str]
    user_id: UUID


@pytest.fixture
def phase_five_context(auth_context: AuthTestContext) -> PhaseFiveContext:
    async def enable_admin() -> UUID:
        engine = create_async_engine(auth_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            user = await db.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            user.must_change_password = False
            await db.commit()
            return user.id

    user_id = asyncio.run(enable_admin())
    token, _ = create_access_token(user_id, auth_context.settings)
    return PhaseFiveContext(
        client=auth_context.client,
        settings=auth_context.settings,
        headers={"Authorization": f"Bearer {token}"},
        user_id=user_id,
    )


def test_notification_read_and_hide_preserve_source_row(
    phase_five_context: PhaseFiveContext,
) -> None:
    async def seed() -> UUID:
        engine = create_async_engine(phase_five_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            notification = Notification(
                type="scan.completed",
                title="Analyse terminée",
                message="La plateforme a été analysée.",
                severity="info",
                event_metadata={},
            )
            db.add(notification)
            await db.commit()
            notification_id = notification.id
        await engine.dispose()
        return notification_id

    notification_id = asyncio.run(seed())
    listed = phase_five_context.client.get("/v1/notifications", headers=phase_five_context.headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["is_read"] is False

    read = phase_five_context.client.post(
        f"/v1/notifications/{notification_id}/read", headers=phase_five_context.headers
    )
    assert read.status_code == 200
    assert read.json()["is_read"] is True

    hidden = phase_five_context.client.post(
        f"/v1/notifications/{notification_id}/hide", headers=phase_five_context.headers
    )
    assert hidden.status_code == 204
    assert (
        phase_five_context.client.get(
            "/v1/notifications", headers=phase_five_context.headers
        ).json()["total"]
        == 0
    )
    archived = phase_five_context.client.get(
        "/v1/notifications?hidden=true", headers=phase_five_context.headers
    )
    assert archived.status_code == 200
    assert archived.json()["total"] == 1

    async def source_count() -> int:
        engine = create_async_engine(phase_five_context.settings.database_url)
        factory = async_sessionmaker(engine)
        async with factory() as db:
            count = await db.scalar(select(func.count(Notification.id)))
        await engine.dispose()
        return count or 0

    assert asyncio.run(source_count()) == 1
    asyncio.run(seed())
    hide_all = phase_five_context.client.post(
        "/v1/notifications/hide-all", headers=phase_five_context.headers
    )
    assert hide_all.status_code == 204
    assert (
        phase_five_context.client.get(
            "/v1/notifications", headers=phase_five_context.headers
        ).json()["total"]
        == 0
    )
    assert asyncio.run(source_count()) == 2


def test_platform_history_hide_preserves_audit_events(
    phase_five_context: PhaseFiveContext,
) -> None:
    created = phase_five_context.client.post(
        "/v1/platforms",
        headers=phase_five_context.headers,
        json={"name": "Portail audité", "target_type": "none"},
    )
    assert created.status_code == 201
    platform_id = created.json()["id"]
    history = phase_five_context.client.get(
        f"/v1/platforms/{platform_id}/history", headers=phase_five_context.headers
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["action"] == "platform.create"
    assert history.json()["items"][0]["actor_name"]

    hidden = phase_five_context.client.post(
        f"/v1/platforms/{platform_id}/history/hide", headers=phase_five_context.headers
    )
    assert hidden.status_code == 204

    async def audit_count() -> int:
        engine = create_async_engine(phase_five_context.settings.database_url)
        factory = async_sessionmaker(engine)
        async with factory() as db:
            count = await db.scalar(
                select(func.count(AuditEvent.id)).where(AuditEvent.platform_id == UUID(platform_id))
            )
        await engine.dispose()
        return count or 0

    assert asyncio.run(audit_count()) == 2
    visible = phase_five_context.client.get(
        f"/v1/platforms/{platform_id}/history", headers=phase_five_context.headers
    )
    assert visible.status_code == 200
    assert visible.json()["total"] == 0
    trash = phase_five_context.client.get(
        f"/v1/platforms/{platform_id}/history?hidden=true",
        headers=phase_five_context.headers,
    )
    assert trash.status_code == 200
    assert trash.json()["total"] == 2


def test_global_activity_tracks_concrete_events_without_http_requests(
    phase_five_context: PhaseFiveContext,
) -> None:
    tracked_headers = {
        **phase_five_context.headers,
        "User-Agent": "Mozilla/5.0 Chrome/126.0.0.0 Safari/537.36",
        "X-Forwarded-For": "203.0.113.42",
    }
    viewed = phase_five_context.client.post(
        "/v1/activity/page-view",
        headers=tracked_headers,
        json={"path": "/platforms", "title": "Plateformes"},
    )
    assert viewed.status_code == 204

    page_events = phase_five_context.client.get(
        "/v1/activity?q=Page%20consult%C3%A9e",
        headers=phase_five_context.headers,
    )
    assert page_events.status_code == 200
    page_event = page_events.json()["items"][0]
    assert page_event["action"] == "page.view"
    assert page_event["actor_name"]
    assert page_event["ip"] == "203.0.113.42"
    assert page_event["metadata"]["browser"] == "Google Chrome 126.0.0.0"
    assert page_event["metadata"]["path"] == "/platforms"

    async def seed_obsolete_technical_event() -> None:
        engine = create_async_engine(phase_five_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            db.add(
                AuditEvent(
                    action="request.success",
                    entity_type="http_request",
                    summary="Requête GET /health/live réussie (200)",
                    event_metadata={"result": "success"},
                )
            )
            await db.commit()
        await engine.dispose()

    asyncio.run(seed_obsolete_technical_event())
    activity = phase_five_context.client.get(
        "/v1/activity",
        headers=phase_five_context.headers,
    )
    assert activity.status_code == 200
    assert all(item["entity_type"] != "http_request" for item in activity.json()["items"])


def test_admin_can_hide_global_activity_without_deleting_events(
    phase_five_context: PhaseFiveContext,
) -> None:
    viewed = phase_five_context.client.post(
        "/v1/activity/page-view",
        headers=phase_five_context.headers,
        json={"path": "/activity", "title": "Historique des activités"},
    )
    assert viewed.status_code == 204
    assert (
        phase_five_context.client.get(
            "/v1/activity", headers=phase_five_context.headers
        ).json()["total"]
        > 0
    )

    hidden = phase_five_context.client.post(
        "/v1/activity/hide", headers=phase_five_context.headers
    )
    assert hidden.status_code == 204
    assert (
        phase_five_context.client.get(
            "/v1/activity", headers=phase_five_context.headers
        ).json()["total"]
        == 0
    )

    async def audit_count() -> int:
        engine = create_async_engine(phase_five_context.settings.database_url)
        factory = async_sessionmaker(engine)
        async with factory() as db:
            count = await db.scalar(select(func.count(AuditEvent.id)))
        await engine.dispose()
        return count or 0

    assert asyncio.run(audit_count()) > 0


def test_audit_role_cannot_clear_global_activity(
    phase_five_context: PhaseFiveContext,
) -> None:
    async def create_audit_user() -> UUID:
        engine = create_async_engine(phase_five_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            audit_role = await db.scalar(select(Role).where(Role.name == "Audit"))
            assert audit_role is not None
            user = User(
                username="auditeur-clear-test",
                password_hash=hash_password("Auditeur!Password42"),
                display_name="Auditeur",
                must_change_password=False,
                roles=[audit_role],
            )
            db.add(user)
            await db.commit()
            user_id = user.id
        await engine.dispose()
        return user_id

    user_id = asyncio.run(create_audit_user())
    token, _ = create_access_token(user_id, phase_five_context.settings)
    denied = phase_five_context.client.post(
        "/v1/activity/hide", headers={"Authorization": f"Bearer {token}"}
    )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"


def test_audit_event_is_immutable(phase_five_context: PhaseFiveContext) -> None:
    async def mutate() -> str:
        engine = create_async_engine(phase_five_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            event = AuditEvent(
                action="test.created",
                entity_type="test",
                summary="Événement de test",
                event_metadata={},
            )
            db.add(event)
            await db.commit()
            event_id = event.id
            event.summary = "Modification interdite"
            with pytest.raises(RuntimeError, match="immutable"):
                await db.commit()
            await db.rollback()
            summary = await db.scalar(select(AuditEvent.summary).where(AuditEvent.id == event_id))
        await engine.dispose()
        assert summary is not None
        return summary

    assert asyncio.run(mutate()) == "Événement de test"
