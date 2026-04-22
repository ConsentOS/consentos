"""Security headers middleware.

Adds standard security headers to all API responses:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - X-XSS-Protection: 0 (disabled in favour of CSP)
  - Referrer-Policy: strict-origin-when-cross-origin
  - Content-Security-Policy: default-src 'none'
  - Strict-Transport-Security (HSTS) in production
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


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

        # The consent bridge must be embeddable as a cross-origin iframe
        # for cross-domain consent sharing. All other endpoints deny framing.
        if request.url.path == "/consent-bridge":
            response.headers["Content-Security-Policy"] = "default-src 'unsafe-inline'"
        else:
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = "default-src 'none'"

        # HSTS — only on HTTPS requests (reverse proxy may terminate TLS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
