import asyncio
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.models.auth import User
from app.models.notification import Notification
from app.models.vulnerability import ServiceVulnerability, Vulnerability
from app.services.nvd_client import MOCK_CVES, NVDClient
from tests.conftest import AuthTestContext


@dataclass
class VulnerabilityTestContext:
    client: TestClient
    headers: dict[str, str]
    service_id: str
    settings: object


@pytest.fixture
def vulnerability_context(auth_context: AuthTestContext) -> VulnerabilityTestContext:
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
        json={"name": "NVD", "target_type": "ip", "target_value": "8.8.4.4"},
    )
    service = auth_context.client.post(
        f"/v1/platforms/{platform.json()['id']}/services",
        headers=headers,
        json={
            "name": "NGINX",
            "vendor": "F5",
            "product": "nginx",
            "version": "1.20.0",
        },
    )
    assert service.status_code == 201
    return VulnerabilityTestContext(
        auth_context.client, headers, service.json()["id"], auth_context.settings
    )


def test_nvd_check_selects_cpe_creates_history_and_deduplicates_notifications(
    vulnerability_context: VulnerabilityTestContext,
) -> None:
    first = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "completed"
    assert first.json()["active_vulnerabilities"] == 1
    assert first.json()["new_notifications"] == 1

    notifications = vulnerability_context.client.get(
        "/v1/notifications", headers=vulnerability_context.headers
    )
    assert notifications.status_code == 200
    notification = notifications.json()["items"][0]
    assert notification["service_name"] == "NGINX"
    assert notification["service_version"] == "1.20.0"
    assert notification["threat_identifier"] == "CVE-2021-23017"
    assert notification["platforms"][0]["name"] == "NVD"

    candidates = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/cpe-candidates",
        headers=vulnerability_context.headers,
    )
    assert candidates.status_code == 200
    assert candidates.json()[0]["selected"] is True

    vulnerabilities = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    )
    assert vulnerabilities.status_code == 200
    item = vulnerabilities.json()[0]
    assert item["cve_id"] == "CVE-2021-23017"
    assert item["match_state"] == "confirmed"

    second = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert second.status_code == 200
    assert second.json()["new_notifications"] == 0

    ignored = vulnerability_context.client.patch(
        f"/v1/service-vulnerabilities/{item['link_id']}/ignore",
        headers=vulnerability_context.headers,
        json={"ignored": True, "reason": "Risque accepté temporairement"},
    )
    assert ignored.status_code == 200
    assert ignored.json()["ignored_at"] is not None

    async def counts() -> tuple[int, int, int]:
        settings = vulnerability_context.settings
        engine = create_async_engine(settings.database_url)  # type: ignore[attr-defined]
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            notifications = await db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.type == "vulnerability.detected"
                )
            )
            links = await db.scalar(select(func.count(ServiceVulnerability.id)))
            cves = await db.scalar(select(func.count(Vulnerability.id)))
        await engine.dispose()
        return notifications or 0, links or 0, cves or 0

    assert asyncio.run(counts()) == (1, 1, 1)


