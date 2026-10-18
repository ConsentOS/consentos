"""Check how the ConsentOS banner is installed on a page.

The loader tag is judged from the HTML the server sent, not from the
page after it has run, because tag managers insert their own scripts at
the top of ``<head>`` and would make the loader look out of place when
it isn't. Whether the banner then starts and fetches its configuration
is observed in the browser.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlparse

from src.navigation import NavigationPolicy

logger = logging.getLogger(__name__)

LOADER_FILENAME = "consent-loader.js"
BANNER_HOST_SELECTOR = "#consentos-banner-host"

# Script types a browser runs. Anything else (JSON-LD, templates, the
# blocked ``text/plain`` scripts the banner releases) doesn't run, so it
# doesn't count when deciding whether the loader comes first.
_EXECUTABLE_TYPES = {
    "",
    "text/javascript",
    "application/javascript",
    "module",
    "text/ecmascript",
    "application/ecmascript",
}


@dataclass
class LoaderTag:
    """The loader's ``<script>`` tag as found in the page's HTML."""

    src: str
    site_id: str | None
    api_base: str | None
    cdn_base: str | None
    is_async: bool
    is_defer: bool
    in_head: bool
    first_script: bool


@dataclass
class ConfigRequest:
    url: str
    status: int | None


@dataclass
class InstallCheckResult:
    url: str
    final_url: str | None = None
    reachable: bool = False
    error: str | None = None
    loader: LoaderTag | None = None
    config_requests: list[ConfigRequest] = field(default_factory=list)
    banner_rendered: bool = False


class _ScriptFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.seen_body = False
        self.executable_before = 0
        self.loader: LoaderTag | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "head":
            self.in_head = True
        elif tag == "body":
            self.in_head = False
            self.seen_body = True
        elif tag == "script":
            self._script(dict(attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.in_head = False

    def _script(self, attrs: dict[str, str | None]) -> None:
        src = attrs.get("src") or ""
        if self.loader is None and urlparse(src).path.endswith(f"/{LOADER_FILENAME}"):
            self.loader = LoaderTag(
                src=src,
                site_id=attrs.get("data-site-id"),
                api_base=attrs.get("data-api-base"),
                cdn_base=attrs.get("data-cdn-base"),
                is_async="async" in attrs,
                is_defer="defer" in attrs,
                in_head=self.in_head and not self.seen_body,
                first_script=self.executable_before == 0,
            )
            return
        script_type = (attrs.get("type") or "").strip().lower()
        if self.loader is None and script_type in _EXECUTABLE_TYPES:
            self.executable_before += 1


def find_loader(html: str) -> LoaderTag | None:
    """The first ConsentOS loader tag in ``html``, if there is one."""
    finder = _ScriptFinder()
    finder.feed(html)
    finder.close()
    return finder.loader


def is_config_request(url: str) -> bool:
    path = urlparse(url).path
    return "/config/sites/" in path and path.endswith("/geo-resolved")


async def check_install(
    url: str,
    *,
    headless: bool,
    timeout_ms: int,
    policy: NavigationPolicy,
    banner_wait_ms: int = 8_000,
) -> InstallCheckResult:
    """Load ``url`` as a first-time visitor and report how the banner is installed."""
    from playwright.async_api import async_playwright

    result = InstallCheckResult(url=url)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        try:
            # A fresh context has no consent cookie, so the banner shows.
            context = await browser.new_context(ignore_https_errors=True, service_workers="block")
            await policy.apply(context)
            page = await context.new_page()

            def on_response(response) -> None:  # noqa: ANN001
                if is_config_request(response.url):
                    result.config_requests.append(
                        ConfigRequest(url=response.url, status=response.status)
                    )

            def on_failed(request) -> None:  # noqa: ANN001
                if is_config_request(request.url):
                    result.config_requests.append(ConfigRequest(url=request.url, status=None))

            page.on("response", on_response)
            page.on("requestfailed", on_failed)

            try:
                response = await page.goto(url, wait_until="load", timeout=timeout_ms)
            except Exception as exc:
                result.error = str(exc).splitlines()[0]
                return result

            result.final_url = page.url
            if response is None or response.status >= 400:
                status = response.status if response else "no response"
                result.error = f"The page returned {status}"
                return result
            result.reachable = True
            result.loader = find_loader(await response.text())

            try:
                await page.wait_for_selector(
                    BANNER_HOST_SELECTOR, state="attached", timeout=banner_wait_ms
                )
                result.banner_rendered = True
            except Exception:
                result.banner_rendered = False
        finally:
            await browser.close()
    return result
