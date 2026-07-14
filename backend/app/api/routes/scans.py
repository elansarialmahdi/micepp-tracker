from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import require_permissions
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.models.scan import ScanJob
from app.models.service import Category, Service, ServiceSource
from app.repositories.platforms import get_platform
from app.schemas.scan import ScanConfirmRequest, ScanConfirmResponse, ScanCreate, ScanJobResponse
from app.services.audit import record_audit, request_audit_context
from app.services.automatic_checks import enqueue_service_checks
from app.services.inventory import normalized_name, normalized_version
from app.services.rate_limit import enforce_expensive_limit
from app.services.scan_security import ScanTargetRejected, validate_scan_target
from app.services.scans import execute_scan

router = APIRouter(prefix="/v1", tags=["scans"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
Scanner = Annotated[User, Depends(require_permissions("platform.scan"))]


async def required_scan(db: AsyncSession, scan_id: UUID) -> ScanJob:
    job = await db.scalar(
        select(ScanJob).options(selectinload(ScanJob.detections)).where(ScanJob.id == scan_id)
    )
    if job is None:
        raise AppError(404, "SCAN_NOT_FOUND", "Le scan est introuvable.")
    return job


@router.post(
    "/platforms/{platform_id}/scans",
    response_model=ScanJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def scans_create(
    platform_id: UUID,
    payload: ScanCreate,
    request: Request,
    db: DBSession,
    user: Scanner,
) -> ScanJob:
    settings = request.app.state.settings
    await enforce_expensive_limit(
        request,
        scope="scan-create",
        user_id=user.id,
        limit=settings.scan_create_rate_limit,
        window_seconds=settings.expensive_rate_window_seconds,
    )
    platform = await get_platform(db, platform_id)
    if platform is None:
        raise AppError(404, "PLATFORM_NOT_FOUND", "La plateforme est introuvable.")
    if platform.archived_at is not None:
        raise AppError(409, "PLATFORM_ARCHIVED", "Cette plateforme a été supprimée.")
    target = payload.target or platform.normalized_target
    target_type = payload.target_type
    if payload.target and target_type is None:
        try:
            ipaddress.ip_address(payload.target.strip())
            target_type = "ip"
        except ValueError:
            target_type = "url"
    target_type = target_type or platform.target_type
    if not target or target_type == "none":
        raise AppError(422, "SCAN_TARGET_REQUIRED", "Une cible URL ou IP est obligatoire.")
    active = await db.scalar(
        select(ScanJob.id).where(
            ScanJob.platform_id == platform_id, ScanJob.status.in_(["queued", "running"])
        )
    )
    if active:
        raise AppError(
            409, "SCAN_ALREADY_RUNNING", "Un scan est déjà en cours pour cette plateforme."
        )
    try:
        validated = await validate_scan_target(target, target_type, request.app.state.settings)
    except ScanTargetRejected as exc:
        raise AppError(422, exc.code, str(exc)) from exc
    job = ScanJob(
        platform_id=platform_id,
        requested_by=user.id,
        target=validated.value,
        target_type=validated.target_type,
        scan_type=payload.scan_type,
        status="queued",
        progress=0,
        current_step="en attente",
        authorization_confirmed=True,
        resolved_addresses=list(validated.addresses),
    )
    db.add(job)
    await db.flush()
    record_audit(
        db,
        actor_user_id=user.id,
        action="scan.request",
        entity_type="scan_job",
        entity_id=job.id,
        platform_id=platform_id,
        summary="Scan autorisé et demandé",
        metadata={"scan_type": payload.scan_type, "authorization_confirmed": True},
        **request_audit_context(request),
    )
    await db.commit()
    if request.app.state.settings.app_env == "test" or request.app.state.settings.scan_tasks_eager:
        await execute_scan(db, job, request.app.state.settings)
        await db.refresh(job, attribute_names=["detections"])
    else:
        from app.worker import execute_scan_task

        try:
            execute_scan_task.delay(str(job.id))
        except Exception as exc:
            job.status = "failed"
            job.error_code = "SCAN_QUEUE_UNAVAILABLE"
            job.sanitized_error = "Le worker de scan est temporairement indisponible."
            job.completed_at = datetime.now(UTC)
            await db.commit()
            raise AppError(
                503, "SCAN_QUEUE_UNAVAILABLE", "Le worker de scan est indisponible."
            ) from exc
    return await required_scan(db, job.id)


@router.get("/scans/{scan_id}", response_model=ScanJobResponse)
async def scans_show(scan_id: UUID, db: DBSession, _user: Scanner) -> ScanJob:
    return await required_scan(db, scan_id)


@router.post("/scans/{scan_id}/cancel", response_model=ScanJobResponse)
async def scans_cancel(scan_id: UUID, request: Request, db: DBSession, user: Scanner) -> ScanJob:
    job = await required_scan(db, scan_id)
    if job.status not in {"queued", "running"}:
        raise AppError(409, "SCAN_NOT_CANCELLABLE", "Ce scan ne peut plus être annulé.")
    job.status = "cancelled"
    job.current_step = "annulé"
    job.completed_at = datetime.now(UTC)
    record_audit(
        db,
        actor_user_id=user.id,
        action="scan.cancel",
        entity_type="scan_job",
        entity_id=job.id,
        platform_id=job.platform_id,
        summary="Scan annulé",
        **request_audit_context(request),
    )
    await db.commit()
    return job


@router.post("/scans/{scan_id}/confirm", response_model=ScanConfirmResponse)
async def scans_confirm(
    scan_id: UUID,
    payload: ScanConfirmRequest,
    request: Request,
    db: DBSession,
    user: Scanner,
) -> ScanConfirmResponse:
    job = await required_scan(db, scan_id)
    if job.status != "succeeded" or job.platform_id is None:
        raise AppError(409, "SCAN_RESULTS_NOT_READY", "Les résultats ne sont pas confirmables.")
    if job.current_step == "résultats confirmés":
        raise AppError(409, "SCAN_ALREADY_CONFIRMED", "Ces résultats ont déjà été confirmés.")
    by_id = {item.id: item for item in job.detections}
    if any(item.detected_service_id not in by_id for item in payload.items):
        raise AppError(422, "SCAN_RESULT_INVALID", "Un résultat ne correspond pas à ce scan.")
    category_names = {
        normalized_name(item.category): item.category.strip()
        for item in payload.items
        if item.selected and item.category and item.category.strip()
    }
    categories = {
        category.normalized_name: category
        for category in (
            await db.scalars(select(Category).where(Category.archived_at.is_(None)))
        ).all()
    }
    categories_created = 0
    for key, name in category_names.items():
        if key not in categories:
            category = Category(
                name=name,
                normalized_name=key,
                description=None,
            )
            db.add(category)
            categories[key] = category
            categories_created += 1
    await db.flush()
    existing = {
        (service.normalized_name, service.normalized_version)
        for service in (
            await db.scalars(
                select(Service).where(
                    Service.platform_id == job.platform_id, Service.archived_at.is_(None)
                )
            )
        ).all()
    }
    created = skipped = 0
    new_services: list[Service] = []
    seen: set[tuple[str, str | None]] = set()
    for item in payload.items:
        detection = by_id[item.detected_service_id]
        detection.selected_for_import = item.selected
        if not item.selected:
            skipped += 1
            continue
        key = (normalized_name(item.name), normalized_version(item.version))
        if key in existing or key in seen:
            skipped += 1
            continue
        seen.add(key)
        category = categories.get(normalized_name(item.category)) if item.category else None
        service = Service(
            platform_id=job.platform_id,
            category=category,
            category_id=category.id if category else None,
            name=item.name.strip(),
            normalized_name=key[0],
            vendor=detection.detected_vendor,
            product=detection.detected_product,
            version=item.version.strip() if item.version else None,
            normalized_version=key[1],
            cpe_uri=detection.detected_cpe,
            cpe_match_confidence=detection.confidence if detection.detected_cpe else None,
            cpe_match_method="scan" if detection.detected_cpe else None,
            source=ServiceSource.SCAN.value,
            source_details={
                "scan_job_id": str(job.id),
                "detector": detection.source_detector,
                "port": detection.port,
                "protocol": detection.protocol,
            },
            created_by=user.id,
        )
        db.add(service)
        new_services.append(service)
        created += 1
    platform = await get_platform(db, job.platform_id)
    if platform:
        platform.last_inventory_scan_at = job.completed_at or datetime.now(UTC)
    job.current_step = "résultats confirmés"
    record_audit(
        db,
        actor_user_id=user.id,
        action="scan.confirm",
        entity_type="scan_job",
        entity_id=job.id,
        platform_id=job.platform_id,
        summary=f"Résultats du scan confirmés : {created} service(s) ajouté(s)",
        metadata={"created": created, "skipped": skipped},
        **request_audit_context(request),
    )
    await db.commit()
    enqueue_service_checks([service.id for service in new_services], request.app.state.settings)
    return ScanConfirmResponse(
        created=created, skipped=skipped, categories_created=categories_created
    )
