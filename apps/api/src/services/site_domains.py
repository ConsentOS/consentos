"""Match hosts and URLs against a site's registered domains.

A host belongs to a site when it equals the site's primary domain or one
of its additional domains, or is a subdomain of one of them. A registered
``www.`` prefix is ignored, so ``www.example.com`` also covers
``example.com`` and its other subdomains.

Registered domains and request hosts are normalised the same way: any
scheme, port, path, query and surrounding dots are dropped, and
internationalised names are compared in their punycode form.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from src.models.site import Site

logger = logging.getLogger(__name__)


def url_host(url: str | None) -> str | None:
    """Return the lower-cased hostname of a URL, or None if it has none."""
    if not url:
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def normalise_host(value: str | None) -> str:
    """Reduce a domain, host or URL to a bare, lower-case ASCII host.

    Returns an empty string when nothing usable remains, including when
    the name cannot be converted to punycode.
    """
    if not value:
        return ""
    raw = value.strip()
    if "://" not in raw:
        raw = f"//{raw}"
    host = (url_host(raw) or "").strip(".")
    if not host:
        return ""
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""


def site_domains(site: Site) -> set[str]:
    """Return the site's primary and additional domains, normalised."""
    registered = [site.domain, *(site.additional_domains or [])]
    domains = {normalise_host(d).removeprefix("www.") for d in registered}
    domains.discard("")
    return domains


def host_matches_site(host: str | None, site: Site) -> bool:
    """Return True if ``host`` is one of the site's domains or a subdomain of one.

    Leading dots (as used in cookie ``Domain`` attributes) are accepted.
    """
    candidate = normalise_host(host)
    if not candidate:
        return False
    return any(
        candidate == domain or candidate.endswith(f".{domain}") for domain in site_domains(site)
    )


def request_source_url(request: Request) -> str | None:
    """Return the request's ``Origin``, or its ``Referer`` when Origin is absent or ``null``."""
    origin = request.headers.get("origin", "").strip()
    if origin and origin.lower() != "null":
        return origin
    return request.headers.get("referer") or None


def require_host_on_site(host: str | None, site: Site, *, detail: str) -> None:
    """Raise 403 and log a warning unless ``host`` belongs to the site."""
    if host_matches_site(host, site):
        return
    logger.warning("%s: site %s, host %s", detail, site.id, host)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _own_host(request: Request) -> str | None:
    host = request.headers.get("host")
    return url_host(f"//{host}") if host else None


def require_request_from_site(request: Request, site: Site) -> None:
    """Raise 403 and log a warning if the request's origin is outside the site.

    Requests from pages served by this API itself, such as the hosted
    cookies page, carry the API's own host as their origin and are
    accepted.
    """
    source = request_source_url(request)
    if source is None:
        return
    source_host = url_host(source)
    if source_host is not None and source_host == _own_host(request):
        return
    require_host_on_site(source_host, site, detail="Origin does not match site")
