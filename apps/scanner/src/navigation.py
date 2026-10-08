"""Navigation policy for the scanner.

Keeps the browser and the sitemap fetcher on public hosts, and keeps
discovered URLs on the site's own domains.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urljoin, urlparse

from playwright.async_api import Error as PlaywrightError

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})

MAX_NAVIGATION_REDIRECTS = 10

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9])?\.)*[a-z0-9_-]+$")

Resolver = Callable[[str], Awaitable[list[str]]]


class NavigationBlockedError(Exception):
    """Raised when a URL is outside the scanner's navigation policy."""


def is_public_address(address: str) -> bool:
    """Return True if *address* is a globally routable unicast IP."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


async def resolve_host(host: str) -> list[str]:
    """Resolve *host* to its IP addresses using the event loop resolver."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def normalise_domain(domain: str) -> str:
    """Lower-case *domain* and strip a trailing dot."""
    return domain.strip().lower().rstrip(".")


def strip_port(domain: str) -> str:
    """Return *domain* without a trailing ``:port``."""
    host, sep, port = domain.rpartition(":")
    return host if sep and port.isascii() and port.isdigit() else domain


def is_valid_hostname(domain: str, *, allow_port: bool = False) -> bool:
    """Return True if *domain* is a bare hostname (no scheme or path).

    A ``:port`` suffix is accepted only when *allow_port* is set.
    """
    host = normalise_domain(domain)
    if allow_port and ":" in host:
        host, _, port = host.rpartition(":")
        if not (port.isascii() and port.isdigit() and 0 < int(port) < 65536):
            return False
    try:
        ascii_domain = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return bool(_HOSTNAME_RE.match(ascii_domain))


def site_domains(domain: str, extra: Iterable[str] = ()) -> list[str]:
    """Return the base domains a site's URLs may live on.

    A leading ``www.`` is dropped so the apex and its other subdomains
    are included.
    """
    domains: list[str] = []
    for value in (domain, *extra):
        base = strip_port(normalise_domain(value))
        if base.startswith("www."):
            base = base[4:]
        if base and base not in domains:
            domains.append(base)
    return domains


def host_in_domains(host: str, domains: Iterable[str]) -> bool:
    """Return True if *host* equals or is a subdomain of any of *domains*."""
    host = normalise_domain(host)
    return any(host == d or host.endswith(f".{d}") for d in domains)


def is_site_url(url: str, domains: Iterable[str]) -> bool:
    """Return True if *url* is http(s) and its host is on one of *domains*."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        return False
    return host_in_domains(parsed.hostname, domains)


def filter_site_urls(urls: Iterable[str], domains: Iterable[str]) -> list[str]:
    """Keep only the URLs that belong to the site's domains."""
    domains = list(domains)
    kept: list[str] = []
    for url in urls:
        if is_site_url(url, domains):
            kept.append(url)
        else:
            logger.debug("Skipping URL outside site domains: %s", url)
    return kept


class NavigationPolicy:
    """Decides whether the scanner may request a URL.

    Each instance caches successful host lookups, so create one per
    scan. Failed lookups are not cached and are retried on the next
    request to that host.
    """

    def __init__(
        self,
        *,
        allow_private_networks: bool = False,
        resolver: Resolver = resolve_host,
    ) -> None:
        self.allow_private_networks = allow_private_networks
        self._resolver = resolver
        self._host_cache: dict[str, bool] = {}

    async def is_public_host(self, host: str) -> bool:
        """Return True if every address *host* resolves to is public."""
        host = normalise_domain(host).strip("[]")
        if host in self._host_cache:
            return self._host_cache[host]
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
            addresses = [host]
        except ValueError:
            try:
                addresses = await self._resolver(host)
            except (OSError, UnicodeError) as exc:
                logger.debug("Could not resolve %s: %s", host, exc)
                return False
        allowed = bool(addresses) and all(is_public_address(a) for a in addresses)
        self._host_cache[host] = allowed
        return allowed

    async def is_allowed(self, url: str) -> bool:
        """Return True if the scanner may request *url*."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname
        except ValueError:
            return False
        if parsed.scheme not in ALLOWED_SCHEMES or not host:
            return False
        if self.allow_private_networks:
            return True
        return await self.is_public_host(host)

    async def check(self, url: str) -> None:
        """Raise :class:`NavigationBlockedError` if *url* is not allowed."""
        if not await self.is_allowed(url):
            raise NavigationBlockedError(f"Navigation to {url} is not permitted")

    async def handle_route(self, route) -> None:  # noqa: ANN001
        """Playwright route handler: check every request against the policy.

        Allowed subresource requests continue as normal. Navigation
        requests are fetched here so each redirect hop is checked too.
        """
        request = route.request
        if not await self.is_allowed(request.url):
            await _block(route, request.url)
        elif request.is_navigation_request():
            await self._fetch_navigation(route)
        else:
            await route.continue_()

    async def _fetch_navigation(self, route) -> None:  # noqa: ANN001
        """Follow a navigation's redirects, checking each hop.

        Playwright only routes the first URL of a redirect chain, so
        hops are fetched one at a time and any hop outside the policy
        aborts the navigation. If the chain ends on the requested URL
        its response is fulfilled directly. Otherwise the browser is
        sent a single redirect to the final URL, so the page loads with
        that URL's origin rather than the original one.
        """
        request_url = route.request.url
        url = request_url
        try:
            response = await route.fetch(max_redirects=0)
            hops = 0
            while response.status in _REDIRECT_STATUSES and response.headers.get("location"):
                hops += 1
                if hops > MAX_NAVIGATION_REDIRECTS:
                    logger.info("Too many redirects from %s", request_url)
                    await route.abort("failed")
                    return
                url = urljoin(url, response.headers["location"])
                if not await self.is_allowed(url):
                    await _block(route, url)
                    return
                response = await route.fetch(url=url, max_redirects=0)
        except PlaywrightError as exc:
            logger.info("Navigation fetch failed for %s: %s", url, exc)
            await route.abort("failed")
            return
        if url == request_url:
            await route.fulfill(response=response)
        else:
            await route.fulfill(status=302, headers={"location": url})

    async def apply(self, context) -> None:  # noqa: ANN001
        """Install the route guard on a Playwright browser context."""
        if self.allow_private_networks:
            return
        await context.route("**/*", self.handle_route)

    async def httpx_request_hook(self, request) -> None:  # noqa: ANN001
        """httpx request event hook; also runs for each redirect hop."""
        await self.check(str(request.url))


async def _block(route, url: str) -> None:  # noqa: ANN001
    logger.info("Blocked scanner request to %s", url)
    await route.abort("blockedbyclient")