def test_multiple_vulnerabilities_create_one_notification_per_service(
    vulnerability_context: VulnerabilityTestContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = deepcopy(MOCK_CVES["f5:nginx"][0])
    second = deepcopy(first)
    second["cve"]["id"] = "CVE-2026-99999"
    second["cve"]["descriptions"][0]["value"] = "A second NGINX vulnerability."

    async def multiple_cves(_client: NVDClient, _cpe_uri: str) -> list[dict]:
        return [first, second]

    monkeypatch.setattr(NVDClient, "cves_for_cpe", multiple_cves)

    checked = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert checked.status_code == 200, checked.text
    assert checked.json()["active_vulnerabilities"] == 2
    assert checked.json()["new_notifications"] == 1

    notifications = vulnerability_context.client.get(
        "/v1/notifications", headers=vulnerability_context.headers
    )
    assert notifications.status_code == 200
    payload = notifications.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    notification = payload["items"][0]
    assert notification["service_name"] == "NGINX"
    assert notification["metadata"]["vulnerability_count"] == 2
    assert set(notification["metadata"]["identifiers"]) == {
        "CVE-2021-23017",
        "CVE-2026-99999",
    }

    rechecked = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert rechecked.status_code == 200
    assert rechecked.json()["new_notifications"] == 0
    assert vulnerability_context.client.get(
        "/v1/notifications", headers=vulnerability_context.headers
    ).json()["total"] == 1


def test_version_change_invalidates_old_result_and_rechecks_current_version(
    vulnerability_context: VulnerabilityTestContext,
) -> None:
    first = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert first.status_code == 200
    assert first.json()["active_vulnerabilities"] == 1

    changed = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
        json={"version": "1.22.0"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == "1.22.0"
    assert changed.json()["cpe_uri"] is None
    assert changed.json()["last_checked_at"] is None

    stale_results = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    )
    assert stale_results.status_code == 200
    assert stale_results.json() == []

    recheck = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert recheck.status_code == 200, recheck.text
    assert recheck.json()["status"] == "completed"
    assert recheck.json()["active_vulnerabilities"] == 0

    current_results = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    )
    assert current_results.status_code == 200
    assert current_results.json() == []

    async def resolved_at() -> object:
        settings = vulnerability_context.settings
        engine = create_async_engine(settings.database_url)  # type: ignore[attr-defined]
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            link = await db.scalar(select(ServiceVulnerability))
            assert link is not None
            result = link.resolved_at
        await engine.dispose()
        return result

    assert asyncio.run(resolved_at()) is not None


def test_osv_checks_exact_package_version_without_cpe(
    vulnerability_context: VulnerabilityTestContext,
) -> None:
    vulnerability_context.settings.osv_mode = "mock"  # type: ignore[attr-defined]
    changed = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
        json={
            "name": "Axios",
            "vendor": None,
            "product": "axios",
            "version": "1.11.0",
        },
    )
    assert changed.status_code == 200

    vulnerable = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert vulnerable.status_code == 200, vulnerable.text
    assert vulnerable.json()["source"] == "osv"
    assert vulnerable.json()["cpe_uri"] is None
    assert vulnerable.json()["active_vulnerabilities"] == 1

    service = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
    ).json()
    assert service["security_identity"] == {
        "status": "verified",
        "source": "OSV+NVD",
        "ecosystem": "npm",
        "package": "axios",
        "version": "1.11.0",
    }
    findings = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    ).json()
    assert [item["cve_id"] for item in findings] == ["CVE-2026-44494"]

    upgraded = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
        json={"version": "1.18.1"},
    )
    assert upgraded.status_code == 200
    safe = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert safe.status_code == 200
    assert safe.json()["source"] == "osv"
    assert safe.json()["active_vulnerabilities"] == 0


def test_package_check_combines_osv_and_nvd_findings(
    vulnerability_context: VulnerabilityTestContext,
) -> None:
    vulnerability_context.settings.osv_mode = "mock"  # type: ignore[attr-defined]
    changed = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
        json={"name": "react", "vendor": None, "product": None, "version": "19.0.0"},
    )
    assert changed.status_code == 200

    result = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert result.status_code == 200, result.text
    assert result.json()["source"] == "osv+nvd"
    assert result.json()["active_vulnerabilities"] == 1
    assert result.json()["cpe_uri"] == "cpe:2.3:a:facebook:react:19.0.0:*:*:*:*:*:*:*"

    findings = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    ).json()
    assert [item["cve_id"] for item in findings] == ["CVE-2025-55182"]


def test_product_family_uses_cna_versions_when_nvd_has_no_exact_cpe(
    vulnerability_context: VulnerabilityTestContext,
) -> None:
    vulnerability_context.settings.osv_mode = "mock"  # type: ignore[attr-defined]
    changed = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
        json={
            "name": "IceHRM",
            "vendor": None,
            "product": None,
            "version": "35.0.1",
        },
    )
    assert changed.status_code == 200

    result = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"
    assert result.json()["active_vulnerabilities"] == 1
    assert result.json()["cpe_uri"] == "cpe:2.3:a:icehrm:icehrm:*:*:*:*:*:*:*:*"

    service = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
    ).json()
    assert service["cpe_match_method"] == "nvd_auto_family"
    assert service["security_identity"]["source"] == "NVD+CVE"

    findings = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    ).json()
    assert [item["cve_id"] for item in findings] == ["CVE-2026-15478"]
    assert findings[0]["match_state"] == "confirmed"


