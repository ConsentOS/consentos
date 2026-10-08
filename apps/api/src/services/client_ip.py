"""Resolve the originating client IP address for a request.

``X-Forwarded-For`` and ``X-Real-IP`` are only honoured when the direct
peer is listed in ``TRUSTED_PROXIES``. Otherwise the peer address is
used as-is.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence

from starlette.requests import Request

from src.config.settings import IPNetwork, get_settings

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _parse_ip(value: str | None) -> IPAddress | None:
    if not value:
        return None
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_trusted(ip: IPAddress, trusted: Sequence[IPNetwork]) -> bool:
    return any(ip in network for network in trusted)


def resolve_client_ip(request: Request, trusted: Sequence[IPNetwork]) -> str | None:
    """Return the client IP, honouring forwarded headers from trusted peers only."""
    peer = request.client.host if request.client else None
    peer_ip = _parse_ip(peer)
    if peer_ip is None or not _is_trusted(peer_ip, trusted):
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",")]
        # Each proxy appends the address it received the request from,
        # so walk right to left and stop at the first hop we don't trust.
        for hop in reversed(hops):
            hop_ip = _parse_ip(hop)
            if hop_ip is None:
                return str(peer_ip)
            if not _is_trusted(hop_ip, trusted):
                return str(hop_ip)
        return str(_parse_ip(hops[0]))

    real_ip = _parse_ip(request.headers.get("x-real-ip"))
    if real_ip is not None:
        return str(real_ip)

    return str(peer_ip)


def get_client_ip(request: Request) -> str | None:
    """Resolve the client IP using the configured ``TRUSTED_PROXIES``."""
    return resolve_client_ip(request, get_settings().trusted_proxy_networks)
