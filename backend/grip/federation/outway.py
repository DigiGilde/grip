"""Calls to other organisations, always through the own FSC outway.

The application never calls another organisation directly. It sends the
request to its own outway with the grant hash of the contract the call falls
under; the outway obtains the token and sets Fsc-Authorization.
"""

from __future__ import annotations

from typing import Any

import httpx

from grip.core.config import Settings
from grip.federation.models import Peer

GRANT_HASH_HEADER = "Fsc-Grant-Hash"


class OutwayNotConfiguredError(Exception):
    """OUTWAY_URL is not set, so nothing can be sent to another organisation."""


class MissingGrantError(Exception):
    """There is no grant hash for this service in the contract with the peer."""


class OutwayClient:
    """Sends requests for a peer and a service through the outway."""

    def __init__(
        self, settings: Settings, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._client = http_client or httpx.AsyncClient(
            timeout=settings.FEDERATION_HTTP_TIMEOUT_SECONDS
        )
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def request(
        self,
        peer: Peer,
        service: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        base = self._settings.OUTWAY_URL.rstrip("/")
        if not base:
            raise OutwayNotConfiguredError("OUTWAY_URL is not set")
        grant_hash = (peer.grant_hashes or {}).get(service)
        if not grant_hash:
            raise MissingGrantError(
                f"No grant hash for service {service!r} with peer {peer.peer_id}"
            )
        return await self._client.request(
            method,
            f"{base}{path}",
            params=params,
            json=json,
            headers={GRANT_HASH_HEADER: grant_hash, "Accept": "application/json"},
        )
