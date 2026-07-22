from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import require_permissions
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.service import Service
from app.models.vulnerability import CPECandidate, ServiceVulnerability, Vulnerability
from app.schemas.service import ServiceResponse
from app.schemas.vulnerability import (
    CheckResponse,
    CPECandidateResponse,
    CPEUpdateRequest,
    IgnoreRequest,
    ManualVulnerabilityCreate,
    VulnerabilityDetail,
    VulnerabilitySummary,
)
from app.services.audit import record_audit, request_audit_context
from app.services.nvd_client import NVDClient
from app.services.rate_limit import enforce_expensive_limit
from app.services.vulnerabilities import (
    _sync_service_threat_notification,
    check_service,
    parse_cpe,
)

router = APIRouter(prefix="/v1", tags=["vulnerabilities"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
Reader = Annotated[User, Depends(require_permissions("service.read"))]
Checker = Annotated[User, Depends(require_permissions("service.scan"))]


async def required_service(db: AsyncSession, service_id: UUID) -> Service:
    service = await db.scalar(
        select(Service).where(Service.id == service_id).options(selectinload(Service.platform))
    )
    if service is None:
        raise AppError(404, "SERVICE_NOT_FOUND", "Le service demandé est introuvable.")
    if service.archived_at:
        raise AppError(409, "SERVICE_ARCHIVED", "Ce service a été supprimé.")
    return service


def summary(link: ServiceVulnerability) -> dict:
    item = link.vulnerability
    return {
        "link_id": link.id,
        "service_id": link.service_id,
        "vulnerability_id": item.id,
        "cve_id": item.cve_id,
        "title": item.title,
        "description": item.description,
        "severity": item.severity,
        "cvss_score": item.cvss_score,
        "cvss_version": item.cvss_version,
        "published_at": item.published_at,
        "modified_at": item.modified_at,
        "match_state": link.match_state,
        "match_reason": link.match_reason,
        "confidence": link.confidence,
        "detected_at": link.detected_at,
        "last_seen_at": link.last_seen_at,
        "resolved_at": link.resolved_at,
        "ignored_at": link.ignored_at,
        "ignore_reason": link.ignore_reason,
    }


@router.post("/services/{service_id}/check", response_model=CheckResponse)
async def check(service_id: UUID, request: Request, db: DBSession, user: Checker) -> dict:
    settings: Settings = request.app.state.settings
    await enforce_expensive_limit(
        request,
        scope="service-check",
        user_id=user.id,
        limit=settings.manual_service_check_rate_limit,
        window_seconds=settings.expensive_rate_window_seconds,
    )
    service = await required_service(db, service_id)
    if not service.cpe_enabled:
        raise AppError(
            409,
            "AUTOMATIC_CHECK_DISABLED",
            "La détection automatique est désactivée pour ce service.",
        )
    try:
        result = await check_service(db, service, settings)
    except Exception as exc:
        await db.rollback()
        raise AppError(
            503,
            "VULNERABILITY_SOURCE_UNAVAILABLE",
            "Les sources OSV/NVD sont temporairement indisponibles. Réessayez plus tard.",
        ) from exc
    record_audit(
        db,
        actor_user_id=user.id,
        action="vulnerability.check",
        entity_type="service",
        entity_id=service.id,
        platform_id=service.platform_id,
        summary=f"Vérification de sécurité de {service.name}",
        after_data=result,
        **request_audit_context(request),
    )
    await db.commit()
    return result


@router.get("/services/{service_id}/cpe-candidates", response_model=list[CPECandidateResponse])
async def candidates(service_id: UUID, db: DBSession, _user: Reader) -> list[CPECandidate]:
    await required_service(db, service_id)
    return list(
        (
            await db.scalars(
                select(CPECandidate)
                .where(CPECandidate.service_id == service_id)
                .order_by(CPECandidate.score.desc())
            )
        ).all()
    )


@router.post(
    "/services/{service_id}/cpe-candidates/{candidate_id}/select",
    response_model=CPECandidateResponse,
)
async def select_candidate(
    service_id: UUID, candidate_id: UUID, request: Request, db: DBSession, user: Checker
) -> CPECandidate:
    service = await required_service(db, service_id)
    candidate = await db.get(CPECandidate, candidate_id)
    if candidate is None or candidate.service_id != service_id:
        raise AppError(404, "CPE_CANDIDATE_NOT_FOUND", "Le candidat CPE est introuvable.")
    for item in (
        await db.scalars(select(CPECandidate).where(CPECandidate.service_id == service_id))
    ).all():
        item.selected = item.id == candidate.id
    service.cpe_uri, service.cpe_match_confidence, service.cpe_match_method = (
        candidate.cpe_uri,
        candidate.score,
        "manual",
    )
    service.cpe_enabled = True
    record_audit(
        db,
        actor_user_id=user.id,
        action="cpe.select",
        entity_type="service",
        entity_id=service.id,
        platform_id=service.platform_id,
        summary=f"CPE validé pour {service.name}",
        after_data={"cpe_uri": candidate.cpe_uri},
        **request_audit_context(request),
    )
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.get("/services/{service_id}/vulnerabilities", response_model=list[VulnerabilitySummary])
async def service_vulnerabilities(
    service_id: UUID,
    db: DBSession,
    _user: Reader,
    view: Literal["active", "history"] = Query(default="active"),
) -> list[dict]:
    await required_service(db, service_id)
    state_filters = (
        (
            ServiceVulnerability.resolved_at.is_(None),
            ServiceVulnerability.ignored_at.is_(None),
            ServiceVulnerability.match_state.in_(("confirmed", "probable")),
        )
        if view == "active"
        else (
            (ServiceVulnerability.resolved_at.is_not(None))
            | (ServiceVulnerability.ignored_at.is_not(None)),
        )
    )
    links = (
        await db.scalars(
            select(ServiceVulnerability)
            .where(
                ServiceVulnerability.service_id == service_id,
                *state_filters,
            )
            .options(selectinload(ServiceVulnerability.vulnerability))
            .order_by(ServiceVulnerability.detected_at.desc())
        )
    ).all()
    return [summary(link) for link in links]


@router.patch("/services/{service_id}/cpe", response_model=ServiceResponse)
async def update_service_cpe(
    service_id: UUID,
    payload: CPEUpdateRequest,
    request: Request,
    db: DBSession,
    user: Checker,
) -> Service:
    service = await required_service(db, service_id)
    before = {
        "enabled": service.cpe_enabled,
        "cpe_uri": service.cpe_uri,
        "method": service.cpe_match_method,
    }
    now = datetime.now(UTC)

    if not payload.enabled:
        links = (
            await db.scalars(
                select(ServiceVulnerability)
                .where(
                    ServiceVulnerability.service_id == service.id,
                    ServiceVulnerability.resolved_at.is_(None),
                )
                .options(selectinload(ServiceVulnerability.vulnerability))
            )
        ).all()
        for link in links:
            if not (link.affected_configuration or {}).get("manual"):
                link.resolved_at = now
        service.cpe_enabled = False
        service.cpe_uri = None
        service.cpe_match_confidence = None
        service.cpe_match_method = None
        service.last_checked_at = None
        details = dict(service.source_details or {})
        details["security_identity"] = {"status": "disabled", "source": None}
        service.source_details = details
        for candidate in (
            await db.scalars(select(CPECandidate).where(CPECandidate.service_id == service.id))
        ).all():
            candidate.selected = False
        action = "cpe.disable"
        audit_summary = f"Détection automatique désactivée pour {service.name}"
    elif payload.cpe_uri:
        vendor, product, version = parse_cpe(payload.cpe_uri)
        if not payload.cpe_uri.startswith("cpe:2.3:") or not all((vendor, product, version)):
            raise AppError(422, "CPE_INVALID", "Le CPE saisi n’est pas un CPE 2.3 valide.")
        try:
            exists = await NVDClient(request.app.state.settings, db).cpe_exists(payload.cpe_uri)
        except Exception as exc:
            raise AppError(
                503,
                "CPE_VERIFICATION_UNAVAILABLE",
                "La NVD ne permet pas de vérifier ce CPE pour le moment.",
            ) from exc
        if not exists:
            raise AppError(422, "CPE_NOT_FOUND", "Ce CPE n’existe pas dans la NVD.")
        links = (
            await db.scalars(
                select(ServiceVulnerability)
                .where(
                    ServiceVulnerability.service_id == service.id,
                    ServiceVulnerability.resolved_at.is_(None),
                )
                .options(selectinload(ServiceVulnerability.vulnerability))
            )
        ).all()
        for link in links:
            if not (link.affected_configuration or {}).get("manual"):
                link.resolved_at = now
        service.cpe_enabled = True
        service.cpe_uri = payload.cpe_uri
        service.cpe_match_confidence = 1.0
        service.cpe_match_method = "manual"
        service.last_checked_at = None
        details = dict(service.source_details or {})
        details["security_identity"] = {
            "status": "verified",
            "source": "NVD (CPE manuel)",
            "package": product,
            "version": version,
        }
        service.source_details = details
        for candidate in (
            await db.scalars(select(CPECandidate).where(CPECandidate.service_id == service.id))
        ).all():
            candidate.selected = candidate.cpe_uri == payload.cpe_uri
        action = "cpe.replace"
        audit_summary = f"CPE remplacé manuellement pour {service.name}"
    else:
        service.cpe_enabled = True
        service.last_checked_at = None
        action = "cpe.enable"
        audit_summary = f"Détection automatique réactivée pour {service.name}"

    record_audit(
        db,
        actor_user_id=user.id,
        action=action,
        entity_type="service",
        entity_id=service.id,
        platform_id=service.platform_id,
        summary=audit_summary,
        before_data=before,
        after_data={
            "enabled": service.cpe_enabled,
            "cpe_uri": service.cpe_uri,
            "method": service.cpe_match_method,
        },
        **request_audit_context(request),
    )
    await db.commit()
    await db.refresh(service)
    return service


@router.post(
    "/services/{service_id}/vulnerabilities/manual",
    response_model=VulnerabilitySummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_vulnerability(
    service_id: UUID,
    payload: ManualVulnerabilityCreate,
    request: Request,
    db: DBSession,
    user: Checker,
) -> dict:
    service = await required_service(db, service_id)
    if payload.reference_url and not payload.reference_url.startswith(("https://", "http://")):
        raise AppError(422, "REFERENCE_INVALID", "La référence doit être une URL HTTP(S).")
    now = datetime.now(UTC)
    identifier = payload.identifier or f"MANUEL-{uuid4().hex[:8].upper()}"
    vulnerability = await db.scalar(
        select(Vulnerability).where(Vulnerability.cve_id == identifier)
    )
    if vulnerability is None:
        vulnerability = Vulnerability(
            cve_id=identifier,
            title=payload.title or "Vulnérabilité manuelle",
            description=payload.description,
            source="Manuel",
            severity=payload.severity or "unknown",
            cvss_score=payload.cvss_score,
            cvss_version="manuel" if payload.cvss_score is not None else None,
            metrics={},
            weaknesses=[],
            references=[payload.reference_url] if payload.reference_url else [],
            raw_payload={"manual": True},
            last_sync_at=now,
        )
        db.add(vulnerability)
        await db.flush()
    link = await db.scalar(
        select(ServiceVulnerability).where(
            ServiceVulnerability.service_id == service.id,
            ServiceVulnerability.vulnerability_id == vulnerability.id,
        )
    )
    if link is None:
        link = ServiceVulnerability(
            service_id=service.id,
            vulnerability_id=vulnerability.id,
            match_state="confirmed",
            match_reason="Vulnérabilité ajoutée manuellement.",
            confidence=1.0,
            affected_configuration={"manual": True},
        )
        db.add(link)
    else:
        link.match_state = "confirmed"
        link.match_reason = "Vulnérabilité réactivée manuellement."
        link.confidence = 1.0
        link.affected_configuration = {"manual": True}
        link.resolved_at = None
        link.ignored_at = None
        link.ignored_by = None
        link.ignore_reason = None
        link.last_seen_at = now
    await db.flush()
    await db.refresh(link, attribute_names=["vulnerability"])
    await _sync_service_threat_notification(db, service, now, has_new_findings=True)
    record_audit(
        db,
        actor_user_id=user.id,
        action="vulnerability.create.manual",
        entity_type="service_vulnerability",
        entity_id=link.id,
        platform_id=service.platform_id,
        summary=f"Vulnérabilité manuelle ajoutée à {service.name} : {identifier}",
        after_data={
            "identifier": identifier,
            "severity": payload.severity or "unknown",
            "source": "Manuel",
        },
        **request_audit_context(request),
    )
    await db.commit()
    return summary(link)


@router.get("/service-vulnerabilities/{link_id}", response_model=VulnerabilityDetail)
async def vulnerability_detail(link_id: UUID, db: DBSession, _user: Reader) -> dict:
    link = await db.scalar(
        select(ServiceVulnerability)
        .where(ServiceVulnerability.id == link_id)
        .options(selectinload(ServiceVulnerability.vulnerability))
    )
    if link is None:
        raise AppError(404, "VULNERABILITY_NOT_FOUND", "La vulnérabilité demandée est introuvable.")
    item = summary(link)
    item.update(
        source=link.vulnerability.source,
        metrics=link.vulnerability.metrics,
        weaknesses=link.vulnerability.weaknesses,
        references=link.vulnerability.references,
        affected_configuration=link.affected_configuration,
        last_sync_at=link.vulnerability.last_sync_at,
    )
    return item


@router.patch("/service-vulnerabilities/{link_id}/ignore", response_model=VulnerabilitySummary)
async def ignore_vulnerability(
    link_id: UUID, payload: IgnoreRequest, request: Request, db: DBSession, user: Checker
) -> dict:
    link = await db.scalar(
        select(ServiceVulnerability)
        .where(ServiceVulnerability.id == link_id)
        .options(selectinload(ServiceVulnerability.vulnerability))
    )
    if link is None:
        raise AppError(404, "VULNERABILITY_NOT_FOUND", "La vulnérabilité demandée est introuvable.")
    service = await required_service(db, link.service_id)
    link.ignored_at = datetime.now(UTC) if payload.ignored else None
    link.ignored_by = user.id if payload.ignored else None
    link.ignore_reason = payload.reason if payload.ignored else None
    if not payload.ignored:
        link.resolved_at = None
        link.match_state = "confirmed"
        link.match_reason = "Vulnérabilité réactivée manuellement."
        link.confidence = 1.0
        link.last_seen_at = datetime.now(UTC)
    await _sync_service_threat_notification(
        db,
        service,
        datetime.now(UTC),
        has_new_findings=not payload.ignored,
    )
    record_audit(
        db,
        actor_user_id=user.id,
        action="vulnerability.ignore" if payload.ignored else "vulnerability.restore",
        entity_type="service_vulnerability",
        entity_id=link.id,
        platform_id=service.platform_id,
        summary=(
            f"Vulnérabilité {link.vulnerability.cve_id} ignorée pour le service {service.name}"
            if payload.ignored
            else (
                f"Vulnérabilité {link.vulnerability.cve_id} réactivée "
                f"pour le service {service.name}"
            )
        ),
        after_data={"ignored": payload.ignored, "reason": payload.reason},
        **request_audit_context(request),
    )
    await db.commit()
    return summary(link)
