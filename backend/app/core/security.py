from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=4)
DUMMY_PASSWORD_HASH = password_hasher.hash("not-a-real-password")


class InvalidAccessTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def validate_password_strength(password: str) -> None:
    checks = (
        len(password) >= 12,
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^A-Za-z0-9]", password)),
    )
    if not all(checks):
        raise ValueError(
            "Le mot de passe doit contenir au moins 12 caractères, une majuscule, "
            "une minuscule, un chiffre et un caractère spécial."
        )


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.jwt_access_ttl_seconds)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": uuid4().hex,
        "iat": now,
        "exp": expires_at,
        "iss": settings.app_name,
    }
    token = jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm)
    return token, settings.jwt_access_ttl_seconds


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_verification_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
            options={"require": ["sub", "type", "jti", "iat", "exp"]},
        )
        if payload["type"] != "access":
            raise InvalidAccessTokenError
        return UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError from exc


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)
