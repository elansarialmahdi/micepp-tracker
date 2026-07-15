from __future__ import annotations

import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from packaging.version import InvalidVersion, Version
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.service import Service
from app.models.vulnerability import CPECandidate, MatchState, ServiceVulnerability, Vulnerability
from app.services.audit import create_notification
from app.services.nvd_client import NVDClient
from app.services.osv_client import OSVClient, PackageIdentity


def clean(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def parse_cpe(uri: str) -> tuple[str, str, str]:
    parts = uri.split(":")
    return (parts[3], parts[4], parts[5]) if len(parts) > 5 else ("", "", "")


def cpe_update(uri: str) -> str:
    parts = uri.split(":")
    return parts[6] if len(parts) > 6 else ""


def _parsed_version(value: str | None) -> Version | None:
    if not value:
        return None
    try:
        return Version(value)
    except InvalidVersion:
        # Certains éditeurs suffixent les versions dans les CPE (ex. 35.0.1.OS).
        numeric = re.search(r"\d+(?:\.\d+)+", value)
        if not numeric:
            return None
        try:
            return Version(numeric.group(0))
        except InvalidVersion:
            return None


def candidate_score(service: Service, uri: str) -> float:
    vendor, product, version = parse_cpe(uri)
    expected_vendor = service.vendor
    expected_product = service.product or service.name
    vendor_score = (
        SequenceMatcher(None, clean(expected_vendor), clean(vendor)).ratio()
        if expected_vendor
        else 1.0
    )
    product_score = SequenceMatcher(None, clean(expected_product), clean(product)).ratio()
    version_score = (
        1.0
        if version in {"*", "-", service.normalized_version}
        else SequenceMatcher(None, clean(service.version), clean(version)).ratio()
    )
    return round(vendor_score * 0.2 + product_score * 0.65 + version_score * 0.15, 3)


def _version_in_range(version: str | None, match: dict[str, Any]) -> bool | None:
    current = _parsed_version(version)
    if current is None:
        return None
    try:
        _, _, exact_version = parse_cpe(match.get("criteria", ""))
        parsed_exact = _parsed_version(exact_version)
        if exact_version not in {"", "*", "-"} and (
            parsed_exact is None or current != parsed_exact
        ):
            return False
        checks = (
            ("versionStartIncluding", lambda x: current >= x),
            ("versionStartExcluding", lambda x: current > x),
            ("versionEndIncluding", lambda x: current <= x),
            ("versionEndExcluding", lambda x: current < x),
        )
        bounds = [
            test(_parsed_version(match[key]))
            for key, test in checks
            if key in match and _parsed_version(match[key]) is not None
        ]
        return all(bounds)
    except InvalidVersion:
        return None


def applicability(
    cve: dict[str, Any], cpe_uri: str, version: str | None
) -> tuple[MatchState, float, str, dict[str, Any] | None]:
    if cve.get("vulnStatus", "").lower() == "rejected":
        return MatchState.NOT_AFFECTED, 1.0, "La CVE a été rejetée par la NVD.", None
    target_vendor, target_product, _ = parse_cpe(cpe_uri)
    matches: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for match in value.get("cpeMatch", []):
                vendor, product, _ = parse_cpe(match.get("criteria", ""))
                if clean(vendor) == clean(target_vendor) and clean(product) == clean(
                    target_product
                ):
                    matches.append(match)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(cve.get("configurations", []))
    vulnerable = [match for match in matches if match.get("vulnerable")]
    if not vulnerable:
        return (
            MatchState.NOT_AFFECTED,
            0.95,
            "La configuration NVD ne marque pas ce produit comme vulnérable.",
            matches[0] if matches else None,
        )
    verdicts = [(_version_in_range(version, match), match) for match in vulnerable]
    if any(verdict is True for verdict, _ in verdicts):
        match = next(match for verdict, match in verdicts if verdict is True)
        return (
            MatchState.CONFIRMED,
            0.98,
            "Le CPE et la plage de versions NVD correspondent.",
            match,
        )
    if all(verdict is False for verdict, _ in verdicts):
        return (
            MatchState.NOT_AFFECTED,
            0.98,
            "La version est hors des plages affectées publiées par la NVD.",
            vulnerable[0],
        )
    return (
        MatchState.PROBABLE,
        0.75,
        "Le produit correspond, mais la version ne permet pas une confirmation stricte.",
        vulnerable[0],
    )


def _cna_version_applies(current_value: str | None, item: dict[str, Any]) -> bool | None:
    if str(item.get("status", "")).lower() != "affected":
        return False
    current = _parsed_version(current_value)
    if current is None:
        return None
    start_value = str(item.get("version", ""))
    start = _parsed_version(start_value)
    end_excluding = _parsed_version(item.get("lessThan"))
    end_including = _parsed_version(item.get("lessThanOrEqual"))
    if end_excluding is not None or end_including is not None:
        if start is not None and current < start:
            return False
        if end_excluding is not None and current >= end_excluding:
            return False
        if end_including is not None and current > end_including:
            return False
        return True
    if start_value.lower() in {"", "*", "n/a", "unknown"}:
        return None
    return start is not None and current == start


def cna_applicability(
    record: dict[str, Any], cpe_uri: str, version: str | None
) -> tuple[MatchState, float, str, dict[str, Any] | None] | None:
    target_vendor, target_product, _ = parse_cpe(cpe_uri)
    containers = record.get("containers", {})
    sources = [containers.get("cna", {})]
    sources.extend(containers.get("adp", []))
    product_matched = False
    verdicts: list[tuple[bool | None, dict[str, Any]]] = []
    for source in sources:
        for affected in source.get("affected", []):
            product = str(affected.get("product", ""))
            vendor = str(affected.get("vendor", ""))
            cpe_match = any(
                clean(parse_cpe(uri)[0]) == clean(target_vendor)
                and clean(parse_cpe(uri)[1]) == clean(target_product)
                for uri in affected.get("cpes", [])
            )
            product_match = clean(product) == clean(target_product)
            vendor_match = vendor.lower() in {"", "n/a", "unknown"} or (
                clean(vendor) == clean(target_vendor)
            )
            if not cpe_match and not (product_match and vendor_match):
                continue
            product_matched = True
            versions = affected.get("versions", [])
            if not versions and str(affected.get("defaultStatus", "")).lower() == "affected":
                verdicts.append((True, affected))
            verdicts.extend((_cna_version_applies(version, item), affected) for item in versions)
    if any(verdict is True for verdict, _ in verdicts):
        affected = next(item for verdict, item in verdicts if verdict is True)
        return (
            MatchState.CONFIRMED,
            0.99,
            "Le produit et la version correspondent aux données officielles du CNA.",
            affected,
        )
    if product_matched and verdicts and all(verdict is False for verdict, _ in verdicts):
        return (
            MatchState.NOT_AFFECTED,
            0.98,
            "La version est hors des versions affectées déclarées par le CNA.",
            verdicts[0][1],
        )
    if product_matched and any(verdict is None for verdict, _ in verdicts):
        return (
            MatchState.PROBABLE,
            0.75,
            "Le produit correspond au CNA, mais sa plage de versions est imprécise.",
            verdicts[0][1],
        )
    return None


def _cna_cvss(record: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    cna = record.get("containers", {}).get("cna", {})
    for metric in cna.get("metrics", []):
        for key in ("cvssV4_0", "cvssV3_1", "cvssV3_0", "cvssV2_0"):
            data = metric.get(key)
            if data:
                return data.get("baseScore"), data.get("version"), data.get("baseSeverity")
    return None, None, None


def _date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _english(items: list[dict[str, Any]]) -> str:
    return next(
        (item.get("value", "") for item in items if item.get("lang") == "en"),
        items[0].get("value", "") if items else "",
    )


def _cvss(cve: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        if metrics.get(key):
            data = metrics[key][0].get("cvssData", {})
            return (
                data.get("baseScore"),
                data.get("version"),
                data.get("baseSeverity") or metrics[key][0].get("baseSeverity"),
            )
    return None, None, None


def _security_identity(service: Service, **values: Any) -> None:
    details = dict(service.source_details or {})
    details["security_identity"] = values
    service.source_details = details


def _osv_identifier(item: dict[str, Any]) -> str | None:
    return next(
        (alias for alias in item.get("aliases", []) if str(alias).startswith("CVE-")),
        item.get("id"),
    )


async def _check_osv(
    db: AsyncSession,
    service: Service,
    client: OSVClient,
    identity: PackageIdentity,
    now: datetime,
) -> dict[str, Any]:
    payloads = await client.vulnerabilities(identity)
    seen: set[Any] = set()
    new_threats = 0
    for item in payloads:
        identifier = _osv_identifier(item)
        if not identifier:
            continue
        vulnerability = await db.scalar(
            select(Vulnerability).where(Vulnerability.cve_id == identifier)
        )
        if vulnerability is None:
            vulnerability = Vulnerability(cve_id=identifier, description="")
            db.add(vulnerability)
            await db.flush()
        database_specific = item.get("database_specific", {})
        severity = str(database_specific.get("severity") or "unknown").lower()
        vulnerability.title = item.get("summary") or identifier
        vulnerability.description = item.get("details") or item.get("summary") or identifier
        vulnerability.published_at = _date(item.get("published"))
        vulnerability.modified_at = _date(item.get("modified"))
        vulnerability.severity = severity
        vulnerability.cvss_score = None
        vulnerability.cvss_version = None
        vulnerability.metrics = {"severity": item.get("severity", [])}
        vulnerability.weaknesses = database_specific.get("cwe_ids", [])
        vulnerability.references = [
            {"url": reference.get("url"), "source": reference.get("type") or "OSV"}
            for reference in item.get("references", [])
            if str(reference.get("url", "")).startswith(("https://", "http://"))
        ]
        vulnerability.source = "OSV"
        vulnerability.raw_payload = item
        vulnerability.last_sync_at = now
        link = await db.scalar(
            select(ServiceVulnerability).where(
                ServiceVulnerability.service_id == service.id,
                ServiceVulnerability.vulnerability_id == vulnerability.id,
            )
        )
        is_new = link is None or link.resolved_at is not None
        if link is None:
            link = ServiceVulnerability(
                service_id=service.id,
                vulnerability_id=vulnerability.id,
                match_state=MatchState.CONFIRMED.value,
                match_reason="Le paquet et la version correspondent exactement dans OSV.",
                confidence=1.0,
            )
            db.add(link)
        link.match_state = MatchState.CONFIRMED.value
        link.match_reason = "Le paquet et la version correspondent exactement dans OSV."
        link.confidence = 1.0
        link.affected_configuration = next(
            (
                affected
                for affected in item.get("affected", [])
                if affected.get("package", {}).get("name", "").lower() == identity.name.lower()
            ),
            None,
        )
        link.last_seen_at, link.resolved_at = now, None
        seen.add(vulnerability.id)
        if is_new:
            new_threats += 1
            create_notification(
                db,
                type="vulnerability.detected",
                title=f"Menace sur {service.name}",
                message=(
                    f"{service.name} {service.version} est affecté selon OSV "
                    f"({identity.ecosystem}:{identity.name})."
                ),
                severity=severity if severity in {"critical", "high", "medium", "low"} else "info",
                platforms=[service.platform],
                service_id=service.id,
                vulnerability_id=vulnerability.id,
                metadata={"identifier": identifier, "source": "OSV"},
            )
    return {
        "seen": seen,
        "new_notifications": new_threats,
    }


async def check_service(db: AsyncSession, service: Service, settings: Settings) -> dict[str, Any]:
    now = datetime.now(UTC)
    osv_client = OSVClient(settings)
    detector = str((service.source_details or {}).get("detector", "")).lower()
    if detector == "nmap":
        package_identity, package_status = None, "not_applicable"
    else:
        package_identity, package_status = await osv_client.resolve_package(
            service.name, service.product, service.version
        )
    seen: set[Any] = set()
    osv_seen: set[Any] = set()
    new_threats = 0
    if package_identity is not None:
        osv_result = await _check_osv(db, service, osv_client, package_identity, now)
        osv_seen = set(osv_result["seen"])
        seen.update(osv_seen)
        new_threats += osv_result["new_notifications"]
        _security_identity(
            service,
            status="verified",
            source="OSV+NVD",
            ecosystem=package_identity.ecosystem,
            package=package_identity.name,
            version=package_identity.version,
        )
    else:
        _security_identity(
            service,
            status=package_status,
            source="OSV" if package_status != "not_applicable" else None,
            package=(service.product or service.name).lower(),
            version=service.version,
        )
    client = NVDClient(settings, db)
    search_terms: list[str] = []
    for value in (service.vendor, service.product, service.name):
        if value and clean(value) not in {clean(term) for term in search_terms}:
            search_terms.append(value)
    keyword = " ".join(search_terms)
    raw_candidates = await client.search_cpes(keyword)
    await db.execute(delete(CPECandidate).where(CPECandidate.service_id == service.id))
    candidates: list[CPECandidate] = []
    family_evidence: list[tuple[str, str, dict[str, Any]]] = []
    for raw in raw_candidates:
        uri = raw.get("cpeName", "")
        if not uri or raw.get("deprecated") is True:
            continue
        row = await db.scalar(
            select(CPECandidate).where(
                CPECandidate.service_id == service.id, CPECandidate.cpe_uri == uri
            )
        )
        vendor, product, version = parse_cpe(uri)
        product_similarity = SequenceMatcher(
            None, clean(service.product or service.name), clean(product)
        ).ratio()
        if service.product is None and clean(product) != clean(service.name):
            continue
        if service.product is not None and product_similarity < 0.82:
            continue
        family_evidence.append((vendor, product, raw))
        if service.version and version not in {"", "*", "-", service.normalized_version}:
            continue
        if row is None:
            row = CPECandidate(service_id=service.id, cpe_uri=uri, score=0, method="nvd_keyword")
            db.add(row)
        row.title = next(
            (x.get("title") for x in raw.get("titles", []) if x.get("lang") in {None, "en"}), None
        )
        row.vendor, row.product, row.version = vendor, product, version
        row.score, row.raw_payload, row.last_checked_at = candidate_score(service, uri), raw, now
        candidates.append(row)
    if not candidates and family_evidence and package_identity is None:
        family_counts: dict[tuple[str, str], int] = {}
        for vendor, product, _ in family_evidence:
            key = (vendor, product)
            family_counts[key] = family_counts.get(key, 0) + 1
        vendor, product = max(family_counts, key=lambda key: family_counts[key])
        family_uri = f"cpe:2.3:a:{vendor}:{product}:*:*:*:*:*:*:*:*"
        family_row = CPECandidate(
            service_id=service.id,
            cpe_uri=family_uri,
            title=f"{service.product or service.name} (famille de produit)",
            vendor=vendor,
            product=product,
            version="*",
            score=candidate_score(service, family_uri),
            method="nvd_keyword_family",
            raw_payload={"evidence_count": family_counts[(vendor, product)]},
            last_checked_at=now,
        )
        db.add(family_row)
        candidates.append(family_row)
    candidates.sort(
        key=lambda item: (
            clean(item.version) == clean(service.version),
            cpe_update(item.cpe_uri) in {"", "-", "*"},
            clean(item.product) == clean(service.product or service.name),
            item.score,
        ),
        reverse=True,
    )
    automatically_managed = (service.cpe_match_method or "").startswith("nvd_auto")
    if service.cpe_uri and automatically_managed and not candidates:
        service.cpe_uri = None
        service.cpe_match_confidence = None
        service.cpe_match_method = None
    if candidates and (not service.cpe_uri or automatically_managed):
        for candidate in candidates:
            candidate.selected = False
        candidates[0].selected = True
        if candidates[0].method == "nvd_keyword_family":
            match_method = "nvd_auto_family"
        elif clean(candidates[0].version) == clean(service.version):
            match_method = "nvd_auto_exact"
        else:
            match_method = "nvd_auto"
        service.cpe_uri, service.cpe_match_confidence, service.cpe_match_method = (
            candidates[0].cpe_uri,
            candidates[0].score,
            match_method,
        )
        if package_identity is None:
            _security_identity(
                service,
                status="verified",
                source="NVD+CVE" if match_method == "nvd_auto_family" else "NVD",
                package=service.product or service.name,
                version=service.version,
            )
    if not service.cpe_uri:
        previous = (
            await db.scalars(
                select(ServiceVulnerability).where(
                    ServiceVulnerability.service_id == service.id,
                    ServiceVulnerability.resolved_at.is_(None),
                )
            )
        ).all()
        for link in previous:
            if link.vulnerability_id not in seen:
                link.resolved_at = now
        service.last_checked_at = now
        await db.commit()
        return {
            "status": "completed" if package_identity is not None else "needs_review",
            "source": "osv" if package_identity is not None else "nvd",
            "cpe_uri": None,
            "candidates": len(candidates),
            "active_vulnerabilities": len(seen),
            "new_notifications": new_threats,
        }
    payloads = (
        await client.cves_for_keyword(keyword)
        if service.cpe_match_method == "nvd_auto_family"
        else await client.cves_for_cpe(service.cpe_uri)
    )
    for wrapper in payloads:
        cve = wrapper.get("cve", wrapper)
        cve_id = cve.get("id")
        if not cve_id:
            continue
        state, confidence, reason, affected = applicability(cve, service.cpe_uri, service.version)
        cve_record = None
        if affected is None:
            cve_record = await client.cve_record(cve_id)
            cna_result = (
                cna_applicability(cve_record, service.cpe_uri, service.version)
                if cve_record
                else None
            )
            if cna_result is not None:
                state, confidence, reason, affected = cna_result
        vulnerability = await db.scalar(select(Vulnerability).where(Vulnerability.cve_id == cve_id))
        score, cvss_version, severity = _cvss(cve)
        if score is None and cve_record:
            score, cvss_version, severity = _cna_cvss(cve_record)
        if vulnerability is None:
            vulnerability = Vulnerability(cve_id=cve_id, description="")
            db.add(vulnerability)
            await db.flush()
        vulnerability.title = cve_id
        vulnerability.description = _english(cve.get("descriptions", []))
        vulnerability.published_at, vulnerability.modified_at = (
            _date(cve.get("published")),
            _date(cve.get("lastModified")),
        )
        vulnerability.cvss_score, vulnerability.cvss_version, vulnerability.severity = (
            score,
            cvss_version,
            (severity or "unknown").lower(),
        )
        vulnerability.metrics, vulnerability.weaknesses = (
            cve.get("metrics", {}),
            cve.get("weaknesses", []),
        )
        vulnerability.source = "NVD+CVE" if cve_record else "NVD"
        vulnerability.references = [
            {"url": item.get("url"), "source": item.get("source")}
            for item in cve.get("references", [])
            if str(item.get("url", "")).startswith(("https://", "http://"))
        ]
        vulnerability.raw_payload, vulnerability.last_sync_at = cve, now
        link = await db.scalar(
            select(ServiceVulnerability).where(
                ServiceVulnerability.service_id == service.id,
                ServiceVulnerability.vulnerability_id == vulnerability.id,
            )
        )
        applies_to_current_version = state in {MatchState.CONFIRMED, MatchState.PROBABLE}
        if not applies_to_current_version:
            if vulnerability.id in osv_seen:
                continue
            if link is not None:
                link.match_state, link.match_reason, link.confidence = (
                    state.value,
                    reason,
                    confidence,
                )
                link.affected_configuration = affected
                link.last_seen_at, link.resolved_at = now, now
            continue

        is_new = link is None or link.resolved_at is not None
        if link is None:
            link = ServiceVulnerability(
                service_id=service.id,
                vulnerability_id=vulnerability.id,
                match_state=state.value,
                match_reason=reason,
                confidence=confidence,
            )
            db.add(link)
        link.match_state, link.match_reason, link.confidence, link.affected_configuration = (
            state.value,
            reason,
            confidence,
            affected,
        )
        link.last_seen_at, link.resolved_at = now, None
        seen.add(vulnerability.id)
        if is_new:
            new_threats += 1
            create_notification(
                db,
                type="vulnerability.detected",
                title=f"Menace sur {service.name}",
                message=(
                    f"{service.name} {service.version} est potentiellement affecté : {reason}"
                ),
                severity=vulnerability.severity
                if vulnerability.severity in {"critical", "high", "medium", "low"}
                else "info",
                platforms=[service.platform],
                service_id=service.id,
                vulnerability_id=vulnerability.id,
                metadata={"cve_id": cve_id, "match_state": state.value},
            )
    previous = (
        await db.scalars(
            select(ServiceVulnerability).where(
                ServiceVulnerability.service_id == service.id,
                ServiceVulnerability.resolved_at.is_(None),
            )
        )
    ).all()
    for link in previous:
        if link.vulnerability_id not in seen:
            link.resolved_at = now
    service.last_checked_at = now
    await db.commit()
    return {
        "status": "completed",
        "source": "osv+nvd" if package_identity is not None else "nvd",
        "cpe_uri": service.cpe_uri,
        "candidates": len(candidates),
        "active_vulnerabilities": len(seen),
        "new_notifications": new_threats,
    }
