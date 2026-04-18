"""Sitemap parser for URL discovery.

Fetches and parses XML sitemaps (including sitemap indexes) to discover
URLs for crawling. Falls back to common page paths if no sitemap exists.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

# XML namespace used in sitemaps
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Common page paths to try when no sitemap is available
_DEFAULT_PATHS = [
    "/",
    "/about",
    "/contact",
    "/privacy",
    "/privacy-policy",
    "/terms",
    "/cookie-policy",
]


async def discover_urls(
    domain: str,
    *,
    max_urls: int = 50,
    timeout: float = 10.0,
) -> list[str]:
    """Discover URLs for a domain via sitemap or fallback paths.

    Attempts to fetch /sitemap.xml first. If that fails, tries
    /robots.txt for a Sitemap directive. Falls back to default paths.
    """
    base = f"https://{domain}"
    urls: list[str] = []

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        verify=False,  # noqa: S501 — scanning may target sites with self-signed certs
    ) as client:
        # Try sitemap.xml
        sitemap_urls = await _fetch_sitemap(client, f"{base}/sitemap.xml", max_urls)
        if sitemap_urls:
            return sitemap_urls[:max_urls]

        # Try robots.txt for Sitemap directive
        sitemap_url = await _find_sitemap_in_robots(client, f"{base}/robots.txt")
        if sitemap_url:
            sitemap_urls = await _fetch_sitemap(client, sitemap_url, max_urls)
            if sitemap_urls:
                return sitemap_urls[:max_urls]

    # Fallback to default paths
    urls = [f"{base}{path}" for path in _DEFAULT_PATHS]
    return urls[:max_urls]


async def _fetch_sitemap(
    client: httpx.AsyncClient,
    url: str,
    max_urls: int,
) -> list[str]:
    """Fetch and parse an XML sitemap. Handles sitemap indexes."""
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return []

        # SPAs with catch-all nginx/Caddy rules return 200 + text/html
        # for /sitemap.xml. Don't try to parse HTML as XML.
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type and "xml" not in content_type:
            logger.debug("Sitemap %s returned HTML, skipping", url)
            return []

        root = ElementTree.fromstring(resp.text)

        # Check if it's a sitemap index
        sitemaps = root.findall("sm:sitemap/sm:loc", _NS)
        if sitemaps:
            urls: list[str] = []
            for sm_loc in sitemaps:
                if sm_loc.text:
                    child_urls = await _fetch_sitemap(client, sm_loc.text, max_urls - len(urls))
                    urls.extend(child_urls)
                    if len(urls) >= max_urls:
                        break
            return urls[:max_urls]

        # Regular sitemap — extract <loc> URLs
        locs = root.findall("sm:url/sm:loc", _NS)
        return [loc.text for loc in locs if loc.text][:max_urls]

    except Exception as exc:
        logger.debug("Failed to fetch sitemap %s: %s", url, exc)
        return []


async def _find_sitemap_in_robots(
    client: httpx.AsyncClient,
    robots_url: str,
) -> str | None:
    """Look for a Sitemap directive in robots.txt."""
    try:
        resp = await client.get(robots_url)
        if resp.status_code != 200:
            return None

        for line in resp.text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("sitemap:"):
                return stripped.split(":", 1)[1].strip()

    except Exception:
        pass

    return None
