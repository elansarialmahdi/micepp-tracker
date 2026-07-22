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
class InventoryContext:
    client: TestClient
    settings: Settings
    headers: dict[str, str]


@pytest.fixture
def inventory_context(auth_context: AuthTestContext) -> InventoryContext:
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
    return InventoryContext(
        client=auth_context.client,
        settings=auth_context.settings,
        headers={"Authorization": f"Bearer {token}"},
    )


def create_platform(context: InventoryContext, name: str) -> str:
    response = context.client.post(
        "/v1/platforms",
        headers=context.headers,
        json={"name": name, "target_type": "none"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_category(context: InventoryContext, platform_id: str, name: str):  # type: ignore[no-untyped-def]
    return context.client.post(
        f"/v1/platforms/{platform_id}/categories",
        headers=context.headers,
        json={"name": name},
    )


def test_categories_are_global_and_unique(inventory_context: InventoryContext) -> None:
    first_platform = create_platform(inventory_context, "Première plateforme")
    second_platform = create_platform(inventory_context, "Seconde plateforme")

    first = create_category(inventory_context, first_platform, " Serveurs   web ")
    assert first.status_code == 201
    duplicate = create_category(inventory_context, first_platform, "serveurs web")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CATEGORY_DUPLICATE"
    same_name_elsewhere = create_category(inventory_context, second_platform, "Serveurs web")
    assert same_name_elsewhere.status_code == 409

    categories = inventory_context.client.get(
        f"/v1/platforms/{first_platform}/categories", headers=inventory_context.headers
    )
    assert categories.status_code == 200
    assert [item["name"] for item in categories.json()] == ["Serveurs web"]


def test_archived_category_can_be_created_again(inventory_context: InventoryContext) -> None:
    platform_id = create_platform(inventory_context, "Plateforme restauration")
    category = create_category(inventory_context, platform_id, "Serveurs web").json()

    archived = inventory_context.client.delete(
        f"/v1/categories/{category['id']}", headers=inventory_context.headers
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    restored = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/categories",
        headers=inventory_context.headers,
        json={"name": " serveurs   web ", "description": "Catégorie restaurée"},
    )

    assert restored.status_code == 201
    assert restored.json()["id"] == category["id"]
    assert restored.json()["archived_at"] is None
    assert restored.json()["description"] == "Catégorie restaurée"


def test_ai_categorization_creates_and_reuses_global_categories(
    inventory_context: InventoryContext,
) -> None:
    platform_id = create_platform(inventory_context, "Plateforme IA")
    inventory_context.settings.ai_provider = "mock"
    response = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/categories/ai-categorize",
        headers=inventory_context.headers,
        json={
            "items": [
                {"key": "apache", "name": "Apache HTTP Server", "version": "2.4"},
                {"key": "php", "name": "PHP", "version": "8.3"},
            ]
        },
    )
    assert response.status_code == 200
    by_key = {item["key"]: item for item in response.json()["items"]}
    assert by_key["apache"]["category"]["name"] == "Web et API"
    assert by_key["php"]["category"]["name"] == "Langages et runtimes"
    assert by_key["apache"]["category_created"] is True

    second = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/categories/ai-categorize",
        headers=inventory_context.headers,
        json={"items": [{"key": "nginx", "name": "Nginx"}]},
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["category_created"] is False


def test_ai_preview_prefers_a_compatible_existing_category(
    inventory_context: InventoryContext,
) -> None:
    platform_id = create_platform(inventory_context, "Plateforme avec catégories")
    inventory_context.settings.ai_provider = "mock"
    category = create_category(inventory_context, platform_id, "Serveurs web").json()

    preview = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/categories/ai-categorize/preview",
        headers=inventory_context.headers,
        json={"items": [{"key": "apache", "name": "Apache HTTP Server"}]},
    )

    assert preview.status_code == 200
    assert preview.json()["items"] == [
        {
            "key": "apache",
            "category_name": "Serveurs web",
            "existing_category_id": category["id"],
            "confidence": 0.9,
            "reason": "Classification déterministe du provider de test.",
        }
    ]


def test_ai_preview_does_not_create_until_selected_categories_are_confirmed(
    inventory_context: InventoryContext,
) -> None:
    platform_id = create_platform(inventory_context, "Plateforme aperçu IA")
    inventory_context.settings.ai_provider = "mock"
    preview = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/categories/ai-categorize/preview",
        headers=inventory_context.headers,
        json={
            "items": [
                {"key": "apache", "name": "Apache"},
                {"key": "php", "name": "PHP"},
            ]
        },
    )
    assert preview.status_code == 200
    assert [item["category_name"] for item in preview.json()["items"]] == [
        "Web et API",
        "Langages et runtimes",
    ]
    categories_before = inventory_context.client.get(
        f"/v1/platforms/{platform_id}/categories", headers=inventory_context.headers
    )
    assert categories_before.json() == []

    confirmed = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/categories/ai-categorize/confirm",
        headers=inventory_context.headers,
        json={
            "items": [
                {"key": "apache", "category_name": "Serveurs HTTP", "selected": True},
                {"key": "php", "category_name": "Langages et runtimes", "selected": False},
            ]
        },
    )
    assert confirmed.status_code == 200
    assert [(item["key"], item["category"]["name"]) for item in confirmed.json()["items"]] == [
        ("apache", "Serveurs HTTP")
    ]
    categories_after = inventory_context.client.get(
        f"/v1/platforms/{platform_id}/categories", headers=inventory_context.headers
    )
    assert [item["name"] for item in categories_after.json()] == ["Serveurs HTTP"]


