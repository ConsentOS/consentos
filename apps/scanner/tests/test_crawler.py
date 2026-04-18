"""Tests for the Playwright cookie crawler — CMP-21.

These tests mock Playwright to avoid requiring an actual browser.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.crawler import (
    _ALL_CATEGORIES,
    _CONSENT_COOKIE_NAME,
    CookieCrawler,
    CrawlResult,
    DiscoveredCookie,
    SiteCrawlResult,
    _build_consent_cookie,
    _build_initiator_chain,
    _get_script_initiator,
)

# ── Fixtures ────────────────────────────────────────────────────────────


def _make_mock_page(
    *,
    cookies: list[dict] | None = None,
    ls_items: list[dict] | None = None,
    ss_items: list[dict] | None = None,
):
    """Build a mock Playwright Page object."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.on = MagicMock()  # synchronous registration

    # page.evaluate returns different results for localStorage vs sessionStorage
    eval_results = []
    eval_results.append(ls_items or [])
    eval_results.append(ss_items or [])
    page.evaluate = AsyncMock(side_effect=eval_results)

    return page


def _make_mock_context(
    page,
    cookies: list[dict] | None = None,
    delayed_cookies: list[dict] | None = None,
):
    """Build a mock BrowserContext.

    *cookies* is returned on the first ``context.cookies()`` call (the
    initial CDP enumeration).  *delayed_cookies* is returned on the
    second call (the delayed pass); defaults to the same list so
    existing tests need no changes.
    """
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    first = cookies or []
    second = delayed_cookies if delayed_cookies is not None else first
    # The crawler calls context.cookies() twice per page (initial +
    # delayed pass). Using a cycling function instead of a fixed-length
    # side_effect list so multi-page tests don't exhaust the mock.
    _cycle = [first, second]
    _call_count = 0

    async def _cycling_cookies(*_args, **_kwargs):
        nonlocal _call_count
        result = _cycle[_call_count % len(_cycle)]
        _call_count += 1
        return result

    context.cookies = AsyncMock(side_effect=_cycling_cookies)
    context.clear_cookies = AsyncMock()
    context.close = AsyncMock()
    return context


def _make_mock_browser(context):
    """Build a mock Browser."""
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    return browser


# ── DiscoveredCookie dataclass ──────────────────────────────────────────


class TestDiscoveredCookie:
    def test_defaults(self):
        c = DiscoveredCookie(name="_ga", domain="example.com")
        assert c.storage_type == "cookie"
        assert c.path is None
        assert c.expires is None
        assert c.http_only is None
        assert c.secure is None
        assert c.same_site is None
        assert c.value_length == 0
        assert c.script_source is None
        assert c.page_url == ""

    def test_initiator_chain_defaults_to_empty(self):
        c = DiscoveredCookie(name="_ga", domain="example.com")
        assert c.initiator_chain == []

    def test_with_all_fields(self):
        c = DiscoveredCookie(
            name="_ga",
            domain=".example.com",
            storage_type="cookie",
            path="/",
            expires=1700000000.0,
            http_only=True,
            secure=True,
            same_site="Lax",
            value_length=42,
            script_source="https://cdn.example.com/tracker.js",
            page_url="https://example.com/",
            initiator_chain=["https://example.com/", "https://cdn.example.com/tracker.js"],
        )
        assert c.http_only is True
        assert c.value_length == 42
        assert len(c.initiator_chain) == 2


# ── CrawlResult dataclass ──────────────────────────────────────────────


class TestCrawlResult:
    def test_defaults(self):
        r = CrawlResult(url="https://example.com/")
        assert r.cookies == []
        assert r.error is None

    def test_with_error(self):
        r = CrawlResult(url="https://example.com/", error="Timeout")
        assert r.error == "Timeout"


# ── SiteCrawlResult ────────────────────────────────────────────────────


