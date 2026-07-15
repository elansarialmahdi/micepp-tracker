import asyncio
from dataclasses import dataclass
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.security import create_access_token
from app.models.auth import User
from app.models.notification import AuditEvent
from app.models.scan import ScanJob
from app.models.service import Service
from app.services.detectors import Detection
from app.services.scan_security import ScanTargetRejected, validate_scan_target
from app.services.scans import fuse_detections
from tests.conftest import AuthTestContext


@dataclass
class ScanTestContext:
    client: TestClient
    settings: Settings
    headers: dict[str, str]
    platform_id: str


@pytest.fixture
def scan_context(auth_context: AuthTestContext) -> ScanTestContext:
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
        json={
            "name": "Cible de scan",
            "target_type": "ip",
            "target_value": "8.8.8.8",
        },
    )
    assert created.status_code == 201
    return ScanTestContext(
        client=auth_context.client,
        settings=auth_context.settings,
        headers=headers,
        platform_id=created.json()["id"],
    )


def test_scan_infers_target_type_and_blocks_unsafe_targets(
    scan_context: ScanTestContext,
) -> None:
    blocked = scan_context.client.post(
        f"/v1/platforms/{scan_context.platform_id}/scans",
        headers=scan_context.headers,
        json={
            "target": "127.0.0.1",
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "SCAN_TARGET_BLOCKED"


def test_mock_scan_fuses_results_and_confirms_selected_services(
    scan_context: ScanTestContext,
) -> None:
    launched = scan_context.client.post(
        f"/v1/platforms/{scan_context.platform_id}/scans",
        headers=scan_context.headers,
        json={"authorization_confirmed": True, "scan_type": "full"},
    )
    assert launched.status_code == 202
    job = launched.json()
    assert job["status"] == "succeeded", job
    assert job["progress"] == 100
    assert len(job["detections"]) == 2
    nginx = next(item for item in job["detections"] if item["detected_name"] == "Nginx")
    assert "mock-nmap" in nginx["source_detector"]
    assert "mock-web" in nginx["source_detector"]
    assert "metadata" not in nginx

    items = [
        {
            "detected_service_id": item["id"],
            "selected": item["detected_name"] == "Nginx",
            "name": "NGINX Server" if item["detected_name"] == "Nginx" else item["detected_name"],
            "version": item["detected_version"],
            "category": "Serveurs web" if item["detected_name"] == "Nginx" else None,
        }
        for item in job["detections"]
    ]
    confirmed = scan_context.client.post(
        f"/v1/scans/{job['id']}/confirm",
        headers=scan_context.headers,
        json={"items": items},
    )
    assert confirmed.status_code == 200
    assert confirmed.json() == {"created": 1, "skipped": 1, "categories_created": 1}

    async def stored() -> tuple[Service, int, ScanJob]:
        engine = create_async_engine(scan_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            service = await db.scalar(select(Service).where(Service.name == "NGINX Server"))
            audit_count = await db.scalar(
                select(func.count(AuditEvent.id)).where(AuditEvent.action == "scan.confirm")
            )
            scan = await db.get(ScanJob, UUID(job["id"]))
            assert service is not None and scan is not None
        await engine.dispose()
        return service, audit_count or 0, scan

    service, audit_count, stored_job = asyncio.run(stored())
    assert service.source == "scan"
    assert service.source_details["scan_job_id"] == job["id"]
    assert audit_count == 1
    assert stored_job.authorization_confirmed is True


def test_queued_scan_response_serializes_empty_detections(
    scan_context: ScanTestContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    delay = MagicMock()
    monkeypatch.setattr("app.worker.execute_scan_task.delay", delay)
    scan_context.settings.app_env = "development"

    launched = scan_context.client.post(
        f"/v1/platforms/{scan_context.platform_id}/scans",
        headers=scan_context.headers,
        json={"authorization_confirmed": True, "scan_type": "full"},
    )

    assert launched.status_code == 202
    assert launched.json()["status"] == "queued"
    assert launched.json()["detections"] == []
    delay.assert_called_once()


def test_private_network_requires_explicit_configuration() -> None:
    settings = Settings(app_env="test")
    with pytest.raises(ScanTargetRejected, match="privés"):
        asyncio.run(validate_scan_target("10.0.0.4", "ip", settings))
    settings.allow_private_network_scans = True
    validated = asyncio.run(validate_scan_target("10.0.0.4", "ip", settings))
    assert validated.addresses == ("10.0.0.4",)


def test_scan_fuses_same_name_and_version_across_detectors() -> None:
    fused = fuse_detections(
        [
            Detection(
                name="Nginx",
                version="1.26.0",
                source="nmap",
                confidence=0.7,
                port=80,
                protocol="tcp",
            ),
            Detection(
                name=" nginx ",
                version="1.26.0",
                vendor="F5",
                product="nginx",
                source="web",
                confidence=0.95,
                port=443,
                protocol="https",
            ),
        ]
    )

    assert len(fused) == 1
    assert fused[0].confidence == 0.95
    assert fused[0].source == "nmap,web"
    assert fused[0].vendor == "F5"
    assert fused[0].port == 443
