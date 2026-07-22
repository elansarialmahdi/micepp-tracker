import asyncio
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.models.auth import User
from app.models.service import Service
from app.models.vulnerability import ServiceVulnerability
from tests.conftest import AuthTestContext


def admin_headers(context: AuthTestContext) -> dict[str, str]:
    async def enable_admin() -> UUID:
        engine = create_async_engine(context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            user = await db.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            user.must_change_password = False
            await db.commit()
            user_id = user.id
        await engine.dispose()
        return user_id

    token, _ = create_access_token(asyncio.run(enable_admin()), context.settings)
    return {"Authorization": f"Bearer {token}"}


def handler_headers(context: AuthTestContext, user_id: UUID) -> dict[str, str]:
    async def enable_handler() -> None:
        engine = create_async_engine(context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            user = await db.get(User, user_id)
            assert user is not None
            user.must_change_password = False
            await db.commit()
        await engine.dispose()

    asyncio.run(enable_handler())
    token, _ = create_access_token(user_id, context.settings)
    return {"Authorization": f"Bearer {token}"}


def treatment_state(
    context: AuthTestContext, service_id: str, link_id: str
) -> tuple[str | None, str | None, bool, object | None]:
    async def read_state() -> tuple[str | None, str | None, bool, object | None]:
        engine = create_async_engine(context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            service = await db.get(Service, UUID(service_id))
            link = await db.get(ServiceVulnerability, UUID(link_id))
            assert service is not None
            assert link is not None
            state = (service.version, service.cpe_uri, service.cpe_enabled, link.resolved_at)
        await engine.dispose()
        return state

    return asyncio.run(read_state())


def set_initial_cpe(context: AuthTestContext, service_id: str) -> None:
    async def update_state() -> None:
        engine = create_async_engine(context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            service = await db.get(Service, UUID(service_id))
            assert service is not None
            service.cpe_enabled = False
            service.cpe_uri = "cpe:2.3:a:apache:http_server:2.4.49:*:*:*:*:*:*:*"
            service.cpe_match_confidence = 1.0
            service.cpe_match_method = "manual"
            await db.commit()
        await engine.dispose()

    asyncio.run(update_state())


def create_vulnerable_service(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    platform = client.post(
        "/v1/platforms",
        headers=headers,
        json={"name": "Plateforme traitement", "target_type": "none"},
    )
    assert platform.status_code == 201
    service = client.post(
        f"/v1/platforms/{platform.json()['id']}/services/bulk",
        headers=headers,
        json={"items": [{"name": "Apache", "version": "2.4.49", "category_id": None}]},
    )
    assert service.status_code == 201
    service_id = service.json()[0]["id"]
    vulnerability = client.post(
        f"/v1/services/{service_id}/vulnerabilities/manual",
        headers=headers,
        json={"identifier": "CVE-TEST-0001", "description": "Vulnérabilité de test"},
    )
    assert vulnerability.status_code == 201
    return service_id, vulnerability.json()["link_id"]


def test_admin_assigns_handler_submits_and_admin_confirms(
    auth_context: AuthTestContext,
) -> None:
    client = auth_context.client
    admin = admin_headers(auth_context)
    roles = client.get("/v1/roles", headers=admin)
    assert roles.status_code == 200
    by_name = {role["name"]: role for role in roles.json()}
    assert by_name["Audit"]["permissions"] == ["history.read"]
    assert set(by_name["Traitant"]["permissions"]) == {
        "treatment.read_own",
        "treatment.submit",
    }

    created_user = client.post(
        "/v1/users",
        headers=admin,
        json={
            "username": "traitant",
            "password": "Temporary!Password42",
            "role_ids": [by_name["Traitant"]["id"]],
        },
    )
    assert created_user.status_code == 201
    assert created_user.json()["display_name"] == "traitant"

    multiple_roles = client.post(
        "/v1/users",
        headers=admin,
        json={
            "username": "multi-role",
            "password": "Temporary!Password42",
            "role_ids": [by_name["Audit"]["id"], by_name["Traitant"]["id"]],
        },
    )
    assert multiple_roles.status_code == 422

    handler_id = UUID(created_user.json()["id"])
    handler = handler_headers(auth_context, handler_id)

    service_id, link_id = create_vulnerable_service(client, admin)
    second_vulnerability = client.post(
        f"/v1/services/{service_id}/vulnerabilities/manual",
        headers=admin,
        json={"identifier": "CVE-TEST-0002", "description": "Deuxième vulnérabilité"},
    )
    assert second_vulnerability.status_code == 201
    second_link_id = second_vulnerability.json()["link_id"]
    set_initial_cpe(auth_context, service_id)
    assigned = client.post(
        "/v1/treatments",
        headers=admin,
        json={
            "service_id": service_id,
            "assigned_to_id": str(handler_id),
            "note": "Mettre à jour Apache.",
        },
    )
    assert assigned.status_code == 201
    assert assigned.json()["status"] == "assigned"
    assert assigned.json()["service_name"] == "Apache"
    assert assigned.json()["service_version_before"] == "2.4.49"
    assert "cve_id" not in assigned.json()
    treatment_id = assigned.json()["id"]
    assert treatment_state(auth_context, service_id, link_id) == (
        "2.4.49",
        "cpe:2.3:a:apache:http_server:2.4.49:*:*:*:*:*:*:*",
        False,
        None,
    )
    assert treatment_state(auth_context, service_id, second_link_id)[3] is None

    mine = client.get("/v1/treatments/mine", headers=handler)
    assert mine.status_code == 200
    assert mine.json()[0]["platform_name"] == "Plateforme traitement"

    submitted = client.patch(
        f"/v1/treatments/{treatment_id}/submit",
        headers=handler,
        json={"new_version": "2.4.60", "note": "Mise à jour réalisée."},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    # The handler proposes a version; assignment and submission must not alter
    # the inventory or make the vulnerability disappear.
    assert treatment_state(auth_context, service_id, link_id) == (
        "2.4.49",
        "cpe:2.3:a:apache:http_server:2.4.49:*:*:*:*:*:*:*",
        False,
        None,
    )
    assert treatment_state(auth_context, service_id, second_link_id)[3] is None

    confirmed = client.patch(f"/v1/treatments/{treatment_id}/confirm", headers=admin)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    service = client.get(f"/v1/services/{service_id}", headers=admin)
    assert service.status_code == 200
    assert service.json()["version"] == "2.4.60"
    confirmed_state = treatment_state(auth_context, service_id, link_id)
    assert confirmed_state[:3] == ("2.4.60", None, True)
    assert confirmed_state[3] is not None
    assert treatment_state(auth_context, service_id, second_link_id)[3] is not None


def test_admin_cancels_treatment_and_can_assign_it_again(
    auth_context: AuthTestContext,
) -> None:
    client = auth_context.client
    admin = admin_headers(auth_context)
    roles = client.get("/v1/roles", headers=admin).json()
    handler_role = next(role for role in roles if role["name"] == "Traitant")
    created_user = client.post(
        "/v1/users",
        headers=admin,
        json={
            "username": "traitant-annulation",
            "password": "Temporary!Password42",
            "role_ids": [handler_role["id"]],
        },
    )
    handler_id = UUID(created_user.json()["id"])
    handler = handler_headers(auth_context, handler_id)
    service_id, link_id = create_vulnerable_service(client, admin)

    assigned = client.post(
        "/v1/treatments",
        headers=admin,
        json={
            "service_id": service_id,
            "assigned_to_id": str(handler_id),
        },
    )
    assert assigned.status_code == 201
    treatment_id = assigned.json()["id"]

    cancelled = client.patch(f"/v1/treatments/{treatment_id}/cancel", headers=admin)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.get("/v1/treatments/mine", headers=handler).json() == []
    cancelled_items = client.get("/v1/treatments?state=cancelled", headers=admin)
    assert cancelled_items.status_code == 200
    assert [item["id"] for item in cancelled_items.json()] == [treatment_id]

    reassigned = client.post(
        "/v1/treatments",
        headers=admin,
        json={
            "service_id": service_id,
            "assigned_to_id": str(handler_id),
        },
    )
    assert reassigned.status_code == 201
    assert reassigned.json()["id"] != treatment_id
