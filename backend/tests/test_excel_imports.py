import asyncio
from dataclasses import dataclass
from io import BytesIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import create_access_token
from app.models.auth import User
from app.models.notification import AuditEvent
from app.models.service import Service
from tests.conftest import AuthTestContext


@dataclass
class ImportTestContext:
    client: TestClient
    settings: Settings
    headers: dict[str, str]
    platform_id: str


@pytest.fixture
def import_context(auth_context: AuthTestContext) -> ImportTestContext:
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
    headers = {"Authorization": f"Bearer {token}"}
    created = auth_context.client.post(
        "/v1/platforms",
        headers=headers,
        json={"name": "Plateforme import", "target_type": "none"},
    )
    assert created.status_code == 201
    return ImportTestContext(
        client=auth_context.client,
        settings=auth_context.settings,
        headers=headers,
        platform_id=created.json()["id"],
    )


def workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def upload(context: ImportTestContext, content: bytes, filename: str = "services.xlsx"):
    return context.client.post(
        f"/v1/platforms/{context.platform_id}/service-imports",
        headers=context.headers,
        files={
            "file": (
                filename,
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def service_count(context: ImportTestContext) -> int:
    async def count() -> int:
        engine = create_async_engine(context.settings.database_url)
        factory = async_sessionmaker(engine)
        async with factory() as db:
            value = await db.scalar(select(func.count(Service.id)))
        await engine.dispose()
        return value or 0

    return asyncio.run(count())


def test_excel_import_preview_then_atomic_confirmation(import_context: ImportTestContext) -> None:
    content = workbook_bytes(
        [
            ["Service", "Version", "Catégorie"],
            ["Apache", "2.4.62", "Web"],
            ["Apache", "2.4.62", "Web"],
            [None, "1.0", "Outils"],
            ["Nginx", None, None],
        ]
    )
    uploaded = upload(import_context, content)
    assert uploaded.status_code == 201
    payload = uploaded.json()
    assert payload["row_count"] == 4
    assert [column["name"] for column in payload["columns"]] == [
        "Service",
        "Version",
        "Catégorie",
    ]
    assert service_count(import_context) == 0

    preview = import_context.client.post(
        f"/v1/service-imports/{payload['id']}/preview",
        headers=import_context.headers,
        json={"name_column": 0, "version_column": 1, "category_column": 2},
    )
    assert preview.status_code == 200
    assert preview.json()["valid_count"] == 2
    assert preview.json()["invalid_count"] == 1
    assert preview.json()["duplicate_count"] == 1
    assert service_count(import_context) == 0

    confirmed = import_context.client.post(
        f"/v1/service-imports/{payload['id']}/confirm",
        headers=import_context.headers,
        json={"duplicate_strategy": "ignore", "ignored_rows": [4]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json() == {
        "created": 2,
        "merged": 0,
        "skipped": 1,
        "invalid": 1,
        "categories_created": 1,
    }
    assert service_count(import_context) == 2

    async def imported_rows() -> tuple[list[Service], int]:
        engine = create_async_engine(import_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            services = (await db.scalars(select(Service).order_by(Service.name))).all()
            audit_count = await db.scalar(
                select(func.count(AuditEvent.id)).where(AuditEvent.action == "service.import.excel")
            )
        await engine.dispose()
        return services, audit_count or 0

    services, audit_count = asyncio.run(imported_rows())
    assert all(service.source == "excel" for service in services)
    assert all(
        service.source_details and service.source_details["import_id"] for service in services
    )
    assert audit_count == 1


def test_rejects_invalid_extension_mime_and_fake_xlsx(import_context: ImportTestContext) -> None:
    valid = workbook_bytes([["Service"], ["Nginx"]])
    extension = upload(import_context, valid, "services.xls")
    assert extension.status_code == 415
    assert extension.json()["error"]["code"] == "IMPORT_EXTENSION_INVALID"

    mime = import_context.client.post(
        f"/v1/platforms/{import_context.platform_id}/service-imports",
        headers=import_context.headers,
        files={"file": ("services.xlsx", valid, "text/html")},
    )
    assert mime.status_code == 415
    assert mime.json()["error"]["code"] == "IMPORT_MIME_INVALID"

    fake = upload(import_context, b"PK\x03\x04not-a-workbook")
    assert fake.status_code == 422
    assert fake.json()["error"]["code"] == "IMPORT_FILE_INVALID"


def test_formula_is_never_executed_and_becomes_invalid(import_context: ImportTestContext) -> None:
    content = workbook_bytes([["Service"], ["=1+1"]])
    uploaded = upload(import_context, content)
    assert uploaded.status_code == 422
    assert uploaded.json()["error"]["code"] == "IMPORT_FILE_INVALID"
    assert service_count(import_context) == 0


def test_optional_mock_categorization_and_manual_override(
    import_context: ImportTestContext,
) -> None:
    import_context.settings.ai_provider = "mock"
    uploaded = upload(import_context, workbook_bytes([["Service"], ["Nginx"]]))
    assert uploaded.status_code == 201
    assert uploaded.json()["ai_categorization_available"] is True
    preview = import_context.client.post(
        f"/v1/service-imports/{uploaded.json()['id']}/preview",
        headers=import_context.headers,
        json={"name_column": 0, "category_mode": "ai"},
    )
    assert preview.status_code == 200
    assert preview.json()["rows"][0]["category"] == "Web"
    confirmed = import_context.client.post(
        f"/v1/service-imports/{uploaded.json()['id']}/confirm",
        headers=import_context.headers,
        json={"category_overrides": {"2": "Serveurs web"}},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["categories_created"] == 1
