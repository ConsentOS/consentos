"""GeoIP service — resolve an IP address to a country/region code.

Resolution order (see :func:`detect_region`):

1. **CDN / proxy headers.** Operators configure ``GEOIP_COUNTRY_HEADER``
   (and optionally ``GEOIP_REGION_HEADER``) to match whatever their edge
   uses — e.g. ``cf-ipcountry`` + ``cf-region-code`` on Cloudflare
   Enterprise, or ``x-gclb-country`` + ``x-gclb-region`` on GCP. A short
   built-in country list (``cf-ipcountry``, ``x-vercel-ip-country``,
   ``x-appengine-country``, ``x-country-code``) covers the common case
   where only country-level granularity is needed.
2. **Local MaxMind GeoLite2-City database.** Set
   ``GEOIP_MAXMIND_DB_PATH`` to a mounted ``.mmdb`` file. Gives both
   country and ISO 3166-2 subdivision without any external calls.
3. **External ip-api.com lookup** (rate-limited, no API key). Last-ditch
   fallback; fine for development, not recommended for production.
4. Unresolved — the caller should fall back to the default region.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import geoip2.database
import httpx
from fastapi import Request

from src.config.settings import get_settings
from src.services.client_ip import get_client_ip

logger = logging.getLogger(__name__)

# Lazily-initialised MaxMind reader. ``geoip2.database.Reader`` opens
# the file once and then every lookup is a memory-mapped read, so we
# cache it for the lifetime of the process. ``None`` means either no
# path is configured, initialisation failed, or we haven't tried yet.
_maxmind_reader: geoip2.database.Reader | None = None
_maxmind_initialised = False

# Standard headers set by CDN / reverse proxy providers. Operators
# running behind a CDN that uses a non-standard header (e.g. Google
# Cloud Load Balancer's ``x-gclb-country``) can add one more via the
# ``GEOIP_COUNTRY_HEADER`` env var — see ``detect_region_from_headers``.
_GEO_HEADERS = [
    "cf-ipcountry",  # Cloudflare
    "x-vercel-ip-country",  # Vercel
    "x-appengine-country",  # Google App Engine
    "x-country-code",  # Generic / custom
]

# Mapping from two-letter country code to region codes used in regional_modes
# EU member states → "EU", US states handled separately, etc.
_EU_COUNTRIES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
    }
)


@dataclass(frozen=True)
class GeoResult:
    """Result of a GeoIP lookup."""

    country_code: str | None
    region: str | None

    @property
    def is_resolved(self) -> bool:
        return self.country_code is not None


def country_to_region(country_code: str, state_code: str | None = None) -> str:
    """Map a country code (+ optional subdivision) to a regional_modes key.

    Resolution order:
      - EU member states collapse to ``"EU"`` regardless of subdivision;
        regional_modes treats the bloc as a single unit.
      - Any other country with a subdivision produces ``"{CC}-{SUB}"``
        (e.g. ``"US-CA"``, ``"GB-SCT"``, ``"BR-SP"``). The operator
        opts in to subdivision-level resolution by configuring a key
        of that form in ``regional_modes``; if they don't, the
        fallback resolver still matches on the plain country code.
      - Country with no subdivision is returned as-is (``"GB"``,
        ``"BR"``, …).
    """
    upper = country_code.upper()

    if upper in _EU_COUNTRIES:
        return "EU"

    if state_code:
        return f"{upper}-{state_code.upper()}"

    return upper


def detect_region_from_headers(request: Request) -> GeoResult:
    """Attempt to detect the visitor's region from proxy/CDN headers.

    This is the fastest path — no external calls needed. A custom
    country header configured via ``GEOIP_COUNTRY_HEADER`` takes
    priority over the built-in list so operators can plumb in
    non-standard CDN/load-balancer headers (e.g. ``x-gclb-country``)
    without code changes.

    When ``GEOIP_REGION_HEADER`` is also set and the custom country
    header resolved, the subdivision code from that header is paired
    with the country to build region keys like ``US-CA``. The built-in
    country list is country-only — operators who need subdivision
    granularity must configure the explicit pair.

    Header lookups are case-insensitive.
    """
    settings = get_settings()
    custom_country = settings.geoip_country_header
    custom_region = settings.geoip_region_header

    if custom_country:
        value = request.headers.get(custom_country)
        if value and value.upper() != "XX":
            country = value.upper().strip()
            state: str | None = None
            if custom_region:
                raw_state = request.headers.get(custom_region)
                if raw_state and raw_state.upper() != "XX":
                    # ISO 3166-2 subdivision codes may be prefixed
                    # with the country (e.g. ``US-CA``) or bare (e.g.
                    # ``CA``). Strip the prefix so ``country_to_region``
                    # sees just the subdivision.
                    stripped = raw_state.strip().upper()
                    state = stripped.split("-", 1)[-1] if "-" in stripped else stripped
            return GeoResult(
                country_code=country,
                region=country_to_region(country, state),
            )

    for header in _GEO_HEADERS:
        value = request.headers.get(header)
        if value and value.upper() != "XX":
            country = value.upper().strip()
            return GeoResult(
                country_code=country,
                region=country_to_region(country),
            )

    return GeoResult(country_code=None, region=None)


async def lookup_ip_region(ip: str) -> GeoResult:
    """Look up the region for an IP address via an external API.

    Uses ip-api.com (free tier, no key required, 45 req/min).
    In production this should be replaced with a local MaxMind database.
    """
    if _is_private_ip(ip):
        return GeoResult(country_code=None, region=None)

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,countryCode,region"},
            )
            if resp.status_code != 200:
                return GeoResult(country_code=None, region=None)

            data = resp.json()
            if data.get("status") != "success":
                return GeoResult(country_code=None, region=None)

            country = data.get("countryCode")
            state = data.get("region")  # State/province code
            if not country:
                return GeoResult(country_code=None, region=None)

            region = country_to_region(country, state)
            return GeoResult(country_code=country, region=region)

    except Exception:
        logger.debug("GeoIP lookup failed for %s", ip, exc_info=True)
        return GeoResult(country_code=None, region=None)


def _get_maxmind_reader() -> geoip2.database.Reader | None:
    """Return the cached MaxMind reader, opening the DB on first use.

    Caches both successful opens and failures (via
    ``_maxmind_initialised``) so we don't retry a bad path on every
    request. Returns ``None`` if no path is configured or the DB
    couldn't be opened.
    """
    global _maxmind_reader, _maxmind_initialised
    if _maxmind_initialised:
        return _maxmind_reader

    _maxmind_initialised = True
    db_path = get_settings().geoip_maxmind_db_path
    if not db_path:
        return None

    try:
        _maxmind_reader = geoip2.database.Reader(db_path)
        logger.info("GeoIP: opened MaxMind database at %s", db_path)
    except Exception:
        logger.warning(
            "GeoIP: failed to open MaxMind database at %s — falling back to "
            "external lookups. Check GEOIP_MAXMIND_DB_PATH and that the file "
            "is readable inside the container.",
            db_path,
            exc_info=True,
        )
        _maxmind_reader = None

    return _maxmind_reader


def lookup_ip_maxmind(ip: str) -> GeoResult:
    """Resolve an IP via the local MaxMind database.

    Memory-mapped read, no network I/O — cheap enough to call
    synchronously from the async path. Returns an unresolved
    ``GeoResult`` when the DB isn't configured, the IP is private, or
    the record can't be found.
    """
    if _is_private_ip(ip):
        return GeoResult(country_code=None, region=None)

    reader = _get_maxmind_reader()
    if reader is None:
        return GeoResult(country_code=None, region=None)

    try:
        response = reader.city(ip)
    except Exception:
        logger.debug("MaxMind lookup failed for %s", ip, exc_info=True)
        return GeoResult(country_code=None, region=None)

    country = response.country.iso_code
    if not country:
        return GeoResult(country_code=None, region=None)

    # ``subdivisions`` is ordered most-specific first; the first entry
    # is the ISO 3166-2 code (without the country prefix).
    state = response.subdivisions.most_specific.iso_code if response.subdivisions else None
    return GeoResult(
        country_code=country.upper(),
        region=country_to_region(country, state),
    )


async def detect_region(request: Request) -> GeoResult:
    """Detect the visitor's region.

    Resolution order:

    1. CDN/proxy headers (see :func:`detect_region_from_headers`).
    2. Local MaxMind database, if ``GEOIP_MAXMIND_DB_PATH`` is set.
    3. External ``ip-api.com`` lookup — last-ditch fallback.

    Returns an unresolved :class:`GeoResult` if every tier fails.
    """
    result = detect_region_from_headers(request)
    if result.is_resolved:
        return result

    ip = get_client_ip(request)
    if not ip:
        return GeoResult(country_code=None, region=None)

    if get_settings().geoip_maxmind_db_path:
        result = lookup_ip_maxmind(ip)
        if result.is_resolved:
            return result

    return await lookup_ip_region(ip)


def _is_private_ip(ip: str) -> bool:
    """Check if an IP address is a private/loopback address."""
    return (
        ip.startswith("127.")
        or ip.startswith("10.")
        or ip.startswith("192.168.")
        or ip.startswith("172.16.")
        or ip.startswith("172.17.")
        or ip.startswith("172.18.")
        or ip.startswith("172.19.")
        or ip.startswith("172.2")
        or ip.startswith("172.3")
        or ip == "::1"
        or ip == "localhost"
    )
