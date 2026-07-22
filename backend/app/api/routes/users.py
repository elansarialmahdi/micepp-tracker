from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import require_permissions
from app.core.errors import AppError
from app.core.security import hash_password, validate_password_strength
from app.db.session import get_db
from app.models.auth import RefreshSession, Role, User
from app.schemas.auth import MessageResponse
from app.schemas.user import (
    ManagedUserCreate,
    ManagedUserPasswordUpdate,
    ManagedUserResponse,
    ManagedUserRolesUpdate,
    ManagedUserUpdate,
    RoleResponse,
)
from app.services.audit import record_audit, request_audit_context

router = APIRouter(prefix="/v1", tags=["users"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
UserReader = Annotated[User, Depends(require_permissions("user.read"))]
UserManager = Annotated[User, Depends(require_permissions("user.manage"))]


def role_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=sorted(permission.code for permission in role.permissions),
    )


def managed_user_response(user: User) -> ManagedUserResponse:
    return ManagedUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_active=user.is_active and user.archived_at is None,
        must_change_password=user.must_change_password,
        roles=sorted((role_response(role) for role in user.roles), key=lambda role: role.name),
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


async def requested_roles(db: AsyncSession, role_ids: list[UUID]) -> list[Role]:
    unique_ids = set(role_ids)
    roles = (
        await db.scalars(
            select(Role)
            .where(Role.id.in_(unique_ids))
            .options(selectinload(Role.permissions))
        )
    ).all()
    if len(roles) != len(unique_ids):
        raise AppError(422, "ROLE_INVALID", "Un ou plusieurs rôles sont introuvables.")
    return list(roles)


async def managed_user(db: AsyncSession, user_id: UUID) -> User:
    user = await db.scalar(
        select(User)
        .where(User.id == user_id, User.archived_at.is_(None))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "L’utilisateur est introuvable.")
    return user


async def revoke_user_sessions(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


@router.get("/roles", response_model=list[RoleResponse])
async def roles_index(db: DBSession, _user: UserReader) -> list[RoleResponse]:
    roles = (
        await db.scalars(select(Role).options(selectinload(Role.permissions)).order_by(Role.name))
    ).all()
    return [role_response(role) for role in roles]


@router.get("/users", response_model=list[ManagedUserResponse])
async def users_index(db: DBSession, _user: UserReader) -> list[ManagedUserResponse]:
    users = (
        await db.scalars(
            select(User)
            .where(User.archived_at.is_(None))
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .order_by(User.display_name, User.username)
        )
    ).all()
    return [managed_user_response(user) for user in users]


@router.post("/users", response_model=ManagedUserResponse, status_code=status.HTTP_201_CREATED)
async def users_create(
    payload: ManagedUserCreate,
    request: Request,
    db: DBSession,
    actor: UserManager,
) -> ManagedUserResponse:
    if await db.scalar(
        select(User.id).where(
            User.username == payload.username,
            User.archived_at.is_(None),
        )
    ):
        raise AppError(409, "USERNAME_EXISTS", "Ce nom d’utilisateur existe déjà.")
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise AppError(422, "PASSWORD_TOO_WEAK", str(exc)) from exc
    roles = await requested_roles(db, payload.role_ids)
    user = User(
        username=payload.username,
        display_name=payload.display_name or payload.username,
        password_hash=hash_password(payload.password),
        must_change_password=True,
        roles=roles,
    )
    db.add(user)
    await db.flush()
    record_audit(
        db,
        actor_user_id=actor.id,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        summary=f"Utilisateur créé : {user.display_name}",
        after_data={"username": user.username, "roles": sorted(role.name for role in roles)},
        **request_audit_context(request),
    )
    await db.commit()
    await db.refresh(user, attribute_names=["roles"])
    for role in user.roles:
        await db.refresh(role, attribute_names=["permissions"])
    return managed_user_response(user)


@router.patch("/users/{user_id}", response_model=ManagedUserResponse)
async def users_update(
    user_id: UUID,
    payload: ManagedUserUpdate,
    request: Request,
    db: DBSession,
    actor: UserManager,
) -> ManagedUserResponse:
    user = await managed_user(db, user_id)
    roles = await requested_roles(db, payload.role_ids)
    username_owner = await db.scalar(
        select(User.id).where(
            User.username == payload.username,
            User.archived_at.is_(None),
            User.id != user.id,
        )
    )
    if username_owner:
        raise AppError(409, "USERNAME_EXISTS", "Ce nom d’utilisateur existe déjà.")
    if user.id == actor.id and not any(role.name == "Administrateur" for role in roles):
        raise AppError(
            409,
            "SELF_ADMIN_REQUIRED",
            "Vous ne pouvez pas retirer votre propre rôle administrateur.",
        )

    before_data = {
        "username": user.username,
        "roles": sorted(role.name for role in user.roles),
    }
    user.username = payload.username
    user.roles = roles
    record_audit(
        db,
        actor_user_id=actor.id,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        summary=f"Utilisateur modifié : {user.display_name}",
        before_data=before_data,
        after_data={
            "username": user.username,
            "roles": sorted(role.name for role in roles),
        },
        **request_audit_context(request),
    )
    await db.commit()
    return managed_user_response(user)


@router.patch("/users/{user_id}/password", response_model=MessageResponse)
async def users_update_password(
    user_id: UUID,
    payload: ManagedUserPasswordUpdate,
    request: Request,
    db: DBSession,
    actor: UserManager,
) -> MessageResponse:
    user = await managed_user(db, user_id)
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise AppError(422, "PASSWORD_TOO_WEAK", str(exc)) from exc

    user.password_hash = hash_password(payload.password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    await revoke_user_sessions(db, user.id)
    record_audit(
        db,
        actor_user_id=actor.id,
        action="user.password.reset",
        entity_type="user",
        entity_id=user.id,
        summary=f"Mot de passe réinitialisé pour {user.display_name}",
        **request_audit_context(request),
    )
    await db.commit()
    return MessageResponse(
        message="Mot de passe modifié. L’utilisateur devra le changer à sa prochaine connexion."
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def users_archive(
    user_id: UUID,
    request: Request,
    db: DBSession,
    actor: UserManager,
) -> Response:
    user = await managed_user(db, user_id)
    if user.id == actor.id:
        raise AppError(409, "SELF_ARCHIVE_FORBIDDEN", "Vous ne pouvez pas supprimer votre compte.")

    user.is_active = False
    user.archived_at = datetime.now(UTC)
    await revoke_user_sessions(db, user.id)
    record_audit(
        db,
        actor_user_id=actor.id,
        action="user.archive",
        entity_type="user",
        entity_id=user.id,
        summary=f"Utilisateur supprimé : {user.display_name}",
        before_data={"username": user.username, "is_active": True},
        after_data={"username": user.username, "is_active": False},
        **request_audit_context(request),
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/users/{user_id}/roles", response_model=ManagedUserResponse)
async def users_update_roles(
    user_id: UUID,
    payload: ManagedUserRolesUpdate,
    request: Request,
    db: DBSession,
    actor: UserManager,
) -> ManagedUserResponse:
    user = await db.scalar(
        select(User)
        .where(User.id == user_id, User.archived_at.is_(None))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "L’utilisateur est introuvable.")
    roles = await requested_roles(db, payload.role_ids)
    if user.id == actor.id and not any(role.name == "Administrateur" for role in roles):
        raise AppError(
            409,
            "SELF_ADMIN_REQUIRED",
            "Vous ne pouvez pas retirer votre propre rôle administrateur.",
        )
    before_roles = sorted(role.name for role in user.roles)
    user.roles = roles
    after_roles = sorted(role.name for role in roles)
    record_audit(
        db,
        actor_user_id=actor.id,
        action="user.roles.update",
        entity_type="user",
        entity_id=user.id,
        summary=f"Rôles modifiés pour {user.display_name}",
        before_data={"roles": before_roles},
        after_data={"roles": after_roles},
        **request_audit_context(request),
    )
    await db.commit()
    return managed_user_response(user)
