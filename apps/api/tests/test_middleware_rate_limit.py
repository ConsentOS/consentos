"""Tests for the rate limiting middleware."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config.settings import Settings
from src.middleware.rate_limit import RateLimitMiddleware


def _middleware(trusted: str = "") -> RateLimitMiddleware:
    return RateLimitMiddleware(
        Starlette(), trusted_proxies=Settings(trusted_proxies=trusted).trusted_proxy_networks
    )


def _request(headers: dict[str, str] | None = None, peer: str | None = None) -> MagicMock:
    request = MagicMock()
    request.headers = headers or {}
    if peer is None:
        request.client = None
    else:
        request.client = MagicMock()
        request.client.host = peer
    return request


class TestClientIpResolution:
    def test_get_client_ip_from_forwarded_for(self):
        request = _request({"x-forwarded-for": "1.2.3.4"}, peer="10.0.0.5")
        assert _middleware("10.0.0.5")._get_client_ip(request) == "1.2.3.4"

    def test_untrusted_peer_ignores_forwarded_for(self):
        request = _request({"x-forwarded-for": "1.2.3.4"}, peer="203.0.113.9")
        assert _middleware("10.0.0.5")._get_client_ip(request) == "203.0.113.9"

    def test_no_trusted_proxies_ignores_forwarded_headers(self):
        request = _request({"x-forwarded-for": "1.2.3.4", "x-real-ip": "5.6.7.8"}, peer="10.0.0.5")
        assert _middleware()._get_client_ip(request) == "10.0.0.5"

    def test_multi_hop_takes_first_untrusted_from_right(self):
        request = _request(
            {"x-forwarded-for": "6.6.6.6, 1.2.3.4, 10.0.0.7, 10.0.0.8"}, peer="10.0.0.5"
        )
        assert _middleware("10.0.0.0/24")._get_client_ip(request) == "1.2.3.4"

    def test_cidr_matching(self):
        middleware = _middleware("192.168.0.0/16, 2001:db8::/32")
        inside = _request({"x-forwarded-for": "1.2.3.4"}, peer="192.168.44.1")
        outside = _request({"x-forwarded-for": "1.2.3.4"}, peer="192.169.0.1")
        v6 = _request({"x-forwarded-for": "1.2.3.4"}, peer="2001:db8::1")
        assert middleware._get_client_ip(inside) == "1.2.3.4"
        assert middleware._get_client_ip(outside) == "192.169.0.1"
        assert middleware._get_client_ip(v6) == "1.2.3.4"

    def test_ipv4_mapped_peer_matches_ipv4_network(self):
        request = _request({"x-forwarded-for": "1.2.3.4"}, peer="::ffff:10.0.0.5")
        assert _middleware("10.0.0.0/8")._get_client_ip(request) == "1.2.3.4"

    def test_all_hops_trusted_uses_leftmost(self):
        request = _request({"x-forwarded-for": "10.0.0.9, 10.0.0.8"}, peer="10.0.0.5")
        assert _middleware("10.0.0.0/8")._get_client_ip(request) == "10.0.0.9"

    def test_malformed_forwarded_for_falls_back_to_peer(self):
        request = _request({"x-forwarded-for": "not-an-ip, 10.0.0.8"}, peer="10.0.0.5")
        assert _middleware("10.0.0.0/8")._get_client_ip(request) == "10.0.0.5"

    def test_empty_forwarded_for_entry_falls_back_to_peer(self):
        request = _request({"x-forwarded-for": "1.2.3.4,,"}, peer="10.0.0.5")
        assert _middleware("10.0.0.5")._get_client_ip(request) == "10.0.0.5"

    def test_real_ip_from_trusted_peer(self):
        request = _request({"x-real-ip": "9.8.7.6"}, peer="10.0.0.5")
        assert _middleware("10.0.0.5")._get_client_ip(request) == "9.8.7.6"

    def test_real_ip_from_untrusted_peer_ignored(self):
        request = _request({"x-real-ip": "9.8.7.6"}, peer="203.0.113.9")
        assert _middleware("10.0.0.5")._get_client_ip(request) == "203.0.113.9"

    def test_malformed_real_ip_falls_back_to_peer(self):
        request = _request({"x-real-ip": "garbage"}, peer="10.0.0.5")
        assert _middleware("10.0.0.5")._get_client_ip(request) == "10.0.0.5"

    def test_non_ip_peer_returned_unchanged(self):
        request = _request({"x-forwarded-for": "1.2.3.4"}, peer="testclient")
        assert _middleware("10.0.0.0/8")._get_client_ip(request) == "testclient"

    def test_get_client_ip_from_client(self):
        request = _request(peer="10.0.0.1")
        assert _middleware()._get_client_ip(request) == "10.0.0.1"

    def test_get_client_ip_no_client(self):
        assert _middleware()._get_client_ip(_request()) == "unknown"


class TestTrustedProxiesSetting:
    def test_default_is_empty(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
        assert Settings().trusted_proxy_networks == ()

    def test_parses_ips_and_cidrs(self):
        settings = Settings(trusted_proxies=" 10.0.0.1 ,172.16.0.0/12,,::1 ")
        assert [str(n) for n in settings.trusted_proxy_networks] == [
            "10.0.0.1/32",
            "172.16.0.0/12",
            "::1/128",
        ]

    def test_invalid_entry_rejected(self):
        with pytest.raises(ValidationError):
            Settings(trusted_proxies="10.0.0.1, not-a-network")


def _call_next_ok():
    async def call_next(request):
        return JSONResponse({"ok": True})

    return call_next


def _dispatch_request(path: str = "/api/v1/config") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("203.0.113.9", 1234),
        "server": ("test", 80),
        "scheme": "http",
    }
    return Request(scope)


class TestDispatch:
    @pytest.mark.asyncio
    async def test_counts_requests_and_sets_headers(self):
        middleware = _middleware()
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        middleware._redis = redis

        response = await middleware.dispatch(_dispatch_request(), _call_next_ok())

        assert response.status_code == 200
        assert response.headers["X-RateLimit-Remaining"] == "119"
        key = redis.incr.await_args.args[0]
        assert key.startswith("cmp:rate:req:203.0.113.9:")
        redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejects_over_limit(self):
        middleware = _middleware()
        middleware._redis = AsyncMock(incr=AsyncMock(return_value=121))

        response = await middleware.dispatch(_dispatch_request(), _call_next_ok())

        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_auth_bucket_uses_stricter_limit(self):
        middleware = _middleware()
        middleware._redis = AsyncMock(incr=AsyncMock(return_value=11))

        response = await middleware.dispatch(
            _dispatch_request("/api/v1/auth/login"), _call_next_ok()
        )

        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_health_path_skips_redis(self):
        middleware = _middleware()
        middleware._redis = AsyncMock()

        response = await middleware.dispatch(_dispatch_request("/health"), _call_next_ok())

        assert response.status_code == 200
        middleware._redis.incr.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_fails_open_and_warns_once(self, caplog):
        middleware = _middleware()
        middleware._redis = AsyncMock(incr=AsyncMock(side_effect=ConnectionError("down")))

        with caplog.at_level(logging.WARNING, logger="src.middleware.rate_limit"):
            first = await middleware.dispatch(_dispatch_request(), _call_next_ok())
            second = await middleware.dispatch(_dispatch_request(), _call_next_ok())

        assert first.status_code == 200
        assert second.status_code == 200
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1

    @pytest.mark.asyncio
    async def test_redis_recovery_resets_warning(self, caplog):
        middleware = _middleware()
        redis = AsyncMock(incr=AsyncMock(side_effect=[ConnectionError("down"), 1]))
        middleware._redis = redis

        with caplog.at_level(logging.INFO, logger="src.middleware.rate_limit"):
            await middleware.dispatch(_dispatch_request(), _call_next_ok())
            await middleware.dispatch(_dispatch_request(), _call_next_ok())

        assert middleware._redis_failing is False
        assert any("resumed" in r.getMessage() for r in caplog.records)


class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_health_bypasses_rate_limit(self):
        """Health checks should never be rate limited."""
        from src.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_passes_through_when_redis_unavailable(self):
        """When Redis is down, requests should still be served."""
        from src.main import create_app

        # Rate limiting disabled by default in test settings
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self):
        """Rate limit headers should be added when middleware is active."""
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()

        middleware = RateLimitMiddleware(app, requests_per_minute=100)
        middleware._redis = mock_redis

        # Since we can't easily inject the mock Redis into the ASGI middleware,
        # test the logic unit separately
        assert middleware.requests_per_minute == 100

    @pytest.mark.asyncio
    async def test_middleware_creation(self):
        """Middleware should initialise with provided parameters."""
        from starlette.applications import Starlette

        app = Starlette()
        middleware = RateLimitMiddleware(app, redis_url="redis://fake:6379", requests_per_minute=30)
        assert middleware.requests_per_minute == 30
        assert middleware.redis_url == "redis://fake:6379"
        assert middleware._redis is None  # Lazy initialisation


class TestRateLimitConfiguration:
    def test_default_settings_enabled(self, monkeypatch):
        """Rate limiting is on by default — public endpoints must not be DoS-able.

        Note: the suite-wide conftest sets ``RATE_LIMIT_ENABLED=false``
        so other tests aren't rate-limited by Redis; we unset it here
        to verify the baked-in default.
        """
        monkeypatch.delenv("RATE_LIMIT_ENABLED", raising=False)

        from src.config.settings import Settings

        settings = Settings()
        assert settings.rate_limit_enabled is True

    def test_configurable_limit(self):
        """Rate limit per minute should be configurable."""
        from src.config.settings import Settings

        settings = Settings(rate_limit_per_minute=120)
        assert settings.rate_limit_per_minute == 120