class TestSiteCrawlResult:
    def test_unique_cookies_deduplicates(self):
        cookie_a = DiscoveredCookie(name="_ga", domain="example.com", storage_type="cookie")
        cookie_b = DiscoveredCookie(name="_ga", domain="example.com", storage_type="cookie")
        cookie_c = DiscoveredCookie(name="_gid", domain="example.com", storage_type="cookie")

        result = SiteCrawlResult(
            domain="example.com",
            pages=[
                CrawlResult(url="https://example.com/", cookies=[cookie_a, cookie_c]),
                CrawlResult(url="https://example.com/about", cookies=[cookie_b]),
            ],
            total_cookies_found=3,
        )

        unique = result.unique_cookies
        assert len(unique) == 2
        names = {c.name for c in unique}
        assert names == {"_ga", "_gid"}

    def test_unique_cookies_separates_storage_types(self):
        """Same name in cookie vs localStorage should be separate entries."""
        cookie = DiscoveredCookie(name="token", domain="example.com", storage_type="cookie")
        ls = DiscoveredCookie(name="token", domain="example.com", storage_type="local_storage")

        result = SiteCrawlResult(
            domain="example.com",
            pages=[CrawlResult(url="https://example.com/", cookies=[cookie, ls])],
            total_cookies_found=2,
        )

        assert len(result.unique_cookies) == 2

    def test_empty_pages(self):
        result = SiteCrawlResult(domain="example.com")
        assert result.unique_cookies == []


# ── _get_script_initiator ──────────────────────────────────────────────


class TestGetScriptInitiator:
    def test_identifies_js_url(self):
        request = MagicMock()
        request.url = "https://cdn.example.com/tracker.js"
        request.resource_type = "script"
        request.redirected_from = None

        assert _get_script_initiator(request) == "https://cdn.example.com/tracker.js"

    def test_follows_redirect_chain(self):
        original = MagicMock()
        original.url = "https://cdn.example.com/analytics.js"
        original.resource_type = "script"
        original.redirected_from = None

        redirect = MagicMock()
        redirect.url = "https://example.com/track"
        redirect.resource_type = "fetch"
        redirect.redirected_from = original

        assert _get_script_initiator(redirect) == "https://cdn.example.com/analytics.js"

    def test_returns_none_for_non_script(self):
        request = MagicMock()
        request.url = "https://example.com/image.png"
        request.resource_type = "image"
        request.redirected_from = None

        assert _get_script_initiator(request) is None

    def test_handles_javascript_resource_type(self):
        request = MagicMock()
        request.url = "https://example.com/bundle"
        request.resource_type = "javascript"
        request.redirected_from = None

        assert _get_script_initiator(request) == "https://example.com/bundle"

    def test_handles_circular_redirect(self):
        """Should not loop infinitely on circular redirects."""
        req_a = MagicMock()
        req_a.url = "https://example.com/a"
        req_a.resource_type = "fetch"

        req_b = MagicMock()
        req_b.url = "https://example.com/b"
        req_b.resource_type = "fetch"

        # Create circular chain
        req_a.redirected_from = req_b
        req_b.redirected_from = req_a

        # Should not hang — returns None since neither is a script
        result = _get_script_initiator(req_a)
        assert result is None


# ── _build_initiator_chain ────────────────────────────────────────────


class TestBuildInitiatorChain:
    def test_single_url_no_parent(self):
        chain = _build_initiator_chain("https://example.com/script.js", {})
        assert chain == ["https://example.com/script.js"]

    def test_two_level_chain(self):
        imap = {"https://cdn.example.com/tracker.js": "https://example.com/"}
        chain = _build_initiator_chain("https://cdn.example.com/tracker.js", imap)
        assert chain == ["https://example.com/", "https://cdn.example.com/tracker.js"]

    def test_three_level_chain(self):
        imap = {
            "https://cdn.example.com/pixel.js": "https://cdn.example.com/gtm.js",
            "https://cdn.example.com/gtm.js": "https://example.com/",
        }
        chain = _build_initiator_chain("https://cdn.example.com/pixel.js", imap)
        assert chain == [
            "https://example.com/",
            "https://cdn.example.com/gtm.js",
            "https://cdn.example.com/pixel.js",
        ]

    def test_respects_max_depth(self):
        # Build a chain longer than max_depth
        imap = {}
        for i in range(25):
            imap[f"https://example.com/s{i + 1}.js"] = f"https://example.com/s{i}.js"
        chain = _build_initiator_chain("https://example.com/s25.js", imap, max_depth=5)
        # Should be capped: the leaf + 5 parents = 6 entries at most
        assert len(chain) <= 6

    def test_handles_circular_reference(self):
        imap = {
            "https://a.com/a.js": "https://b.com/b.js",
            "https://b.com/b.js": "https://a.com/a.js",
        }
        chain = _build_initiator_chain("https://a.com/a.js", imap)
        # Should not loop — cycle detected via seen set
        assert len(chain) == 2


