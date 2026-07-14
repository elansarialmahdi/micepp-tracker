from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_token
from app.models.auth import RefreshSession, Role, User

USER_LOAD_OPTIONS = (selectinload(User.roles).selectinload(Role.permissions),)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(
        select(User).where(User.username == username).options(*USER_LOAD_OPTIONS)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id).options(*USER_LOAD_OPTIONS))
    return result.scalar_one_or_none()


async def get_refresh_session(db: AsyncSession, raw_token: str) -> RefreshSession | None:
    result = await db.execute(
        select(RefreshSession)
        .where(RefreshSession.token_hash == hash_token(raw_token))
        .options(
            selectinload(RefreshSession.user)
            .selectinload(User.roles)
            .selectinload(Role.permissions)
        )
    )
    return result.scalar_one_or_none()


def permission_codes(user: User) -> list[str]:
    return sorted({permission.code for role in user.roles for permission in role.permissions})
