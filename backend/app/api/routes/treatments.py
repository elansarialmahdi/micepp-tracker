from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import require_permissions
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import Role, User
from app.models.service import Service
from app.models.treatment import TreatmentStatus, VulnerabilityTreatment
from app.models.vulnerability import CPECandidate, ServiceVulnerability
from app.schemas.treatment import (
    TreatmentCreate,
    TreatmentResponse,
    TreatmentSubmit,
    TreatmentUserResponse,
)
from app.services.audit import record_audit, request_audit_context
from app.services.automatic_checks import enqueue_service_checks
from app.services.inventory import normalized_version

router = APIRouter(prefix="/v1", tags=["treatments"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
TreatmentAssigner = Annotated[User, Depends(require_permissions("treatment.assign"))]
TreatmentReader = Annotated[User, Depends(require_permissions("treatment.read_own"))]
TreatmentSubmitter = Annotated[User, Depends(require_permissions("treatment.submit"))]
TreatmentReviewer = Annotated[User, Depends(require_permissions("treatment.review"))]

TREATMENT_LOAD_OPTIONS = (
    selectinload(VulnerabilityTreatment.service).selectinload(Service.platform),
    selectinload(VulnerabilityTreatment.assignee),
    selectinload(VulnerabilityTreatment.assigner),
    selectinload(VulnerabilityTreatment.confirmer),
)


def treatment_user(user: User | None) -> TreatmentUserResponse | None:
    if user is None:
        return None
    return TreatmentUserResponse(id=user.id, username=user.username, display_name=user.display_name)


def treatment_response(treatment: VulnerabilityTreatment) -> TreatmentResponse:
    service = treatment.service
    return TreatmentResponse(
        id=treatment.id,
        status=treatment.status,
        assignment_note=treatment.assignment_note,
        completion_note=treatment.completion_note,
        service_version_before=treatment.service_version_before,
        new_version=treatment.new_version,
        assigned_at=treatment.assigned_at,
        submitted_at=treatment.submitted_at,
        confirmed_at=treatment.confirmed_at,
        service_id=service.id,
        service_name=service.name,
        service_version=service.version,
        platform_id=service.platform.id,
        platform_name=service.platform.name,
        assignee=treatment_user(treatment.assignee),
        assigned_by=treatment_user(treatment.assigner),
        confirmed_by=treatment_user(treatment.confirmer),
    )


async def load_treatment(db: AsyncSession, treatment_id: UUID) -> VulnerabilityTreatment:
    treatment = await db.scalar(
        select(VulnerabilityTreatment)
        .where(VulnerabilityTreatment.id == treatment_id)
        .options(*TREATMENT_LOAD_OPTIONS)
    )
    if treatment is None:
        raise AppError(404, "TREATMENT_NOT_FOUND", "La demande de traitement est introuvable.")
    return treatment


@router.get("/treatment-assignees", response_model=list[TreatmentUserResponse])
async def treatment_assignees(
    db: DBSession, _user: TreatmentAssigner
) -> list[TreatmentUserResponse]:
    users = (
        (
            await db.scalars(
                select(User)
                .join(User.roles)
                .where(
                    Role.name.in_(("Traitant", "Administrateur")),
                    User.is_active.is_(True),
                    User.archived_at.is_(None),
                )
                .order_by(User.display_name, User.username)
            )
        )
        .unique()
        .all()
    )
    return [treatment_user(user) for user in users if user is not None]


@router.post("/treatments", response_model=TreatmentResponse, status_code=status.HTTP_201_CREATED)
async def treatments_create(
    payload: TreatmentCreate,
    request: Request,
    db: DBSession,
    actor: TreatmentAssigner,
) -> TreatmentResponse:
    service = await db.scalar(
        select(Service)
        .where(Service.id == payload.service_id, Service.archived_at.is_(None))
        .options(selectinload(Service.platform))
    )
    if service is None:
        raise AppError(404, "SERVICE_NOT_FOUND", "Le service est introuvable.")
    active_vulnerability = await db.scalar(
        select(ServiceVulnerability.id).where(
            ServiceVulnerability.service_id == service.id,
            ServiceVulnerability.resolved_at.is_(None),
            ServiceVulnerability.ignored_at.is_(None),
            ServiceVulnerability.match_state.in_(("confirmed", "probable")),
        )
    )
    if active_vulnerability is None:
        raise AppError(409, "SERVICE_NOT_VULNERABLE", "Ce service n’est pas vulnérable.")
    assignee = await db.scalar(
        select(User)
        .where(
            User.id == payload.assigned_to_id,
            User.is_active.is_(True),
            User.archived_at.is_(None),
        )
        .options(selectinload(User.roles))
    )
    if assignee is None or not any(
        role.name in {"Traitant", "Administrateur"} for role in assignee.roles
    ):
        raise AppError(
            422,
            "ASSIGNEE_INVALID",
            "L’utilisateur sélectionné n’est pas un traitant actif.",
        )
    existing = await db.scalar(
        select(VulnerabilityTreatment.id).where(
            VulnerabilityTreatment.service_id == service.id,
            VulnerabilityTreatment.status.in_(("assigned", "submitted")),
        )
    )
    if existing:
        raise AppError(409, "TREATMENT_ALREADY_ACTIVE", "Ce service est déjà attribué.")
    treatment = VulnerabilityTreatment(
        service_id=service.id,
        assigned_to_id=assignee.id,
        assigned_by_id=actor.id,
        status=TreatmentStatus.ASSIGNED.value,
        assignment_note=payload.note,
        service_version_before=service.version,
    )
    db.add(treatment)
    await db.flush()
    record_audit(
        db,
        actor_user_id=actor.id,
        action="treatment.assign",
        entity_type="vulnerability_treatment",
        entity_id=treatment.id,
        platform_id=service.platform_id,
        summary=(
            f"Traitement de {service.name} {service.version or ''} "
            f"attribué à {assignee.display_name}"
        ),
        after_data={"assignee": assignee.display_name, "note": payload.note},
        **request_audit_context(request),
    )
    await db.commit()
    return treatment_response(await load_treatment(db, treatment.id))


@router.get("/treatments/mine", response_model=list[TreatmentResponse])
async def treatments_mine(
    db: DBSession,
    user: TreatmentReader,
    state: Literal["open", "all"] = Query(default="open"),
) -> list[TreatmentResponse]:
    query = (
        select(VulnerabilityTreatment)
        .where(VulnerabilityTreatment.assigned_to_id == user.id)
        .options(*TREATMENT_LOAD_OPTIONS)
    )
    if state == "open":
        query = query.where(VulnerabilityTreatment.status.in_(("assigned", "submitted")))
    items = (await db.scalars(query.order_by(VulnerabilityTreatment.assigned_at.desc()))).all()
    return [treatment_response(item) for item in items]


@router.get("/treatments", response_model=list[TreatmentResponse])
async def treatments_index(
    db: DBSession,
    _user: TreatmentReviewer,
    state: Literal["open", "all", "submitted", "confirmed", "cancelled"] = Query(default="open"),
) -> list[TreatmentResponse]:
    query = select(VulnerabilityTreatment).options(*TREATMENT_LOAD_OPTIONS)
    if state == "open":
        query = query.where(VulnerabilityTreatment.status.in_(("assigned", "submitted")))
    elif state != "all":
        query = query.where(VulnerabilityTreatment.status == state)
    items = (await db.scalars(query.order_by(VulnerabilityTreatment.assigned_at.desc()))).all()
    return [treatment_response(item) for item in items]


@router.patch("/treatments/{treatment_id}/cancel", response_model=TreatmentResponse)
async def treatments_cancel(
    treatment_id: UUID,
    request: Request,
    db: DBSession,
    user: TreatmentReviewer,
) -> TreatmentResponse:
    treatment = await load_treatment(db, treatment_id)
    if treatment.status not in {
        TreatmentStatus.ASSIGNED.value,
        TreatmentStatus.SUBMITTED.value,
    }:
        raise AppError(
            409,
            "TREATMENT_NOT_CANCELLABLE",
            "Cette demande de traitement ne peut plus être annulée.",
        )
    previous_status = treatment.status
    treatment.status = TreatmentStatus.CANCELLED.value
    service = treatment.service
    record_audit(
        db,
        actor_user_id=user.id,
        action="treatment.cancel",
        entity_type="vulnerability_treatment",
        entity_id=treatment.id,
        platform_id=service.platform_id,
        summary=f"Traitement annulé : {service.name} {treatment.service_version_before or ''}",
        before_data={
            "status": previous_status,
            "assignee": treatment.assignee.display_name if treatment.assignee else None,
        },
        after_data={"status": TreatmentStatus.CANCELLED.value},
        **request_audit_context(request),
    )
    await db.commit()
    return treatment_response(await load_treatment(db, treatment.id))


@router.patch("/treatments/{treatment_id}/submit", response_model=TreatmentResponse)
async def treatments_submit(
    treatment_id: UUID,
    payload: TreatmentSubmit,
    request: Request,
    db: DBSession,
    user: TreatmentSubmitter,
) -> TreatmentResponse:
    treatment = await load_treatment(db, treatment_id)
    if treatment.assigned_to_id != user.id:
        raise AppError(403, "TREATMENT_NOT_ASSIGNED", "Ce traitement ne vous est pas attribué.")
    if treatment.status != TreatmentStatus.ASSIGNED.value:
        raise AppError(409, "TREATMENT_NOT_ASSIGNABLE", "Ce traitement a déjà été déclaré terminé.")
    treatment.status = TreatmentStatus.SUBMITTED.value
    treatment.new_version = payload.new_version
    treatment.completion_note = payload.note
    treatment.submitted_at = datetime.now(UTC)
    service = treatment.service
    record_audit(
        db,
        actor_user_id=user.id,
        action="treatment.submit",
        entity_type="vulnerability_treatment",
        entity_id=treatment.id,
        platform_id=service.platform_id,
        summary=(
            f"Traitement déclaré terminé : {service.name} {treatment.service_version_before or ''}"
        ),
        after_data={"new_version": payload.new_version, "note": payload.note},
        **request_audit_context(request),
    )
    await db.commit()
    return treatment_response(await load_treatment(db, treatment.id))


@router.patch("/treatments/{treatment_id}/confirm", response_model=TreatmentResponse)
async def treatments_confirm(
    treatment_id: UUID,
    request: Request,
    db: DBSession,
    user: TreatmentReviewer,
) -> TreatmentResponse:
    treatment = await load_treatment(db, treatment_id)
    if treatment.status != TreatmentStatus.SUBMITTED.value or not treatment.new_version:
        raise AppError(
            409,
            "TREATMENT_NOT_SUBMITTED",
            "Le traitant n’a pas encore terminé cette demande.",
        )
    service = treatment.service
    previous_version = service.version
    service.version = treatment.new_version
    service.normalized_version = normalized_version(treatment.new_version)
    # A CPE identifies a product *and its version*. Once the reviewer accepts the
    # installed version, the previous identity must never be reused, even when CPE
    # checks had previously been disabled. The queued check below will discover the
    # CPE matching the newly accepted version.
    service.cpe_enabled = True
    service.cpe_uri = None
    service.cpe_match_confidence = None
    service.cpe_match_method = None
    service.last_checked_at = None
    now = datetime.now(UTC)
    await db.execute(
        update(ServiceVulnerability)
        .where(
            ServiceVulnerability.service_id == service.id,
            ServiceVulnerability.resolved_at.is_(None),
        )
        .values(resolved_at=now)
    )
    await db.execute(delete(CPECandidate).where(CPECandidate.service_id == service.id))
    treatment.status = TreatmentStatus.CONFIRMED.value
    treatment.confirmed_by_id = user.id
    treatment.confirmed_at = now
    record_audit(
        db,
        actor_user_id=user.id,
        action="treatment.confirm",
        entity_type="vulnerability_treatment",
        entity_id=treatment.id,
        platform_id=service.platform_id,
        summary=f"Traitement confirmé : {service.name} {treatment.service_version_before or ''}",
        before_data={"version": previous_version},
        after_data={
            "version": treatment.new_version,
            "traitant": treatment.assignee.display_name if treatment.assignee else None,
        },
        **request_audit_context(request),
    )
    await db.commit()
    enqueue_service_checks([service.id], request.app.state.settings)
    return treatment_response(await load_treatment(db, treatment.id))
