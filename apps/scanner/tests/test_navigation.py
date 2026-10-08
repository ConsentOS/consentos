"""Tests for the scanner navigation policy."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from playwright.async_api import Error as PlaywrightError

from src.navigation import (
    MAX_NAVIGATION_REDIRECTS,
    NavigationBlockedError,
    NavigationPolicy,
    filter_site_urls,
    host_in_domains,
    is_public_address,
    is_site_url,
    is_valid_hostname,
    resolve_host,
    site_domains,
    strip_port,
)


def _resolver(mapping: dict[str, list[str]]):
    """Build a fake resolver backed by *mapping*; unknown hosts fail."""
    calls: list[str] = []

    async def resolve(host: str) -> list[str]:
        calls.append(host)
        if host not in mapping:
            raise OSError("not found")
        return mapping[host]

    resolve.calls = calls
    return resolve


def _route(url: str, *, navigation: bool = False, responses: list | None = None):
    route = MagicMock()
    route.request.url = url
    route.request.is_navigation_request = MagicMock(return_value=navigation)
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()
    route.fetch = AsyncMock(side_effect=responses or [])
    return route


def _response(status: int, location: str | None = None):
    response = MagicMock()
    response.status = status
    response.headers = {"location": location} if location else {}
    return response


# ── is_public_address ──────────────────────────────────────────────────


class TestIsPublicAddress:
    @pytest.mark.parametrize(
        "address",
        [
            "10.0.0.1",
            "172.16.5.4",
            "192.168.1.1",
            "127.0.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "224.0.0.1",
            "240.0.0.1",
            "255.255.255.255",
            "::1",
            "::",
            "fe80::1",
            "fe80::1%eth0",
            "fc00::1",
            "fd12:3456::1",
            "ff02::1",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "not-an-ip",
        ],
    )
    def test_non_public(self, address):
        assert is_public_address(address) is False

    @pytest.mark.parametrize(
        "address",
        ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946", "::ffff:8.8.8.8"],
    )
    def test_public(self, address):
        assert is_public_address(address) is True


# ── Domain helpers ─────────────────────────────────────────────────────


class TestDomainHelpers:
    def test_site_domains_strips_www_and_dedupes(self):
        assert site_domains("WWW.Example.com.", ["example.com", "shop.example.org"]) == [
            "example.com",
            "shop.example.org",
        ]

    def test_site_domains_strips_port(self):
        assert site_domains("localhost:3000", ["intranet.local:8443"]) == [
            "localhost",
            "intranet.local",
        ]

    def test_strip_port(self):
        assert strip_port("localhost:3000") == "localhost"
        assert strip_port("example.com") == "example.com"
        assert strip_port("example.com:abc") == "example.com:abc"

    def test_host_in_domains(self):
        domains = ["example.com"]
        assert host_in_domains("example.com", domains)
        assert host_in_domains("blog.example.com", domains)
        assert not host_in_domains("notexample.com", domains)
        assert not host_in_domains("example.com.evil.net", domains)

    def test_is_site_url(self):
        domains = ["example.com"]
        assert is_site_url("https://www.example.com/a", domains)
        assert is_site_url("http://example.com/", domains)
        assert not is_site_url("ftp://example.com/", domains)
        assert not is_site_url("https://other.net/", domains)
        assert not is_site_url("https://example.com@10.0.0.1/", domains)
        assert not is_site_url("/relative", domains)
        assert not is_site_url("http://[::1/", domains)

    def test_filter_site_urls(self):
        urls = [
            "https://example.com/",
            "https://cdn.example.com/x",
            "http://169.254.169.254/latest",
            "file:///etc/hosts",
            "https://elsewhere.org/",
        ]
        assert filter_site_urls(urls, ["example.com"]) == [
            "https://example.com/",
            "https://cdn.example.com/x",
        ]

    @pytest.mark.parametrize("domain", ["example.com", "sub.example.co.uk", "münchen.de"])
    def test_valid_hostnames(self, domain):
        assert is_valid_hostname(domain)

    @pytest.mark.parametrize(
        "domain",
        ["https://example.com", "example.com/path", "example.com:8080", "a@b.com", "", "a b"],
    )
    def test_invalid_hostnames(self, domain):
        assert not is_valid_hostname(domain)

    @pytest.mark.parametrize("domain", ["localhost:3000", "intranet.example.com:8443"])
    def test_ports_accepted_when_allowed(self, domain):
        assert is_valid_hostname(domain, allow_port=True)
        assert not is_valid_hostname(domain)

    @pytest.mark.parametrize(
        "domain", ["localhost:", "localhost:0", "localhost:65536", "localhost:abc", ":3000"]
    )
    def test_invalid_ports_rejected(self, domain):
        assert not is_valid_hostname(domain, allow_port=True)


# ── NavigationPolicy ───────────────────────────────────────────────────


class TestNavigationPolicy:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_public_host_allowed(self):
        policy = NavigationPolicy(resolver=_resolver({"example.com": ["93.184.216.34"]}))
        assert await policy.is_allowed("https://example.com/")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_host_resolving_to_private_address_blocked(self):
        policy = NavigationPolicy(resolver=_resolver({"intranet.example.com": ["10.1.2.3"]}))
        assert not await policy.is_allowed("https://intranet.example.com/")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_mixed_addresses_blocked(self):
        resolver = _resolver({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]})
        policy = NavigationPolicy(resolver=resolver)
        assert not await policy.is_allowed("https://mixed.example.com/")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_unresolvable_host_blocked(self):
        policy = NavigationPolicy(resolver=_resolver({}))
        assert not await policy.is_allowed("https://missing.example.com/")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_failed_lookup_not_cached(self):
        mapping: dict[str, list[str]] = {}
        resolver = _resolver(mapping)
        policy = NavigationPolicy(resolver=resolver)
        assert not await policy.is_allowed("https://flaky.example.com/a")
        mapping["flaky.example.com"] = ["93.184.216.34"]
        assert await policy.is_allowed("https://flaky.example.com/b")
        assert resolver.calls == ["flaky.example.com", "flaky.example.com"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_ip_literals_skip_resolver(self):
        resolver = _resolver({})
        policy = NavigationPolicy(resolver=resolver)
        assert not await policy.is_allowed("http://169.254.169.254/page")
        assert not await policy.is_allowed("http://[::1]:8080/")
        assert await policy.is_allowed("http://8.8.8.8/")
        assert resolver.calls == []

    @pytest.mark.asyncio(loop_scope="session")
    async def test_non_http_schemes_blocked(self):
        policy = NavigationPolicy(allow_private_networks=True)
        assert not await policy.is_allowed("file:///tmp/page.html")
        assert not await policy.is_allowed("ftp://example.com/")
        assert not await policy.is_allowed("https:///nohost")
        assert not await policy.is_allowed("http://[::1/")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_lookups_cached_per_host(self):
        resolver = _resolver({"example.com": ["93.184.216.34"]})
        policy = NavigationPolicy(resolver=resolver)
        await policy.is_allowed("https://example.com/a")
        await policy.is_allowed("https://EXAMPLE.com/b")
        assert resolver.calls == ["example.com"]

    @pytest.mark.asyncio(loop_scope="session")
    async def test_opt_out_allows_private_hosts(self):
        resolver = _resolver({})
        policy = NavigationPolicy(allow_private_networks=True, resolver=resolver)
        assert await policy.is_allowed("http://localhost:8080/")
        assert await policy.is_allowed("http://10.0.0.5/")
        assert resolver.calls == []

    @pytest.mark.asyncio(loop_scope="session")
    async def test_check_raises(self):
        policy = NavigationPolicy()
        with pytest.raises(NavigationBlockedError):
            await policy.check("http://127.0.0.1/")
        await NavigationPolicy(allow_private_networks=True).check("http://127.0.0.1/")


class TestRouteHandler:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_continues_public_request(self):
        policy = NavigationPolicy(resolver=_resolver({"example.com": ["93.184.216.34"]}))
        route = _route("https://example.com/script.js")
        await policy.handle_route(route)
        route.continue_.assert_awaited_once()
        route.abort.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_aborts_private_request(self):
        policy = NavigationPolicy(resolver=_resolver({"localhost": ["127.0.0.1"]}))
        route = _route("http://localhost:6379/")
        await policy.handle_route(route)
        route.abort.assert_awaited_once_with("blockedbyclient")
        route.continue_.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_aborts_private_navigation_without_fetching(self):
        policy = NavigationPolicy(resolver=_resolver({}))
        route = _route("http://10.0.0.1/", navigation=True)
        await policy.handle_route(route)
        route.abort.assert_awaited_once_with("blockedbyclient")
        route.fetch.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_navigation_without_redirect_is_fulfilled(self):
        policy = NavigationPolicy(resolver=_resolver({"example.com": ["93.184.216.34"]}))
        page = _response(200)
        route = _route("https://example.com/", navigation=True, responses=[page])
        await policy.handle_route(route)
        route.fetch.assert_awaited_once_with(max_redirects=0)
        route.fulfill.assert_awaited_once_with(response=page)
        route.continue_.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_navigation_redirect_to_private_address_aborted(self):
        resolver = _resolver(
            {"example.com": ["93.184.216.34"], "internal.example.net": ["10.0.0.7"]}
        )
        policy = NavigationPolicy(resolver=resolver)
        route = _route(
            "https://example.com/",
            navigation=True,
            responses=[_response(302, "http://internal.example.net/admin")],
        )
        await policy.handle_route(route)
        route.abort.assert_awaited_once_with("blockedbyclient")
        route.fetch.assert_awaited_once_with(max_redirects=0)
        route.fulfill.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_later_redirect_hop_to_private_address_aborted(self):
        policy = NavigationPolicy(resolver=_resolver({"example.com": ["93.184.216.34"]}))
        route = _route(
            "https://example.com/",
            navigation=True,
            responses=[_response(301, "/home"), _response(307, "http://169.254.169.254/")],
        )
        await policy.handle_route(route)
        route.abort.assert_awaited_once_with("blockedbyclient")
        assert route.fetch.await_count == 2
        route.fulfill.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_allowed_redirect_chain_sends_browser_to_final_url(self):
        resolver = _resolver(
            {"example.com": ["93.184.216.34"], "www.example.com": ["93.184.216.34"]}
        )
        policy = NavigationPolicy(resolver=resolver)
        route = _route(
            "http://example.com/",
            navigation=True,
            responses=[
                _response(301, "https://example.com/"),
                _response(302, "https://www.example.com/start"),
                _response(200),
            ],
        )
        await policy.handle_route(route)
        assert route.fetch.await_args_list[1].kwargs == {
            "url": "https://example.com/",
            "max_redirects": 0,
        }
        route.fulfill.assert_awaited_once_with(
            status=302, headers={"location": "https://www.example.com/start"}
        )
        route.abort.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_redirect_loop_aborted(self):
        policy = NavigationPolicy(resolver=_resolver({"example.com": ["93.184.216.34"]}))
        route = _route(
            "https://example.com/",
            navigation=True,
            responses=[_response(302, "/again")] * (MAX_NAVIGATION_REDIRECTS + 1),
        )
        await policy.handle_route(route)
        route.abort.assert_awaited_once_with("failed")
        route.fulfill.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_navigation_fetch_error_aborted(self):
        policy = NavigationPolicy(resolver=_resolver({"example.com": ["93.184.216.34"]}))
        route = _route("https://example.com/", navigation=True)
        route.fetch = AsyncMock(side_effect=PlaywrightError("net::ERR_CONNECTION_RESET"))
        await policy.handle_route(route)
        route.abort.assert_awaited_once_with("failed")
        route.fulfill.assert_not_called()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_apply_installs_route(self):
        policy = NavigationPolicy()
        context = AsyncMock()
        await policy.apply(context)
        context.route.assert_awaited_once_with("**/*", policy.handle_route)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_apply_noop_when_opted_out(self):
        context = AsyncMock()
        await NavigationPolicy(allow_private_networks=True).apply(context)
        context.route.assert_not_called()


class TestHttpxHook:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_blocks_redirect_to_private_host(self):
        policy = NavigationPolicy(resolver=_resolver({"example.com": ["93.184.216.34"]}))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.com":
                return httpx.Response(302, headers={"location": "http://10.0.0.1/"})
            return httpx.Response(200, text="should not reach")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
            event_hooks={"request": [policy.httpx_request_hook]},
        ) as client:
            with pytest.raises(NavigationBlockedError):
                await client.get("https://example.com/sitemap.xml")


class TestResolveHost:
    @pytest.mark.asyncio(loop_scope="session")
    async def test_resolves_localhost(self):
        addresses = await resolve_host("localhost")
        assert addresses
        assert all(not is_public_address(a) for a in addresses)