def test_ignored_vulnerabilities_are_available_in_history_and_reactivatable(
    vulnerability_context: VulnerabilityTestContext,
) -> None:
    checked = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert checked.status_code == 200
    active = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    ).json()
    link_id = active[0]["link_id"]

    ignored = vulnerability_context.client.patch(
        f"/v1/service-vulnerabilities/{link_id}/ignore",
        headers=vulnerability_context.headers,
        json={"ignored": True, "reason": "Acceptée temporairement"},
    )
    assert ignored.status_code == 200
    assert vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    ).json() == []
    history = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities?view=history",
        headers=vulnerability_context.headers,
    )
    assert history.status_code == 200
    assert [item["link_id"] for item in history.json()] == [link_id]

    restored = vulnerability_context.client.patch(
        f"/v1/service-vulnerabilities/{link_id}/ignore",
        headers=vulnerability_context.headers,
        json={"ignored": False},
    )
    assert restored.status_code == 200
    assert restored.json()["ignored_at"] is None
    assert restored.json()["resolved_at"] is None
    assert vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    ).json()[0]["link_id"] == link_id

    service = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}",
        headers=vulnerability_context.headers,
    ).json()
    platform_history = vulnerability_context.client.get(
        f"/v1/platforms/{service['platform_id']}/history",
        headers=vulnerability_context.headers,
    ).json()
    actions = {item["action"] for item in platform_history["items"]}
    assert {"vulnerability.ignore", "vulnerability.restore"}.issubset(actions)
    decisions = [
        item["summary"]
        for item in platform_history["items"]
        if item["action"] in {"vulnerability.ignore", "vulnerability.restore"}
    ]
    assert all("service NGINX" in decision for decision in decisions)


def test_manual_vulnerability_and_verified_cpe_controls(
    vulnerability_context: VulnerabilityTestContext,
) -> None:
    checked = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert checked.status_code == 200
    assert checked.json()["active_vulnerabilities"] == 1
    manual = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities/manual",
        headers=vulnerability_context.headers,
        json={
            "description": "Une configuration locale doit être corrigée.",
        },
    )
    assert manual.status_code == 201, manual.text
    manual_identifier = manual.json()["cve_id"]
    assert manual_identifier.startswith("MANUEL-")
    assert manual.json()["severity"] == "unknown"

    notifications = vulnerability_context.client.get(
        "/v1/notifications", headers=vulnerability_context.headers
    )
    assert notifications.status_code == 200
    notification = notifications.json()["items"][0]
    assert manual_identifier in notification["metadata"]["identifiers"]
    assert notification["service_name"] == "NGINX"

    disabled = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}/cpe",
        headers=vulnerability_context.headers,
        json={"enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["cpe_enabled"] is False
    assert disabled.json()["cpe_uri"] is None
    blocked = vulnerability_context.client.post(
        f"/v1/services/{vulnerability_context.service_id}/check",
        headers=vulnerability_context.headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "AUTOMATIC_CHECK_DISABLED"
    active = vulnerability_context.client.get(
        f"/v1/services/{vulnerability_context.service_id}/vulnerabilities",
        headers=vulnerability_context.headers,
    ).json()
    assert [item["cve_id"] for item in active] == [manual_identifier]

    missing = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}/cpe",
        headers=vulnerability_context.headers,
        json={
            "enabled": True,
            "cpe_uri": "cpe:2.3:a:missing:product:1.0:*:*:*:*:*:*:*",
        },
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "CPE_NOT_FOUND"

    cpe_uri = "cpe:2.3:a:f5:nginx:*:*:*:*:*:*:*:*"
    replaced = vulnerability_context.client.patch(
        f"/v1/services/{vulnerability_context.service_id}/cpe",
        headers=vulnerability_context.headers,
        json={"enabled": True, "cpe_uri": cpe_uri},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["cpe_enabled"] is True
    assert replaced.json()["cpe_uri"] == cpe_uri
    assert replaced.json()["cpe_match_method"] == "manual"

    platform_id = replaced.json()["platform_id"]
    history = vulnerability_context.client.get(
        f"/v1/platforms/{platform_id}/history",
        headers=vulnerability_context.headers,
    ).json()
    actions = {item["action"] for item in history["items"]}
    assert {"vulnerability.create.manual", "cpe.disable", "cpe.replace"}.issubset(actions)
