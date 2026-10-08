"""Context from a corpus system: a node and its chain, by URI.

An assignment carries only node URIs. A URI is minted by the corpus system
that manages the node, so the URI says which corpus to ask. There can be
several corpus systems (one per ministry, for example); each is a peer with
the role corpus and its corpus base URI.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings
from grip.federation.contract_loader import (
    SERVICE_CORPUS_CONTEXT,
    operation,
    validation_errors,
)
from grip.federation.models import Peer
from grip.federation.outway import (
    MissingGrantError,
    OutwayClient,
    OutwayNotConfiguredError,
)
from grip.federation.peers import find_corpus_peer, normalize_uri

_NODE_SEGMENT = "/id/node/"


class CorpusError(Exception):
    """Base of everything that can go wrong when asking a corpus."""


class UnknownCorpusError(CorpusError):
    """No corpus system is registered for this URI."""


class NodeNotFoundError(CorpusError):
    """The corpus does not know the node, or does not show it to this instance."""


class CorpusUnavailableError(CorpusError):
    """The corpus could not be reached or answered with an error."""


class CorpusContractError(CorpusError):
    """The corpus answered with something the contract does not describe."""


def node_id_from_uri(uri: str) -> str:
    """The id in a node URI of the form ``{corpus}/id/node/{uuid}``."""
    base, separator, node_id = normalize_uri(uri).rpartition(_NODE_SEGMENT)
    if not separator or not base or not node_id or "/" in node_id:
        raise UnknownCorpusError(f"Not a node URI: {uri}")
    return node_id


class CorpusClient:
    """Fetches nodes and chains through the outway, with a short cache."""

    def __init__(self, outway: OutwayClient, settings: Settings) -> None:
        self._outway = outway
        self._ttl = settings.CORPUS_CACHE_TTL_SECONDS
        self._cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    async def get_node(
        self, db: AsyncSession, uri: str, *, peildatum: date | None = None
    ) -> dict[str, Any]:
        """The node behind a URI, with title and status as of ``peildatum``."""
        params = {"peildatum": peildatum.isoformat()} if peildatum else {}
        return await self._get(db, uri, "getNode", "node", params)

    async def get_chain(
        self,
        db: AsyncSession,
        uri: str,
        *,
        peildatum: date | None = None,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        """The chain from a node up to its politieke input.

        The chain stops at a node of another corpus; those URIs are listed
        in ``external_node_uris`` and can be asked for in turn.
        """
        params: dict[str, Any] = {}
        if peildatum:
            params["peildatum"] = peildatum.isoformat()
        if max_depth is not None:
            params["maxDepth"] = max_depth
        return await self._get(db, uri, "getNodeChain", "chain", params)

    async def search_nodes(
        self,
        db: AsyncSession,
        corpus_uri: str,
        *,
        q: str | None = None,
        types: list[str] | None = None,
        peildatum: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Search the nodes of one corpus, for the node picker. Not cached."""
        peer = await self._peer(db, corpus_uri)
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if q:
            params["q"] = q
        if types:
            params["type"] = types
        if peildatum:
            params["peildatum"] = peildatum.isoformat()
        op = operation("searchNodes", SERVICE_CORPUS_CONTEXT)
        return await self._fetch(peer, op.url_path(), params, "node-page", corpus_uri)

    async def _peer(self, db: AsyncSession, uri: str) -> Peer:
        peer = await find_corpus_peer(db, uri)
        if peer is None:
            raise UnknownCorpusError(f"No corpus system is registered for {uri}")
        return peer

    async def _get(
        self,
        db: AsyncSession,
        uri: str,
        operation_id: str,
        schema: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        node_id = node_id_from_uri(uri)
        key = (operation_id, normalize_uri(uri), tuple(sorted(params.items())))
        cached = self._cache.get(key)
        if cached is not None and time.monotonic() - cached[0] < self._ttl:
            return cached[1]
        peer = await self._peer(db, uri)
        op = operation(operation_id, SERVICE_CORPUS_CONTEXT)
        body = await self._fetch(peer, op.url_path(nodeId=node_id), params, schema, uri)
        self._cache[key] = (time.monotonic(), body)
        return body

    async def _fetch(
        self, peer: Peer, path: str, params: dict[str, Any], schema: str, uri: str
    ) -> dict[str, Any]:
        try:
            response = await self._outway.request(
                peer, SERVICE_CORPUS_CONTEXT, "GET", path, params=params
            )
        except (OutwayNotConfiguredError, MissingGrantError) as exc:
            raise CorpusUnavailableError(str(exc)) from exc
        except Exception as exc:
            raise CorpusUnavailableError(f"{type(exc).__name__}: {exc}") from exc
        if response.status_code == 404:
            raise NodeNotFoundError(uri)
        if response.status_code != 200:
            raise CorpusUnavailableError(
                f"The corpus answered {response.status_code} for {uri}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise CorpusContractError("The corpus did not answer with JSON") from exc
        errors = validation_errors(schema, body)
        if errors:
            raise CorpusContractError("; ".join(errors[:5]))
        return body
