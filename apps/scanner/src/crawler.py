"""Playwright-based headless browser cookie crawler.

For each URL: launches headless Chromium, **pre-seeds an
"all categories accepted" ConsentOS consent cookie**, clears any other
cookies, navigates, waits for network idle, enumerates
``document.cookie`` / ``localStorage`` / ``sessionStorage``, captures
``Set-Cookie`` headers from network requests, and attributes cookies
to source scripts via the request chain.

The pre-seed is what makes the scan useful: without it the loader
would block analytics/marketing scripts and the scan would only see
strictly-necessary cookies, which tells you nothing about what the
site actually loads in the post-consent state. Pre-consent compliance
checks live in ``consent_validator.py`` and use a separate code path.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

from playwright.async_api import (
    BrowserContext,
    Page,
    Request,
    Response,
    async_playwright,
)

logger = logging.getLogger(__name__)

# All ConsentOS categories — pre-seeded as accepted on every crawl so
# the loader's "consent already given" branch fires and unblocks all
# scripts/cookies.
_ALL_CATEGORIES: list[str] = [
    "necessary",
    "functional",
    "analytics",
    "marketing",
    "personalisation",
]

# Must match ``COOKIE_NAME`` in apps/banner/src/consent.ts. If you
# rename it there, rename it here too.
_CONSENT_COOKIE_NAME = "_consentos_consent"


def _build_consent_cookie(url: str) -> dict:
    """Return a Playwright cookie dict pre-seeding ConsentOS consent.

    Mirrors the shape that ``apps/banner/src/consent.ts:writeConsent``
    produces — URL-encoded JSON of a ``ConsentState`` — so the loader's
    ``readConsent`` returns a valid object and short-circuits straight
    to ``updateAcceptedCategories(...)``. Categories are hard-coded to
    every known ConsentOS category; the scanner is a "what does this
    site load when the visitor accepts everything?" tool, by design.
    """
    state = {
        "visitorId": str(uuid.uuid4()),
        "accepted": _ALL_CATEGORIES,
        "rejected": [],
        "consentedAt": datetime.now(UTC).isoformat(),
        "bannerVersion": "scanner",
    }
    value = quote(json.dumps(state, separators=(",", ":")), safe="")
    return {
        "name": _CONSENT_COOKIE_NAME,
        "value": value,
        "url": url,
        "path": "/",
        "expires": time.time() + 365 * 86400,
        "sameSite": "Lax",
    }

# Realistic Chrome UA so sites don't block the crawler as a bot.
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class DiscoveredCookie:
    """A cookie or storage item found during a crawl."""

    name: str
    domain: str
    storage_type: str = "cookie"  # cookie | local_storage | session_storage
    path: str | None = None
    expires: float | None = None
    http_only: bool | None = None
    secure: bool | None = None
    same_site: str | None = None
    value_length: int = 0
    script_source: str | None = None
    page_url: str = ""
    initiator_chain: list[str] = field(default_factory=list)


@dataclass
class CrawlResult:
    """Result of crawling a single page."""

    url: str
    cookies: list[DiscoveredCookie] = field(default_factory=list)
    error: str | None = None


@dataclass
class SiteCrawlResult:
    """Aggregated result of crawling all pages on a site."""

    domain: str
    pages: list[CrawlResult] = field(default_factory=list)
    total_cookies_found: int = 0

    @property
    def unique_cookies(self) -> list[DiscoveredCookie]:
        """Deduplicate cookies across pages by (name, domain, storage_type)."""
        seen: dict[tuple[str, str, str], DiscoveredCookie] = {}
        for page in self.pages:
            for cookie in page.cookies:
                key = (cookie.name, cookie.domain, cookie.storage_type)
                if key not in seen:
                    seen[key] = cookie
        return list(seen.values())


@dataclass
class ProxyConfig:
    """Proxy configuration for geo-located scanning."""

    server: str  # e.g. "http://proxy-eu.example.com:8080"
    username: str | None = None
    password: str | None = None


class CookieCrawler:
    """Crawls a site using Playwright to discover cookies and storage items."""

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 30_000,
        user_agent: str = _DEFAULT_USER_AGENT,
        proxy: ProxyConfig | None = None,
    ) -> None:
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._user_agent = user_agent
        self._proxy = proxy

    async def crawl_site(
        self,
        urls: list[str],
        *,
        max_pages: int = 50,
    ) -> SiteCrawlResult:
        """Crawl multiple URLs and aggregate cookie discoveries."""
        if not urls:
            return SiteCrawlResult(domain="")

        domain = urlparse(urls[0]).hostname or ""
        result = SiteCrawlResult(domain=domain)

        async with async_playwright() as pw:
            launch_kwargs: dict = {"headless": self._headless}
            if self._proxy:
                proxy_opts: dict = {"server": self._proxy.server}
                if self._proxy.username:
                    proxy_opts["username"] = self._proxy.username
                if self._proxy.password:
                    proxy_opts["password"] = self._proxy.password
                launch_kwargs["proxy"] = proxy_opts
            browser = await pw.chromium.launch(**launch_kwargs)
            try:
                for url in urls[:max_pages]:
                    page_result = await self._crawl_page(browser, url)
                    result.pages.append(page_result)
                    result.total_cookies_found += len(page_result.cookies)
            finally:
                await browser.close()

        return result

    async def _crawl_page(
        self,
        browser: Browser,  # noqa: F821
        url: str,
    ) -> CrawlResult:
        """Crawl a single page and discover cookies."""
        result = CrawlResult(url=url)
        script_cookies: dict[str, str] = {}  # cookie name → script URL
        initiator_map: dict[str, str] = {}  # request URL → initiating URL
        initiator_chains: dict[str, list[str]] = {}  # cookie name → chain

        context: BrowserContext | None = None
        try:
            context = await browser.new_context(
                user_agent=self._user_agent,
                ignore_https_errors=True,
            )
            # Start from a clean slate, then plant the ConsentOS consent
            # cookie so the loader treats the visitor as having already
            # accepted every category. Without this the scan only sees
            # strictly-necessary cookies — useless for "what does this
            # site actually load?" reporting.
            await context.clear_cookies()
            await context.add_cookies([_build_consent_cookie(url)])

            page: Page = await context.new_page()

            # Track request initiator chains via frame URL and redirect chains
            def _on_request(request: Request) -> None:
                try:
                    req_url = request.url
                    # Follow redirect chain to find the original initiator
                    redirected = request.redirected_from
                    if redirected:
                        initiator_map[req_url] = redirected.url
                    else:
                        # Use the frame URL as the parent initiator
                        frame_url = request.frame.url if request.frame else ""
                        if frame_url and frame_url != req_url:
                            initiator_map[req_url] = frame_url
                except Exception:
                    pass  # Non-critical — request introspection may fail

            page.on("request", _on_request)

            # Track Set-Cookie headers from responses
            async def _on_response(response: Response) -> None:
                try:
                    headers = await response.all_headers()
                    set_cookie = headers.get("set-cookie", "")
                    if set_cookie:
                        # Attribute cookie to the initiating script
                        request: Request = response.request
                        initiator = _get_script_initiator(request)
                        # Build the initiator chain for this request
                        chain = _build_initiator_chain(request.url, initiator_map)
                        for cookie_str in set_cookie.split("\n"):
                            name = cookie_str.split("=")[0].strip()
                            if name:
                                if initiator:
                                    script_cookies[name] = initiator
                                initiator_chains[name] = chain
                except Exception:
                    pass  # Non-critical — response may have been aborted

            page.on("response", _on_response)

            # Navigate
            await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            # Allow additional time for scripts to set cookies after DOM load.
            await page.wait_for_timeout(3000)

            # Enumerate browser cookies via CDP
            cdp_cookies = await context.cookies()
            for c in cdp_cookies:
                result.cookies.append(
                    DiscoveredCookie(
                        name=c["name"],
                        domain=c["domain"],
                        storage_type="cookie",
                        path=c.get("path"),
                        expires=c.get("expires"),
                        http_only=c.get("httpOnly"),
                        secure=c.get("secure"),
                        same_site=c.get("sameSite"),
                        value_length=len(c.get("value", "")),
                        script_source=script_cookies.get(c["name"]),
                        page_url=url,
                        initiator_chain=initiator_chains.get(c["name"], []),
                    )
                )

            # Enumerate localStorage
            ls_items = await page.evaluate("""() => {
                const items = [];
                try {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        if (key) {
                            items.push({
                                name: key,
                                valueLength: (localStorage.getItem(key) || '').length,
                            });
                        }
                    }
                } catch (e) {}
                return items;
            }""")
            hostname = urlparse(url).hostname or ""
            for item in ls_items:
                result.cookies.append(
                    DiscoveredCookie(
                        name=item["name"],
                        domain=hostname,
                        storage_type="local_storage",
                        value_length=item["valueLength"],
                        page_url=url,
                    )
                )

            # Enumerate sessionStorage
            ss_items = await page.evaluate("""() => {
                const items = [];
                try {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        if (key) {
                            items.push({
                                name: key,
                                valueLength: (sessionStorage.getItem(key) || '').length,
                            });
                        }
                    }
                } catch (e) {}
                return items;
            }""")
            for item in ss_items:
                result.cookies.append(
                    DiscoveredCookie(
                        name=item["name"],
                        domain=hostname,
                        storage_type="session_storage",
                        value_length=item["valueLength"],
                        page_url=url,
                    )
                )

        except Exception as exc:
            result.error = str(exc)
            logger.warning("Failed to crawl %s: %s", url, exc)
        finally:
            if context:
                await context.close()

        return result


def _get_script_initiator(request: Request) -> str | None:
    """Walk the request chain to find the originating script URL.

    Returns a single script URL for backwards compatibility. For the full
    initiator path, use :func:`_build_initiator_chain` instead.
    """
    seen: set[str] = set()
    current = request
    while current:
        url = current.url
        if url in seen:
            break
        seen.add(url)
        if url.endswith(".js") or "javascript" in (current.resource_type or ""):
            return url
        redirected = current.redirected_from
        if redirected:
            current = redirected
        else:
            break
    return None


def _build_initiator_chain(
    url: str,
    initiator_map: dict[str, str],
    max_depth: int = 20,
) -> list[str]:
    """Build the full initiator chain from a URL back to the root.

    Walks the initiator map from *url* towards the top-level page,
    producing a list ordered root-first (i.e. the page URL at index 0
    and the leaf request URL at the end).
    """
    chain = [url]
    seen: set[str] = {url}
    current = url
    for _ in range(max_depth):
        parent = initiator_map.get(current, "")
        if not parent or parent in seen:
            break
        chain.append(parent)
        seen.add(parent)
        current = parent
    chain.reverse()  # Root first
    return chain
