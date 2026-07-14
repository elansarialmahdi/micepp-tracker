import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cli.bootstrap_admin import bootstrap_admin
from app.core.config import Settings
from app.core.security import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
)
from app.db.base import Base
from app.models.auth import Permission, RefreshSession, User
from tests.conftest import AuthTestContext


def login(context: AuthTestContext, password: str | None = None):  # type: ignore[no-untyped-def]
    return context.client.post(
        "/v1/auth/login",
        json={
            "username": "admin",
            "password": password or context.password,
            "remember_me": False,
        },
    )


def test_valid_and_invalid_login(auth_context: AuthTestContext) -> None:
    invalid = login(auth_context, "incorrect")
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "admin" not in invalid.text

    valid = login(auth_context)
    assert valid.status_code == 200
    assert valid.json()["user"]["must_change_password"] is True
    assert valid.json()["access_token"]
    assert "micepp_refresh=" in valid.headers["set-cookie"]
    assert "HttpOnly" in valid.headers["set-cookie"]

    invalid_payload = auth_context.client.post("/v1/auth/login", json={"username": "admin"})
    assert invalid_payload.status_code == 422
    assert invalid_payload.json()["error"]["code"] == "VALIDATION_ERROR"


def test_refresh_rotation_detects_reuse(auth_context: AuthTestContext) -> None:
    login(auth_context)
    old_refresh = auth_context.client.cookies.get("micepp_refresh")
    csrf = auth_context.client.cookies.get("micepp_csrf")
    assert old_refresh and csrf

    rotated = auth_context.client.post("/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200
    assert auth_context.client.cookies.get("micepp_refresh") != old_refresh

    auth_context.client.cookies.set("micepp_refresh", old_refresh, path="/v1/auth")
    reused = auth_context.client.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": auth_context.client.cookies.get("micepp_csrf") or ""},
    )
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "REFRESH_REUSE_DETECTED"


def test_initial_password_change_is_enforced(auth_context: AuthTestContext) -> None:
    response = login(auth_context)
    token = response.json()["access_token"]
    blocked = auth_context.client.get(
        "/v1/dashboard/access", headers={"Authorization": f"Bearer {token}"}
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = auth_context.client.post(
        "/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": auth_context.password,
            "new_password": "Replacement!Password42",
        },
    )
    assert changed.status_code == 200
    new_login = login(auth_context, "Replacement!Password42")
    assert new_login.status_code == 200
    allowed = auth_context.client.get(
        "/v1/dashboard/access",
        headers={"Authorization": f"Bearer {new_login.json()['access_token']}"},
    )
    assert allowed.status_code == 200


def test_permission_is_checked_by_backend(auth_context: AuthTestContext) -> None:
    async def create_roleless_user() -> UUID:
        engine = create_async_engine(auth_context.settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            user = User(
                username="reader",
                display_name="Lecteur",
                password_hash=hash_password("Reader!Password42"),
                must_change_password=False,
            )
            db.add(user)
            await db.commit()
            user_id = user.id
        await engine.dispose()
        return user_id

    user_id = asyncio.run(create_roleless_user())
    token, _ = create_access_token(user_id, auth_context.settings)
    denied = auth_context.client.get(
        "/v1/dashboard/access", headers={"Authorization": f"Bearer {token}"}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"


def test_login_rate_limit_by_username(auth_context: AuthTestContext) -> None:
    for _ in range(auth_context.settings.login_max_attempts):
        response = auth_context.client.post(
            "/v1/auth/login",
            json={"username": "unknown", "password": "wrong", "remember_me": False},
        )
        assert response.status_code == 401
    limited = auth_context.client.post(
        "/v1/auth/login",
        json={"username": "unknown", "password": "wrong", "remember_me": False},
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_expired_access_token_is_rejected() -> None:
    settings = Settings(
        app_env="test",
        app_secret_key="test-secret-that-is-long-and-random-enough",
        jwt_access_ttl_seconds=-1,
    )
    token, _ = create_access_token(uuid4(), settings)
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, settings)


def test_bootstrap_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        app_env="test",
        app_secret_key="test-secret-that-is-long-and-random-enough",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.db'}",
        bootstrap_admin_password="Initial!Password42",
    )

    async def scenario() -> tuple[int, int, int, bool, bool]:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            first = await bootstrap_admin(db, settings)
            second = await bootstrap_admin(db, settings)
            users = await db.scalar(select(func.count(User.id)))
            permissions = await db.scalar(select(func.count(Permission.id)))
            sessions = await db.scalar(select(func.count(RefreshSession.id)))
        await engine.dispose()
        return users or 0, permissions or 0, sessions or 0, first.created, second.created

    users, permissions, sessions, first_created, second_created = asyncio.run(scenario())
    assert users == 1
    assert permissions >= 20
    assert sessions == 0
    assert first_created is True
    assert second_created is False
