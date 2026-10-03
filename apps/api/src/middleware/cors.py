"""Dynamic CORS middleware — static origins plus registered site domains."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.services.cors import get_allowed_domains_cached, is_origin_allowed

# Explicit (not "*"): required to stay valid with Allow-Credentials.
_DEFAULT_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
_PREFLIGHT_MAX_AGE = "600"


def _append_vary_origin(response: Response) -> None:
    """Add ``Origin`` to the response ``Vary`` header (append, not overwrite)."""
    existing = response.headers.get("Vary")
    response.headers["Vary"] = "Origin" if not existing else f"{existing}, Origin"


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """Allows static origins and registered site domains (never reflects ``*``)."""

    def __init__(self, app: object, static_origins: list[str]) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.static_origins = list(static_origins)

    async def _is_origin_allowed(self, origin: str) -> bool:
        registered = await get_allowed_domains_cached()
        return is_origin_allowed(origin, self.static_origins, registered)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        origin = request.headers.get("origin")
        if not origin:
            return await call_next(request)

        allowed = await self._is_origin_allowed(origin)

        if request.method == "OPTIONS":
            if not allowed:
                return Response(status_code=400, headers={"Vary": "Origin"})
            headers: dict[str, str] = {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": _DEFAULT_METHODS,
                "Access-Control-Max-Age": _PREFLIGHT_MAX_AGE,
                "Vary": "Origin",
            }
            requested_headers = request.headers.get("access-control-request-headers")
            if requested_headers:
                headers["Access-Control-Allow-Headers"] = requested_headers
            return Response(status_code=200, headers=headers)

        response = await call_next(request)
        _append_vary_origin(response)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
