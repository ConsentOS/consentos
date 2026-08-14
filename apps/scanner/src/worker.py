"""Scanner HTTP service.

Exposes an HTTP endpoint that accepts scan requests, runs the Playwright
cookie crawler, and returns discovered cookies. Called by the API's Celery
worker to execute scan jobs.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ── Settings ─────────────────────────────────────────────────────────


class ScannerSettings(BaseSettings):
    """Scanner service settings from environment."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "INFO"
    crawler_timeout_ms: int = 30_000
    crawler_headless: bool = True
    max_pages_per_scan: int = 50
    # Navigation wait strategy. "domcontentloaded" (default);
    # "networkidle" is discouraged by Playwright and timed out WordPress-style sites.
    # See CookieCrawler._wait_for_cookies_to_settle for the cookie settle wait.
    crawler_wait_until: str = "domcontentloaded"
    # Cookie settle wait knobs (see _wait_for_cookies_to_settle).
    crawler_settle_max_ms: int = 15_000
    crawler_stable_window_ms: int = 2_000


# ── Request / Response schemas ───────────────────────────────────────


class ProxyRequest(BaseModel):
    """Proxy configuration for geo-located scanning."""

    server: str
    username: str | None = None
    password: str | None = None


class ScanRequest(BaseModel):
    """Incoming scan request from the API worker."""

    domain: str
    urls: list[str] = Field(default_factory=list)
    max_pages: int = 50
    proxy: ProxyRequest | None = None


class DiscoveredCookieResponse(BaseModel):
    """A single cookie found during crawling."""

    name: str
    domain: str
    storage_type: str = "cookie"
    path: str | None = None
    expires: float | None = None
    http_only: bool | None = None
    secure: bool | None = None
    same_site: str | None = None
    value_length: int = 0
    script_source: str | None = None
    page_url: str = ""
    initiator_chain: list[str] = Field(default_factory=list)


class ScanResponse(BaseModel):
    """Result of a scan."""

    domain: str
    pages_crawled: int
    total_cookies: int
    cookies: list[DiscoveredCookieResponse]
    errors: list[str] = Field(default_factory=list)


class ValidationRequest(BaseModel):
    """Request for consent validation and dark pattern detection."""

    url: str
    essential_cookie_names: list[str] = Field(default_factory=list)
    proxy: ProxyRequest | None = None


class ValidationIssueResponse(BaseModel):
    """A single validation issue."""

    check: str
    severity: str
    message: str
    recommendation: str
    details: dict = Field(default_factory=dict)


class DarkPatternIssueResponse(BaseModel):
    """A detected dark pattern."""

    pattern: str
    severity: str
    message: str
    recommendation: str
    details: dict = Field(default_factory=dict)


class ValidationResponse(BaseModel):
    """Result of consent validation and dark pattern detection."""

    url: str
    pre_consent_issues: list[ValidationIssueResponse] = Field(default_factory=list)
    post_accept_issues: list[ValidationIssueResponse] = Field(default_factory=list)
    post_reject_issues: list[ValidationIssueResponse] = Field(default_factory=list)
    dark_pattern_issues: list[DarkPatternIssueResponse] = Field(default_factory=list)
    banner_found: bool = False
    errors: list[str] = Field(default_factory=list)


# ── Application ──────────────────────────────────────────────────────


