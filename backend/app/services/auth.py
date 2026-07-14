from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from app.models.auth import RefreshSession, User
from app.repositories.auth import get_refresh_session, get_user_by_username, permission_codes
from app.schemas.auth import TokenResponse, UserResponse

logger = logging.getLogger("micepp.auth")


@dataclass
class IssuedTokens:
    response: TokenResponse
    refresh_token: str
    csrf_token: str
    refresh_max_age: int


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        must_change_password=user.must_change_password,
        permissions=permission_codes(user),
        roles=sorted(role.name for role in user.roles),
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def authenticate(db: AsyncSession, username: str, password: str, settings: Settings) -> User:
    user = await get_user_by_username(db, username)
    now = datetime.now(UTC)

    if user is None:
        verify_password(DUMMY_PASSWORD_HASH, password)
        logger.warning("login_failed", extra={"action": "auth.login", "result": "failed"})
        raise AppError(401, "INVALID_CREDENTIALS", "Identifiant ou mot de passe incorrect.")

    if user.locked_until and _aware(user.locked_until) > now:
        raise AppError(401, "INVALID_CREDENTIALS", "Identifiant ou mot de passe incorrect.")

    if not verify_password(user.password_hash, password) or not user.is_active or user.archived_at:
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_attempts:
            user.locked_until = now + timedelta(seconds=settings.login_lock_seconds)
        await db.commit()
        logger.warning(
            "login_failed",
            extra={"user_id": str(user.id), "action": "auth.login", "result": "failed"},
        )
        raise AppError(401, "INVALID_CREDENTIALS", "Identifiant ou mot de passe incorrect.")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()
    logger.info(
        "login_succeeded",
        extra={"user_id": str(user.id), "action": "auth.login", "result": "succeeded"},
    )
    return user


async def issue_tokens(
    db: AsyncSession,
    user: User,
    settings: Settings,
    remember_me: bool,
    ip: str | None,
    user_agent: str | None,
    family_id: UUID | None = None,
    absolute_expires_at: datetime | None = None,
) -> tuple[IssuedTokens, RefreshSession]:
    refresh_ttl = (
        settings.jwt_remember_refresh_ttl_seconds
        if remember_me
        else settings.jwt_refresh_ttl_seconds
    )
    now = datetime.now(UTC)
    expires_at = absolute_expires_at or now + timedelta(seconds=refresh_ttl)
    raw_refresh = create_refresh_token()
    refresh_session = RefreshSession(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        jti=uuid4().hex,
        family_id=family_id or uuid4(),
        user_agent=(user_agent or "")[:500] or None,
        ip=ip,
        expires_at=expires_at,
    )
    db.add(refresh_session)
    await db.flush()
    access_token, expires_in = create_access_token(user.id, settings)
    issued = IssuedTokens(
        response=TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
            user=user_response(user),
        ),
        refresh_token=raw_refresh,
        csrf_token=create_csrf_token(),
        refresh_max_age=max(1, int((_aware(expires_at) - now).total_seconds())),
    )
    return issued, refresh_session


async def rotate_refresh_token(
    db: AsyncSession,
    raw_token: str,
    settings: Settings,
    ip: str | None,
    user_agent: str | None,
) -> IssuedTokens:
    refresh_session = await get_refresh_session(db, raw_token)
    if refresh_session is None:
        raise AppError(401, "INVALID_REFRESH_TOKEN", "La session a expiré.")

    now = datetime.now(UTC)
    if refresh_session.revoked_at is not None:
        await db.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == refresh_session.family_id)
            .where(RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        logger.warning(
            "refresh_token_reuse_detected",
            extra={"user_id": str(refresh_session.user_id), "result": "blocked"},
        )
        raise AppError(401, "REFRESH_REUSE_DETECTED", "La session a été révoquée.")

    if _aware(refresh_session.expires_at) <= now:
        refresh_session.revoked_at = now
        await db.commit()
        raise AppError(401, "INVALID_REFRESH_TOKEN", "La session a expiré.")

    issued, replacement = await issue_tokens(
        db,
        refresh_session.user,
        settings,
        False,
        ip,
        user_agent,
        family_id=refresh_session.family_id,
        absolute_expires_at=_aware(refresh_session.expires_at),
    )
    refresh_session.revoked_at = now
    refresh_session.last_used_at = now
    refresh_session.replaced_by_id = replacement.id
    await db.commit()
    return issued


async def revoke_refresh_token(db: AsyncSession, raw_token: str | None) -> UUID | None:
    if not raw_token:
        return None
    refresh_session = await get_refresh_session(db, raw_token)
    if refresh_session and refresh_session.revoked_at is None:
        refresh_session.revoked_at = datetime.now(UTC)
        await db.commit()
        return refresh_session.user_id
    return None


async def revoke_all_sessions(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id)
        .where(RefreshSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise AppError(400, "CURRENT_PASSWORD_INVALID", "Le mot de passe actuel est incorrect.")
    if verify_password(user.password_hash, new_password):
        raise AppError(400, "PASSWORD_UNCHANGED", "Le nouveau mot de passe doit être différent.")
    try:
        validate_password_strength(new_password)
    except ValueError as exc:
        raise AppError(422, "PASSWORD_TOO_WEAK", str(exc)) from exc
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await db.flush()
    await revoke_all_sessions(db, user.id)
    logger.info(
        "password_changed",
        extra={"user_id": str(user.id), "action": "auth.change_password", "result": "succeeded"},
    )