def test_ai_confirmation_restores_an_archived_category(
    inventory_context: InventoryContext,
) -> None:
    platform_id = create_platform(inventory_context, "Plateforme restauration IA")
    category = create_category(inventory_context, platform_id, "Serveurs HTTP").json()
    archived = inventory_context.client.delete(
        f"/v1/categories/{category['id']}", headers=inventory_context.headers
    )
    assert archived.status_code == 200

    confirmed = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/categories/ai-categorize/confirm",
        headers=inventory_context.headers,
        json={
            "items": [
                {"key": "apache", "category_name": "serveurs http", "selected": True}
            ]
        },
    )

    assert confirmed.status_code == 200
    restored = confirmed.json()["items"][0]["category"]
    assert restored["id"] == category["id"]
    assert restored["archived_at"] is None


def test_bulk_services_deduplication_and_global_category_reuse(
    inventory_context: InventoryContext,
) -> None:
    first_platform = create_platform(inventory_context, "Plateforme applicative")
    second_platform = create_platform(inventory_context, "Autre plateforme")
    category = create_category(inventory_context, first_platform, "Applications").json()
    global_category = inventory_context.client.get(
        f"/v1/platforms/{second_platform}/categories", headers=inventory_context.headers
    ).json()[0]
    assert global_category["id"] == category["id"]

    created = inventory_context.client.post(
        f"/v1/platforms/{first_platform}/services/bulk",
        headers=inventory_context.headers,
        json={
            "items": [
                {"name": "Apache", "version": "2.4.62", "category_id": category["id"]},
                {"name": "PHP", "version": "8.3"},
            ]
        },
    )
    assert created.status_code == 201
    assert created.json()[0]["category_name"] == "Applications"

    existing_duplicate = inventory_context.client.post(
        f"/v1/platforms/{first_platform}/services",
        headers=inventory_context.headers,
        json={"name": " apache ", "version": "2.4.62"},
    )
    assert existing_duplicate.status_code == 409
    assert existing_duplicate.json()["error"]["code"] == "SERVICE_DUPLICATE"

    payload_duplicate = inventory_context.client.post(
        f"/v1/platforms/{first_platform}/services/bulk",
        headers=inventory_context.headers,
        json={"items": [{"name": "Nginx"}, {"name": " nginx "}]},
    )
    assert payload_duplicate.status_code == 409

    reused_category = inventory_context.client.post(
        f"/v1/platforms/{first_platform}/services",
        headers=inventory_context.headers,
        json={"name": "PostgreSQL", "category_id": global_category["id"]},
    )
    assert reused_category.status_code == 201


def test_service_filters_update_and_soft_archive(inventory_context: InventoryContext) -> None:
    platform_id = create_platform(inventory_context, "Plateforme filtrée")
    category = create_category(inventory_context, platform_id, "Bases de données").json()
    create_category(inventory_context, platform_id, "Catégorie inutilisée")
    postgres = inventory_context.client.post(
        f"/v1/platforms/{platform_id}/services",
        headers=inventory_context.headers,
        json={"name": "PostgreSQL", "version": "16", "category_id": category["id"]},
    ).json()
    inventory_context.client.post(
        f"/v1/platforms/{platform_id}/services",
        headers=inventory_context.headers,
        json={"name": "Redis", "version": "7.4"},
    )

    used_categories = inventory_context.client.get(
        f"/v1/platforms/{platform_id}/categories?used_only=true",
        headers=inventory_context.headers,
    )
    assert [item["name"] for item in used_categories.json()] == ["Bases de données"]

    filtered = inventory_context.client.get(
        f"/v1/platforms/{platform_id}/services?category_id={category['id']}&q=postgres",
        headers=inventory_context.headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["name"] == "PostgreSQL"

    uncategorized = inventory_context.client.get(
        f"/v1/platforms/{platform_id}/services?uncategorized=true",
        headers=inventory_context.headers,
    )
    assert uncategorized.json()["total"] == 1
    assert uncategorized.json()["items"][0]["name"] == "Redis"

    updated = inventory_context.client.patch(
        f"/v1/services/{postgres['id']}",
        headers=inventory_context.headers,
        json={"version": "17", "category_id": None},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == "17"
    assert updated.json()["category_id"] is None

    archived = inventory_context.client.delete(
        f"/v1/services/{postgres['id']}", headers=inventory_context.headers
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    active = inventory_context.client.get(
        f"/v1/platforms/{platform_id}/services", headers=inventory_context.headers
    )
    assert active.json()["total"] == 1
    all_services = inventory_context.client.get(
        f"/v1/platforms/{platform_id}/services?include_archived=true",
        headers=inventory_context.headers,
    )
    assert all_services.json()["total"] == 2