def create_app():  # noqa: ANN201
    """Create the scanner FastAPI application."""
    from fastapi import FastAPI, HTTPException

    from src.crawler import CookieCrawler
    from src.sitemap import discover_urls

    app = FastAPI(title="CMP Scanner Service", version="0.1.0")
    settings = ScannerSettings()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/scan", response_model=ScanResponse)
    async def run_scan(body: ScanRequest) -> ScanResponse:
        """Execute a Playwright crawl and return discovered cookies."""
        # Discover URLs if none provided
        urls = body.urls
        if not urls:
            try:
                urls = await discover_urls(
                    body.domain, max_urls=min(body.max_pages, settings.max_pages_per_scan)
                )
            except Exception as exc:
                logger.warning("URL discovery failed for %s: %s", body.domain, exc)
                urls = [f"https://{body.domain}/"]

        if not urls:
            raise HTTPException(status_code=400, detail="No URLs to scan")

        # Run crawler
        from src.crawler import ProxyConfig

        proxy_config = None
        if body.proxy:
            proxy_config = ProxyConfig(
                server=body.proxy.server,
                username=body.proxy.username,
                password=body.proxy.password,
            )

        crawler = CookieCrawler(
            headless=settings.crawler_headless,
            timeout_ms=settings.crawler_timeout_ms,
            proxy=proxy_config,
            wait_until=settings.crawler_wait_until,
            settle_max_ms=settings.crawler_settle_max_ms,
            stable_window_ms=settings.crawler_stable_window_ms,
        )
        result = await crawler.crawl_site(
            urls, max_pages=min(body.max_pages, settings.max_pages_per_scan)
        )

        # Build response
        cookies = [
            DiscoveredCookieResponse(
                name=c.name,
                domain=c.domain,
                storage_type=c.storage_type,
                path=c.path,
                expires=c.expires,
                http_only=c.http_only,
                secure=c.secure,
                same_site=c.same_site,
                value_length=c.value_length,
                script_source=c.script_source,
                page_url=c.page_url,
                initiator_chain=c.initiator_chain,
            )
            for c in result.unique_cookies
        ]

        errors = [p.error for p in result.pages if p.error]

        return ScanResponse(
            domain=result.domain,
            pages_crawled=len(result.pages),
            total_cookies=result.total_cookies_found,
            cookies=cookies,
            errors=errors,
        )

    @app.post("/validate", response_model=ValidationResponse)
    async def run_validation(body: ValidationRequest) -> ValidationResponse:
        """Run consent signal validation and dark pattern detection."""
        from playwright.async_api import async_playwright

        from src.consent_validator import (
            _is_tracker_request,
            validate_post_accept,
            validate_post_reject,
            validate_pre_consent,
        )
        from src.crawler import ProxyConfig
        from src.dark_pattern_detector import detect_dark_patterns

        response = ValidationResponse(url=body.url)
        essential_names = set(body.essential_cookie_names)
        tracker_requests: list[str] = []

        proxy_config = None
        if body.proxy:
            proxy_config = ProxyConfig(
                server=body.proxy.server,
                username=body.proxy.username,
                password=body.proxy.password,
            )

        try:
            async with async_playwright() as pw:
                launch_kwargs: dict = {"headless": settings.crawler_headless}
                if proxy_config:
                    proxy_opts: dict = {"server": proxy_config.server}
                    if proxy_config.username:
                        proxy_opts["username"] = proxy_config.username
                    if proxy_config.password:
                        proxy_opts["password"] = proxy_config.password
                    launch_kwargs["proxy"] = proxy_opts

                browser = await pw.chromium.launch(**launch_kwargs)
                try:
                    context = await browser.new_context(ignore_https_errors=True)
                    page = await context.new_page()

                    # Track network requests for tracker detection
                    def _on_request(request) -> None:
                        if _is_tracker_request(request.url):
                            tracker_requests.append(request.url)

                    page.on("request", _on_request)

                    # ── Pre-consent check ────────────────────────
                    await page.goto(
                        body.url,
                        wait_until=settings.crawler_wait_until,
                        timeout=settings.crawler_timeout_ms,
                    )

                    pre_issues = await validate_pre_consent(
                        page, context, essential_names, tracker_requests
                    )
                    response.pre_consent_issues = [
                        ValidationIssueResponse(**vars(i)) for i in pre_issues
                    ]

                    # ── Dark pattern detection ───────────────────
                    dp_result = await detect_dark_patterns(page)
                    response.banner_found = dp_result.banner_found
                    response.dark_pattern_issues = [
                        DarkPatternIssueResponse(**vars(i)) for i in dp_result.issues
                    ]

                    # ── Post-accept check ────────────────────────
                    # Try to click Accept All
                    accept_selectors = [
                        "button:has-text('Accept All')",
                        "button:has-text('Accept')",
                        "button:has-text('Allow All')",
                        "button:has-text('I Agree')",
                        "[data-action='accept']",
                    ]
                    accepted = False
                    for selector in accept_selectors:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await page.wait_for_timeout(2000)
                                accepted = True
                                break
                        except Exception:
                            continue

                    if accepted:
                        tracker_requests.clear()
                        post_accept = await validate_post_accept(page, context)
                        response.post_accept_issues = [
                            ValidationIssueResponse(**vars(i)) for i in post_accept
                        ]

                    # ── Post-reject check ────────────────────────
                    # Reload and reject
                    await context.clear_cookies()
                    tracker_requests.clear()
                    await page.goto(
                        body.url,
                        wait_until=settings.crawler_wait_until,
                        timeout=settings.crawler_timeout_ms,
                    )

                    reject_selectors = [
                        "button:has-text('Reject All')",
                        "button:has-text('Reject')",
                        "button:has-text('Decline')",
                        "button:has-text('Deny')",
                        "[data-action='reject']",
                    ]
                    rejected = False
                    for selector in reject_selectors:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await page.wait_for_timeout(2000)
                                rejected = True
                                break
                        except Exception:
                            continue

                    if rejected:
                        post_reject_trackers: list[str] = []
                        # Collect any new tracker requests after rejection
                        for req_url in tracker_requests:
                            if _is_tracker_request(req_url):
                                post_reject_trackers.append(req_url)

                        post_reject = await validate_post_reject(
                            page, context, essential_names, post_reject_trackers
                        )
                        response.post_reject_issues = [
                            ValidationIssueResponse(**vars(i)) for i in post_reject
                        ]

                    await context.close()
                finally:
                    await browser.close()

        except Exception as exc:
            response.errors.append(str(exc))
            logger.warning("Validation failed for %s: %s", body.url, exc)

        return response

    return app


# ── Entrypoint ───────────────────────────────────────────────────────


def main() -> None:
    """Run the scanner service with uvicorn."""
    import uvicorn

    settings = ScannerSettings()
    logging.basicConfig(level=settings.log_level)

    uvicorn.run(
        "src.worker:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=1,  # Single worker — Playwright manages its own concurrency
        access_log=True,
    )


if __name__ == "__main__":
    main()
