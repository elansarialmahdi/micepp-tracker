import asyncio
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import create_access_token
from app.models.auth import User
from tests.conftest import AuthTestContext


@dataclass
class PlatformTestContext:
    client: TestClient
    settings: Settings
    headers: dict[str, str]


@pytest.fixture
def platform_context(auth_context: AuthTestContext) -> PlatformTestContext:
    async def enable_admin() -> UUID:
        engine = create_async_engine(auth_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            user = await db.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            user.must_change_password = False
            await db.commit()
            user_id = user.id
        await engine.dispose()
        return user_id

    user_id = asyncio.run(enable_admin())
    token, _ = create_access_token(user_id, auth_context.settings)
    return PlatformTestContext(
        client=auth_context.client,
        settings=auth_context.settings,
        headers={"Authorization": f"Bearer {token}"},
    )


def create_platform(
    context: PlatformTestContext,
    *,
    name: str,
    target_type: str = "none",
    target_value: str | None = None,
):
    return context.client.post(
        "/v1/platforms",
        headers=context.headers,
        json={
            "name": name,
            "target_type": target_type,
            "target_value": target_value,
            "description": f"Description de {name}",
        },
    )


def test_create_platforms_without_target_with_url_and_ip(
    platform_context: PlatformTestContext,
) -> None:
    no_target = create_platform(platform_context, name="Plateforme libre")
    assert no_target.status_code == 201
    assert no_target.json()["normalized_target"] is None

    url = create_platform(
        platform_context,
        name="Portail public",
        target_type="url",
        target_value="HTTPS://Example.COM:443",
    )
    assert url.status_code == 201
    assert url.json()["normalized_target"] == "https://example.com/"

    ip = create_platform(
        platform_context,
        name="Intranet",
        target_type="ip",
        target_value="2001:0db8:0:0:0:0:0:1",
    )
    assert ip.status_code == 201
    assert ip.json()["normalized_target"] == "2001:db8::1"


def test_rejects_invalid_or_inconsistent_target(platform_context: PlatformTestContext) -> None:
    invalid_ip = create_platform(
        platform_context,
        name="IP invalide",
        target_type="ip",
        target_value="999.2.3.4",
    )
    assert invalid_ip.status_code == 422
    assert invalid_ip.json()["error"]["code"] == "PLATFORM_TARGET_INVALID"

    credentials_in_url = create_platform(
        platform_context,
        name="URL invalide",
        target_type="url",
        target_value="https://user:password@example.com",
    )
    assert credentials_in_url.status_code == 422
    assert credentials_in_url.json()["error"]["code"] == "PLATFORM_TARGET_INVALID"


def test_list_search_filter_sort_and_pagination(platform_context: PlatformTestContext) -> None:
    create_platform(
        platform_context,
        name="Portail MICEPP",
        target_type="url",
        target_value="https://micepp.example",
    )
    create_platform(
        platform_context,
        name="Serveur interne",
        target_type="ip",
        target_value="192.0.2.10",
    )
    create_platform(platform_context, name="Plateforme manuelle")

    filtered = platform_context.client.get(
        "/v1/platforms?q=micepp&target_type=url&sort=name&page=1&page_size=2",
        headers=platform_context.headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["name"] == "Portail MICEPP"

    paged = platform_context.client.get(
        "/v1/platforms?page=2&page_size=2&sort=name", headers=platform_context.headers
    )
    assert paged.status_code == 200
    assert paged.json()["total"] == 3
    assert len(paged.json()["items"]) == 1


def test_update_and_archive_without_physical_deletion(
    platform_context: PlatformTestContext,
) -> None:
    created = create_platform(
        platform_context,
        name="Ancien nom",
        target_type="url",
        target_value="http://Example.com:80/path",
    ).json()
    platform_id = created["id"]

    updated = platform_context.client.patch(
        f"/v1/platforms/{platform_id}",
        headers=platform_context.headers,
        json={"name": "Nouveau nom", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Nouveau nom"
    assert updated.json()["normalized_target"] == "http://example.com/path"

    archived = platform_context.client.delete(
        f"/v1/platforms/{platform_id}", headers=platform_context.headers
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    active_list = platform_context.client.get("/v1/platforms", headers=platform_context.headers)
    assert active_list.json()["total"] == 0
    archived_list = platform_context.client.get(
        "/v1/platforms?include_archived=true", headers=platform_context.headers
    )
    assert archived_list.json()["total"] == 1
    detail = platform_context.client.get(
        f"/v1/platforms/{platform_id}", headers=platform_context.headers
    )
    assert detail.status_code == 200
    assert detail.json()["archived_at"] is not None