# ── CookieCrawler._crawl_page ──────────────────────────────────────────


class TestCrawlPage:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_discovers_browser_cookies(self):
        cdp_cookies = [
            {
                "name": "_ga",
                "domain": ".example.com",
                "path": "/",
                "expires": 1700000000,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
                "value": "GA1.2.12345",
            }
        ]

        page = _make_mock_page()
        context = _make_mock_context(page, cookies=cdp_cookies)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        result = await crawler._crawl_page(browser, "https://example.com/")

        assert len(result.cookies) == 1
        assert result.cookies[0].name == "_ga"
        assert result.cookies[0].domain == ".example.com"
        assert result.cookies[0].storage_type == "cookie"
        assert result.cookies[0].secure is True
        assert result.cookies[0].value_length == len("GA1.2.12345")
        assert result.error is None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_discovers_local_storage(self):
        ls_items = [{"name": "theme", "valueLength": 4}]

        page = _make_mock_page(ls_items=ls_items)
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        result = await crawler._crawl_page(browser, "https://example.com/")

        ls_cookies = [c for c in result.cookies if c.storage_type == "local_storage"]
        assert len(ls_cookies) == 1
        assert ls_cookies[0].name == "theme"
        assert ls_cookies[0].value_length == 4
        assert ls_cookies[0].domain == "example.com"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_discovers_session_storage(self):
        ss_items = [{"name": "session_id", "valueLength": 36}]

        page = _make_mock_page(ss_items=ss_items)
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        result = await crawler._crawl_page(browser, "https://example.com/")

        ss_cookies = [c for c in result.cookies if c.storage_type == "session_storage"]
        assert len(ss_cookies) == 1
        assert ss_cookies[0].name == "session_id"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_handles_page_error(self):
        page = _make_mock_page()
        page.goto = AsyncMock(side_effect=Exception("Navigation timeout"))
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        result = await crawler._crawl_page(browser, "https://example.com/")

        assert result.error == "Navigation timeout"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_context_closed_after_crawl(self):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        await crawler._crawl_page(browser, "https://example.com/")

        context.close.assert_awaited_once()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_context_closed_on_error(self):
        page = _make_mock_page()
        page.goto = AsyncMock(side_effect=Exception("fail"))
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        await crawler._crawl_page(browser, "https://example.com/")

        context.close.assert_awaited_once()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_user_agent(self):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler(user_agent="CMPBot/1.0")
        await crawler._crawl_page(browser, "https://example.com/")

        browser.new_context.assert_awaited_once()
        call_kwargs = browser.new_context.call_args[1]
        assert call_kwargs["user_agent"] == "CMPBot/1.0"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_two_pass_cookie_collection_merges_delayed(self):
        """Cookies appearing only in the second CDP pass are still discovered."""
        first_pass = [
            {"name": "_ga", "domain": ".example.com", "value": "GA1.2.12345"},
        ]
        second_pass = [
            {"name": "_ga", "domain": ".example.com", "value": "GA1.2.12345"},
            {"name": "_gid", "domain": ".example.com", "value": "GID.99"},
        ]

        page = _make_mock_page()
        context = _make_mock_context(page, cookies=first_pass, delayed_cookies=second_pass)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        result = await crawler._crawl_page(browser, "https://example.com/")

        cookie_names = [c.name for c in result.cookies if c.storage_type == "cookie"]
        assert "_ga" in cookie_names
        assert "_gid" in cookie_names
        # _ga must not be duplicated
        assert cookie_names.count("_ga") == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_uses_networkidle_wait(self):
        """page.goto must use wait_until='networkidle'."""
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        crawler = CookieCrawler()
        await crawler._crawl_page(browser, "https://example.com/")

        page.goto.assert_awaited_once()
        call_kwargs = page.goto.call_args[1]
        assert call_kwargs.get("wait_until") == "networkidle"


# ── CookieCrawler.crawl_site ───────────────────────────────────────────


