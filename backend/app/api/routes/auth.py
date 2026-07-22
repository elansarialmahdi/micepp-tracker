import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import CurrentUser, require_permissions
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    TokenResponse,
    UserResponse,
)
from app.services.audit import record_audit, request_audit_context, request_client_metadata
from app.services.auth import (
    IssuedTokens,
    authenticate,
    change_password,
    issue_tokens,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
    user_response,
)
from app.services.rate_limit import RateLimiter

router = APIRouter(prefix="/v1/auth", tags=["auth"])
dashboard_router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])
DBSession = Annotated[AsyncSession, Depends(get_db)]
DashboardUser = Annotated[User, Depends(require_permissions("dashboard.read"))]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def validate_csrf(request: Request, settings: Settings) -> None:
    header = request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get(settings.csrf_cookie_name)
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise AppError(403, "CSRF_VALIDATION_FAILED", "La validation de sécurité a échoué.")


def set_auth_cookies(response: Response, settings: Settings, issued: IssuedTokens) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        issued.refresh_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path=settings.auth_cookie_path,
        max_age=issued.refresh_max_age,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        issued.csrf_token,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
        max_age=issued.refresh_max_age,
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path=settings.auth_cookie_path)
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DBSession,
) -> TokenResponse:
    settings: Settings = request.app.state.settings
    limiter = RateLimiter(request.app.state.redis)
    ip = client_ip(request)
    await limiter.check(
        "login-ip",
        ip,
        settings.login_max_attempts * 3,
        settings.login_rate_window_seconds,
    )
    await limiter.check(
        "login-username",
        payload.username,
        settings.login_max_attempts,
        settings.login_rate_window_seconds,
    )
    try:
        user = await authenticate(db, payload.username, payload.password, settings)
    except AppError as exc:
        record_audit(
            db,
            action="auth.login.failed",
            entity_type="session",
            summary=f"Échec de connexion pour {payload.username}",
            metadata={
                "username": payload.username,
                "result": "failure",
                "error_code": exc.code,
                **request_client_metadata(request),
            },
            **request_audit_context(request),
        )
        await db.commit()
        raise
    issued, _ = await issue_tokens(
        db,
        user,
        settings,
        payload.remember_me,
        ip,
        request.headers.get("User-Agent"),
    )
    request.state.user_id = str(user.id)
    record_audit(
        db,
        actor_user_id=user.id,
        action="auth.login",
        entity_type="session",
        summary=f"Connexion réussie : {user.display_name}",
        metadata={"result": "success", **request_client_metadata(request)},
        **request_audit_context(request),
    )
    await db.commit()
    await limiter.reset("login-username", payload.username)
    await limiter.reset("login-ip", ip)
    set_auth_cookies(response, settings, issued)
    return issued.response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: DBSession,
) -> TokenResponse:
    settings: Settings = request.app.state.settings
    validate_csrf(request, settings)
    limiter = RateLimiter(request.app.state.redis)
    ip = client_ip(request)
    await limiter.check("refresh-ip", ip, settings.login_max_attempts * 6, 60)
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    if not raw_token:
        raise AppError(401, "INVALID_REFRESH_TOKEN", "La session a expiré.")
    issued = await rotate_refresh_token(
        db,
        raw_token,
        settings,
        ip,
        request.headers.get("User-Agent"),
    )
    request.state.user_id = str(issued.response.user.id)
    set_auth_cookies(response, settings, issued)
    return issued.response


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    db: DBSession,
) -> MessageResponse:
    settings: Settings = request.app.state.settings
    validate_csrf(request, settings)
    user_id = await revoke_refresh_token(db, request.cookies.get(settings.refresh_cookie_name))
    if user_id:
        request.state.user_id = str(user_id)
    record_audit(
        db,
        actor_user_id=user_id,
        action="auth.logout",
        entity_type="session",
        summary="Déconnexion",
        **request_audit_context(request),
    )
    await db.commit()
    clear_auth_cookies(response, settings)
    return MessageResponse(message="Déconnexion effectuée.")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    request: Request,
    response: Response,
    db: DBSession,
    user: CurrentUser,
) -> MessageResponse:
    await revoke_all_sessions(db, user.id)
    record_audit(
        db,
        actor_user_id=user.id,
        action="auth.logout_all",
        entity_type="session",
        summary="Toutes les sessions ont été révoquées",
        **request_audit_context(request),
    )
    await db.commit()
    clear_auth_cookies(response, request.app.state.settings)
    return MessageResponse(message="Toutes les sessions ont été révoquées.")


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return user_response(user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password_route(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: DBSession,
    user: CurrentUser,
) -> MessageResponse:
    await change_password(db, user, payload.current_password, payload.new_password)
    record_audit(
        db,
        actor_user_id=user.id,
        action="auth.password.change",
        entity_type="user",
        entity_id=user.id,
        summary="Mot de passe modifié",
        **request_audit_context(request),
    )
    await db.commit()
    clear_auth_cookies(response, request.app.state.settings)
    return MessageResponse(message="Mot de passe modifié. Veuillez vous reconnecter.")


@dashboard_router.get("/access")
async def dashboard_access(
    user: DashboardUser,
) -> dict[str, str]:
    return {"status": "granted", "user_id": str(user.id)}
