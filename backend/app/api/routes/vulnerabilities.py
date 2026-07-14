from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import require_permissions
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.service import Service
from app.models.vulnerability import CPECandidate, ServiceVulnerability
from app.schemas.vulnerability import (
    CheckResponse,
    CPECandidateResponse,
    IgnoreRequest,
    VulnerabilityDetail,
    VulnerabilitySummary,
)
from app.services.audit import record_audit, request_audit_context
from app.services.rate_limit import enforce_expensive_limit
from app.services.vulnerabilities import check_service

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
async def service_vulnerabilities(service_id: UUID, db: DBSession, _user: Reader) -> list[dict]:
    await required_service(db, service_id)
    links = (
        await db.scalars(
            select(ServiceVulnerability)
            .where(
                ServiceVulnerability.service_id == service_id,
                ServiceVulnerability.resolved_at.is_(None),
                ServiceVulnerability.ignored_at.is_(None),
                ServiceVulnerability.match_state.in_(("confirmed", "probable")),
            )
            .options(selectinload(ServiceVulnerability.vulnerability))
            .order_by(ServiceVulnerability.detected_at.desc())
        )
    ).all()
    return [summary(link) for link in links]


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
    link.ignored_at = datetime.now(UTC) if payload.ignored else None
    link.ignored_by = user.id if payload.ignored else None
    link.ignore_reason = payload.reason if payload.ignored else None
    record_audit(
        db,
        actor_user_id=user.id,
        action="vulnerability.ignore" if payload.ignored else "vulnerability.restore",
        entity_type="service_vulnerability",
        entity_id=link.id,
        summary=f"Décision sur {link.vulnerability.cve_id}",
        after_data={"ignored": payload.ignored, "reason": payload.reason},
        **request_audit_context(request),
    )
    await db.commit()
    return summary(link)
