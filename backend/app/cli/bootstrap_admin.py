import asyncio
import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.permissions import PERMISSIONS
from app.core.security import hash_password, validate_password_strength
from app.db.session import create_database_engine, create_session_factory
from app.models.auth import Permission, Role, User


@dataclass
class BootstrapResult:
    created: bool
    generated_password: str | None = None


def generate_strong_password() -> str:
    while True:
        candidate = f"A!{secrets.token_urlsafe(20)}a9"
        try:
            validate_password_strength(candidate)
            return candidate
        except ValueError:
            continue


async def bootstrap_admin(db: AsyncSession, settings: Settings) -> BootstrapResult:
    existing_permissions = {
        permission.code: permission for permission in (await db.scalars(select(Permission))).all()
    }
    for code, description in PERMISSIONS.items():
        if code not in existing_permissions:
            permission = Permission(code=code, description=description)
            db.add(permission)
            existing_permissions[code] = permission

    role = await db.scalar(select(Role).where(Role.name == "Administrateur"))
    if role is None:
        role = Role(
            name="Administrateur",
            description="Rôle système disposant de toutes les permissions.",
            is_system=True,
        )
        db.add(role)
    role.permissions = list(existing_permissions.values())

    user_count = await db.scalar(select(func.count(User.id)))
    if user_count:
        await db.commit()
        return BootstrapResult(created=False)

    supplied_password = settings.bootstrap_admin_password or None
    if supplied_password:
        validate_password_strength(supplied_password)
        password = supplied_password
        generated_password = None
    else:
        if settings.app_env == "production":
            raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD is required in production")
        password = generate_strong_password()
        generated_password = password

    user = User(
        username=settings.bootstrap_admin_username.strip().casefold(),
        password_hash=hash_password(password),
        display_name=settings.bootstrap_admin_display_name,
        must_change_password=True,
        roles=[role],
    )
    db.add(user)
    await db.commit()
    return BootstrapResult(created=True, generated_password=generated_password)


async def main() -> None:
    settings = get_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as db:
            result = await bootstrap_admin(db, settings)
        if result.generated_password:
            print("=" * 72)
            print(f"Administrateur créé : {settings.bootstrap_admin_username}")
            print(f"Mot de passe initial (affiché une seule fois) : {result.generated_password}")
            print("=" * 72)
        elif result.created:
            print(f"Administrateur créé : {settings.bootstrap_admin_username}")
        else:
            print("Bootstrap déjà effectué ; aucun administrateur recréé.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