class TestCrawlSite:
    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.crawler.async_playwright")
    async def test_crawls_multiple_pages(self, mock_pw):
        cdp_cookies = [{"name": "_ga", "domain": ".example.com", "value": "x"}]

        page = _make_mock_page()
        context = _make_mock_context(page, cookies=cdp_cookies)
        browser = _make_mock_browser(context)

        pw_instance = AsyncMock()
        pw_instance.chromium.launch = AsyncMock(return_value=browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        crawler = CookieCrawler()
        result = await crawler.crawl_site(["https://example.com/", "https://example.com/about"])

        assert result.domain == "example.com"
        assert len(result.pages) == 2
        assert result.total_cookies_found >= 2

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.crawler.async_playwright")
    async def test_respects_max_pages(self, mock_pw):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        pw_instance = AsyncMock()
        pw_instance.chromium.launch = AsyncMock(return_value=browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        urls = [f"https://example.com/page{i}" for i in range(10)]
        crawler = CookieCrawler()
        result = await crawler.crawl_site(urls, max_pages=3)

        assert len(result.pages) == 3

    @pytest.mark.asyncio(loop_scope="session")
    async def test_empty_urls(self):
        crawler = CookieCrawler()
        result = await crawler.crawl_site([])

        assert result.domain == ""
        assert result.pages == []

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.crawler.async_playwright")
    async def test_browser_closed_after_crawl(self, mock_pw):
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        pw_instance = AsyncMock()
        pw_instance.chromium.launch = AsyncMock(return_value=browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        crawler = CookieCrawler()
        await crawler.crawl_site(["https://example.com/"])

        browser.close.assert_awaited_once()


# ── Consent pre-seed ────────────────────────────────────────────────────


class TestBuildConsentCookie:
    """The pre-seeded ``_consentos_consent`` cookie."""

    def test_cookie_name_matches_loader(self):
        cookie = _build_consent_cookie("https://example.com/")
        assert cookie["name"] == _CONSENT_COOKIE_NAME == "_consentos_consent"

    def test_cookie_is_url_scoped_for_playwright(self):
        """``url`` lets Playwright derive domain / path / secure."""
        cookie = _build_consent_cookie("https://example.com/page")
        assert cookie["url"] == "https://example.com/page"
        # ``path`` is NOT set explicitly — Playwright derives it from ``url``.
        # Setting both would cause ``add_cookies`` to reject the cookie.
        assert "path" not in cookie

    def test_cookie_value_decodes_to_consent_state_with_all_categories(self):
        import json as _json
        from urllib.parse import unquote

        cookie = _build_consent_cookie("https://example.com/")
        state = _json.loads(unquote(cookie["value"]))

        assert sorted(state["accepted"]) == sorted(_ALL_CATEGORIES)
        assert state["rejected"] == []
        # ConsentState fields the loader's readConsent() relies on
        assert "visitorId" in state
        assert "consentedAt" in state
        assert "bannerVersion" in state

    def test_cookie_expires_far_in_future(self):
        import time as _time

        cookie = _build_consent_cookie("https://example.com/")
        # ~1 year, allow generous slack for test timing
        assert cookie["expires"] > _time.time() + 300 * 86400

    @pytest.mark.asyncio(loop_scope="session")
    @patch("src.crawler.async_playwright")
    async def test_crawl_seeds_consent_before_navigation(self, mock_pw):
        """``add_cookies`` must be called before ``page.goto``."""
        page = _make_mock_page()
        context = _make_mock_context(page)
        browser = _make_mock_browser(context)

        # Track call order on the context
        call_order: list[str] = []
        original_add = context.add_cookies
        original_clear = context.clear_cookies

        async def _add(*args, **kwargs):
            call_order.append("add_cookies")
            return await original_add(*args, **kwargs)

        async def _clear(*args, **kwargs):
            call_order.append("clear_cookies")
            return await original_clear(*args, **kwargs)

        async def _goto(*args, **kwargs):
            call_order.append("goto")

        context.add_cookies = AsyncMock(side_effect=_add)
        context.clear_cookies = AsyncMock(side_effect=_clear)
        page.goto = AsyncMock(side_effect=_goto)

        pw_instance = AsyncMock()
        pw_instance.chromium.launch = AsyncMock(return_value=browser)
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=pw_instance)
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

        crawler = CookieCrawler()
        await crawler.crawl_site(["https://example.com/"])

        assert call_order == ["clear_cookies", "add_cookies", "goto"], call_order

        # And the cookie payload was the one we expect
        seeded = context.add_cookies.call_args.args[0]
        assert len(seeded) == 1
        assert seeded[0]["name"] == "_consentos_consent"
        assert seeded[0]["url"] == "https://example.com/"
