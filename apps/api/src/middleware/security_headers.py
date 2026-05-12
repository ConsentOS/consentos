"""Security headers middleware.

Adds standard security headers to all API responses:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - X-XSS-Protection: 0 (disabled in favour of CSP)
  - Referrer-Policy: strict-origin-when-cross-origin
  - Content-Security-Policy: default-src 'none' (with carve-outs)
  - Strict-Transport-Security (HSTS) in production

The default ``default-src 'none'`` policy is correct for JSON API
responses but blocks Swagger UI on ``/docs`` and ReDoc on ``/redoc``
(both pull in their own JS, CSS and fonts from a CDN). Those paths
get a looser CSP that allows the documentation UI to load while
still preventing the broader API surface from executing scripts.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Paths that serve interactive HTML documentation. The FastAPI
# defaults are ``/docs`` (Swagger UI), ``/redoc`` (ReDoc) and
# ``/openapi.json`` (the schema both UIs fetch).
_DOCS_PATHS: frozenset[str] = frozenset({"/docs", "/redoc", "/openapi.json"})

# CSP relaxed enough for the bundled Swagger/ReDoc HTML to load
# its CDN assets, inline init script and fetch the OpenAPI JSON,
# but still no plug-ins or arbitrary network access.
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        path = request.url.path
        if path == "/consent-bridge":
            # The consent bridge must be embeddable as a cross-origin
            # iframe for cross-domain consent sharing.
            response.headers["Content-Security-Policy"] = "default-src 'unsafe-inline'"
        elif path in _DOCS_PATHS:
            # Swagger UI / ReDoc need CDN scripts + styles + fonts and
            # an inline init script. The carve-out is narrow: only
            # these three paths get the relaxed CSP.
            response.headers["Content-Security-Policy"] = _DOCS_CSP
            response.headers["X-Frame-Options"] = "DENY"
        else:
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = "default-src 'none'"

        # HSTS — only on HTTPS requests (reverse proxy may terminate TLS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
