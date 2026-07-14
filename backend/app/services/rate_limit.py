import hashlib
from uuid import UUID

from fastapi import Request
from redis.asyncio import Redis

from app.core.errors import AppError


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def check(self, scope: str, identity: str, limit: int, window_seconds: int) -> None:
        identity_hash = hashlib.sha256(identity.casefold().encode("utf-8")).hexdigest()
        key = f"rate-limit:{scope}:{identity_hash}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, window_seconds)
        except Exception as exc:
            raise AppError(
                503,
                "RATE_LIMIT_UNAVAILABLE",
                "Le contrôle de sécurité est temporairement indisponible.",
            ) from exc
        if count > limit:
            raise AppError(429, "RATE_LIMIT_EXCEEDED", "Trop de tentatives. Réessayez plus tard.")

    async def reset(self, scope: str, identity: str) -> None:
        identity_hash = hashlib.sha256(identity.casefold().encode("utf-8")).hexdigest()
        try:
            await self.redis.delete(f"rate-limit:{scope}:{identity_hash}")
        except Exception:
            return


async def enforce_expensive_limit(
    request: Request,
    *,
    scope: str,
    user_id: UUID,
    limit: int,
    window_seconds: int,
) -> None:
    limiter = RateLimiter(request.app.state.redis)
    forwarded_ip = request.headers.get("x-real-ip")
    client_ip = forwarded_ip or (request.client.host if request.client else "unknown")
    await limiter.check(f"{scope}:user", str(user_id), limit, window_seconds)
    await limiter.check(f"{scope}:ip", client_ip, limit * 3, window_seconds)
