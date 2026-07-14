from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.db.session import get_db
from app.models.auth import User
from app.repositories.auth import get_user_by_id, permission_codes

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise AppError(401, "AUTHENTICATION_REQUIRED", "Authentification requise.")
    try:
        user_id = decode_access_token(credentials.credentials, request.app.state.settings)
    except InvalidAccessTokenError as exc:
        raise AppError(401, "ACCESS_TOKEN_INVALID", "La session a expiré.") from exc
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active or user.archived_at is not None:
        raise AppError(401, "ACCESS_TOKEN_INVALID", "La session a expiré.")
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permissions(
    *required: str,
) -> Callable[..., Coroutine[Any, Any, User]]:
    async def dependency(user: CurrentUser) -> User:
        if user.must_change_password:
            raise AppError(
                403,
                "PASSWORD_CHANGE_REQUIRED",
                "Vous devez modifier votre mot de passe initial.",
            )
        granted = set(permission_codes(user))
        if not set(required).issubset(granted):
            raise AppError(403, "PERMISSION_DENIED", "Vous n’avez pas l’autorisation requise.")
        return user

    return dependency
