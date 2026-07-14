import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cli.bootstrap_admin import bootstrap_admin
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app


@dataclass
class FakeRedis:
    values: dict[str, int] = field(default_factory=dict)
    strings: dict[str, str] = field(default_factory=dict)

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, _seconds: int) -> bool:
        return key in self.values or key in self.strings

    async def delete(self, key: str) -> int:
        removed = self.values.pop(key, None) is not None
        removed = self.strings.pop(key, None) is not None or removed
        return int(removed)

    async def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        del ex
        if nx and (key in self.strings or key in self.values):
            return False
        self.strings[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.strings.get(key)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


@dataclass
class AuthTestContext:
    client: TestClient
    settings: Settings
    password: str


async def prepare_database(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await bootstrap_admin(db, settings)
    await engine.dispose()


@pytest.fixture
def auth_context(tmp_path) -> Iterator[AuthTestContext]:  # type: ignore[no-untyped-def]
    password = "Initial!Password42"
    settings = Settings(
        app_env="test",
        app_secret_key="test-secret-that-is-long-and-random-enough",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
        redis_url="redis://unused/0",
        auth_cookie_path="/v1/auth",
        bootstrap_admin_password=password,
        login_max_attempts=3,
        scan_detector_mode="mock",
    )
    asyncio.run(prepare_database(settings))
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.redis = FakeRedis()
        yield AuthTestContext(client=client, settings=settings, password=password)
