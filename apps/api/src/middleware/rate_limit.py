"""Redis-backed rate limiting middleware.

Applies per-IP rate limits to all incoming requests. Public endpoints
(consent recording, config fetching) are the primary protection target.

Uses a sliding window counter stored in Redis with automatic expiry.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config.settings import IPNetwork
from src.services.client_ip import resolve_client_ip

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP rate limiter backed by Redis."""

    def __init__(
        self,
        app: object,
        redis_url: str = "redis://localhost:6379/0",
        requests_per_minute: int = 120,
        auth_requests_per_minute: int = 10,
        trusted_proxies: Sequence[IPNetwork] = (),
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.redis_url = redis_url
        self.requests_per_minute = requests_per_minute
        self.auth_requests_per_minute = auth_requests_per_minute
        self.trusted_proxies = tuple(trusted_proxies)
        self._redis: object | None = None
        self._redis_failing = False

    async def _get_redis(self) -> object | None:
        """Lazy-initialise Redis connection."""
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            return self._redis
        except Exception:
            logger.warning("Rate limiting disabled: Redis unavailable")
            return None

    def _get_client_ip(self, request: Request) -> str:
        """Resolve the client IP, trusting forwarded headers from known proxies only."""
        return resolve_client_ip(request, self.trusted_proxies) or "unknown"

    def _mark_redis_failing(self) -> None:
        # Fail open so the banner keeps working, but warn once per outage
        # rather than on every request.
        if not self._redis_failing:
            logger.warning("Rate limiting suspended: Redis unavailable", exc_info=True)
            self._redis_failing = True

    def _mark_redis_healthy(self) -> None:
        if self._redis_failing:
            logger.info("Rate limiting resumed: Redis available again")
            self._redis_failing = False

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/health/ready", "/health/live"):
            return await call_next(request)

        r = await self._get_redis()
        if r is None:
            return await call_next(request)

        # Auth endpoints get a stricter bucket to slow down credential
        # stuffing — login, password reset, token refresh.
        path = request.url.path
        is_auth = path.startswith("/api/v1/auth/") and path not in ("/api/v1/auth/me",)
        limit = self.auth_requests_per_minute if is_auth else self.requests_per_minute
        bucket = "auth" if is_auth else "req"

        client_ip = self._get_client_ip(request)
        window = int(time.time() // 60)
        key = f"cmp:rate:{bucket}:{client_ip}:{window}"

        try:
            current = await r.incr(key)  # type: ignore[union-attr]
            if current == 1:
                await r.expire(key, 120)  # type: ignore[union-attr]
        except Exception:
            self._mark_redis_failing()
            return await call_next(request)

        self._mark_redis_healthy()

        if current > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        remaining = max(0, limit - current)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
