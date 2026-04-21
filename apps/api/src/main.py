from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.edition import edition_name
from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.extensions.registry import discover_extensions, get_registry
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.routers import (
    auth,
    compliance,
    config,
    consent,
    consent_bridge,
    cookies,
    hosted_pages,
    org_config,
    organisations,
    scanner,
    site_group_config,
    site_groups,
    sites,
    translations,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    setup_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Multi-tenant cookie consent management platform API. "
            "Provides consent collection, cookie scanning, auto-blocking, "
            "compliance checking, and analytics across multiple sites."
        ),
        debug=settings.debug,
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "auth",
                "description": "Authentication — login, token refresh, and current user.",
            },
            {
                "name": "config",
                "description": (
                    "Site configuration — public endpoints for the banner script "
                    "to fetch config, GeoIP-resolved config, and CDN publishing."
                ),
            },
            {
                "name": "consent",
                "description": (
                    "Consent recording and retrieval — public endpoints called "
                    "by the banner script to record visitor consent decisions."
                ),
            },
            {
                "name": "sites",
                "description": "Site and site config CRUD — manage domains and settings.",
            },
            {
                "name": "cookies",
                "description": (
                    "Cookie management — categories, discovered cookies, allow-list, "
                    "known cookies database, and auto-classification."
                ),
            },
            {
                "name": "scanner",
                "description": (
                    "Cookie scanner — trigger scans, view results, and receive "
                    "client-side cookie reports from the banner script."
                ),
            },
            {
                "name": "compliance",
                "description": (
                    "Compliance checking — run checks against GDPR, CNIL, CCPA, "
                    "ePrivacy, and LGPD frameworks."
                ),
            },
            {
                "name": "organisations",
                "description": "Organisation management — multi-tenant root entities.",
            },
            {
                "name": "users",
                "description": "User management — org-scoped users with role-based access.",
            },
        ],
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Rate limiting (must be added before CORS to count requests correctly)
    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            redis_url=settings.redis_url,
            requests_per_minute=settings.rate_limit_per_minute,
            auth_requests_per_minute=10,
        )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Core routers
    api_prefix = "/api/v1"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(config.router, prefix=api_prefix)
    app.include_router(consent.router, prefix=api_prefix)
    app.include_router(scanner.router, prefix=api_prefix)
    app.include_router(compliance.router, prefix=api_prefix)
    app.include_router(organisations.router, prefix=api_prefix)
    app.include_router(org_config.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(site_groups.router, prefix=api_prefix)
    app.include_router(site_group_config.router, prefix=api_prefix)
    app.include_router(sites.router, prefix=api_prefix)
    app.include_router(cookies.router, prefix=api_prefix)
    app.include_router(translations.router, prefix=api_prefix)
    app.include_router(translations.public_router, prefix=api_prefix)

    # Cross-domain consent bridge (no api_prefix — served at /consent-bridge)
    app.include_router(consent_bridge.router)

    # Hosted pages (no api_prefix — public pages at /c/<site_id>/cookies)
    app.include_router(hosted_pages.router)

    # Discover and mount enterprise extensions (no-op in CE mode)
    discover_extensions()
    registry = get_registry()
    registry.apply(app)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Shallow liveness check.

        Answers "is the process running?". Suitable for orchestrator
        liveness probes. For deployment readiness, use
        ``/health/ready`` which verifies downstream dependencies.
        """
        return {"status": "ok", "edition": edition_name()}

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> dict[str, object]:
        """Deep readiness check — verifies database and Redis.

        Returns HTTP 503 if either dependency is unreachable so load
        balancers route traffic away from broken instances.
        """
        from fastapi import HTTPException
        from sqlalchemy import text

        from src.db.session import engine as db_engine

        checks: dict[str, str] = {}
        overall_ok = True

        # Database
        try:
            async with db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
            overall_ok = False

        # Redis
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            pong = await r.ping()
            checks["redis"] = "ok" if pong else "error: ping failed"
            if not pong:
                overall_ok = False
            await r.aclose()
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"
            overall_ok = False

        payload = {
            "status": "ok" if overall_ok else "degraded",
            "edition": edition_name(),
            "checks": checks,
        }
        if not overall_ok:
            raise HTTPException(status_code=503, detail=payload)
        return payload

    return app


app = create_app()
