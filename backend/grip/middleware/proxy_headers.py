"""Trust forwarded headers, but only from configured proxies.

Behind the frontend's nginx (and the platform ingress in front of that) the
backend sees the proxy as its client, plain HTTP as its scheme and whatever
the proxy sent as its host. The ``X-Forwarded-*`` headers carry the real
values, but any client can send them too. This middleware applies them only
when the direct peer is on the ``TRUSTED_PROXIES`` list, and strips nothing
otherwise: an untrusted request is simply taken at face value.

Applied values:

* ``X-Forwarded-Proto`` sets the scheme (``http`` or ``https`` only).
* ``X-Forwarded-Host`` replaces the ``Host`` header.
* ``X-Forwarded-For`` sets the client address: the rightmost entry that is
  not itself a trusted proxy.

With an empty list (the default) the middleware does nothing.
"""

from __future__ import annotations

import ipaddress
import logging
import re

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

# A host with an optional port: letters, digits, dots, hyphens, or a
# bracketed IPv6 literal. Anything else is ignored rather than passed on.
_HOST_RE = re.compile(r"^(\[[0-9a-fA-F:.]+\]|[A-Za-z0-9.-]+)(:\d{1,5})?$")


def parse_trusted_proxies(raw: str) -> tuple[_IPNetwork, ...]:
    """Parse a comma-separated list of IP addresses and CIDR ranges.

    Invalid entries raise ``ValueError``: a typo here must not silently
    widen or drop trust.
    """
    networks: list[_IPNetwork] = []
    for part in raw.split(","):
        entry = part.strip()
        if entry:
            networks.append(ipaddress.ip_network(entry, strict=False))
    return tuple(networks)


def _is_trusted(host: str | None, networks: tuple[_IPNetwork, ...]) -> bool:
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in networks)


def _first(headers: list[tuple[bytes, bytes]], name: bytes) -> str:
    for key, value in headers:
        if key == name:
            return value.decode("latin-1").strip()
    return ""


class TrustedProxyMiddleware:
    """ASGI middleware that applies forwarded headers from trusted proxies."""

    def __init__(self, app: ASGIApp, trusted_proxies: str = "") -> None:
        self.app = app
        self.networks = parse_trusted_proxies(trusted_proxies)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not self.networks:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        if not client or not _is_trusted(client[0], self.networks):
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))

        # A chain of proxies appends; the first value is the one closest to
        # the user for proto and host.
        proto = _first(headers, b"x-forwarded-proto").split(",")[0].strip().lower()
        if proto in ("http", "https"):
            if scope["type"] == "websocket":
                scope["scheme"] = "wss" if proto == "https" else "ws"
            else:
                scope["scheme"] = proto

        host = _first(headers, b"x-forwarded-host").split(",")[0].strip()
        if host and _HOST_RE.match(host):
            headers = [(k, v) for k, v in headers if k != b"host"]
            headers.append((b"host", host.encode("latin-1")))
            scope["headers"] = headers

        forwarded_for = _first(headers, b"x-forwarded-for")
        if forwarded_for:
            # Walk from the right: skip our own proxies, stop at the first
            # address we do not control.
            for candidate in reversed([p.strip() for p in forwarded_for.split(",")]):
                if not candidate:
                    continue
                if _is_trusted(candidate, self.networks):
                    continue
                try:
                    ipaddress.ip_address(candidate)
                except ValueError:
                    break
                scope["client"] = (candidate, 0)
                break

        await self.app(scope, receive, send)
