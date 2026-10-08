"""Who is calling: the peer behind a federation request, and peer lookups."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.federation.contract_loader import (
    SERVICE_OPDRACHTVERKEER,
    operation,
    validation_errors,
)
from grip.federation.models import (
    PEER_ROLE_CHILD,
    PEER_ROLE_CORPUS,
    PEER_ROLE_COUNTERPART,
    PEER_ROLE_PARENT,
    Peer,
)
from grip.federation.outway import OutwayClient
from grip.federation.problems import FederationProblem

logger = logging.getLogger(__name__)

# A parent or a child instance can also be the client or the contractor of
# an assignment, so every instance role counts as a counterpart.
_INSTANCE_ROLES = frozenset({PEER_ROLE_COUNTERPART, PEER_ROLE_PARENT, PEER_ROLE_CHILD})

# The relation an operation requires (x-grip-caller) to the peer roles that
# can have it. Whether this peer is the client or contractor of one specific
# assignment is decided by the domain handler or provider.
_ROLES_FOR_CALLER: dict[str, frozenset[str]] = {
    "client": _INSTANCE_ROLES,
    "contractor": _INSTANCE_ROLES,
    "peer": _INSTANCE_ROLES,
    "parent": frozenset({PEER_ROLE_PARENT}),
    "corpus": frozenset({PEER_ROLE_CORPUS}),
}


def normalize_uri(uri: str) -> str:
    return uri.strip().rstrip("/")


async def get_current_peer(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Peer:
    """The active peer the inway says is calling.

    The header is trusted because these routes are only reachable from the
    inway. That is a property of the deployment, not of this code: when the
    listener is exposed in any other way, anyone can set the header.
    """
    if not settings.FEDERATION_INBOUND_ENABLED:
        raise FederationProblem(
            503,
            "Federatie staat uit",
            "Deze instantie neemt geen verkeer van andere organisaties aan.",
        )
    peer_id = request.headers.get(settings.FSC_PEER_ID_HEADER, "").strip()
    if not peer_id:
        raise FederationProblem(
            403,
            "Geen toegang",
            "Het verzoek is niet via de inway binnengekomen.",
        )
    peer = (
        await db.execute(select(Peer).where(Peer.peer_id == peer_id))
    ).scalar_one_or_none()
    if peer is None or not peer.is_active:
        # Same answer for unknown and inactive: do not reveal which peers exist.
        raise FederationProblem(
            403, "Geen toegang", "Deze peer is niet bekend bij deze instantie."
        )
    return peer


CurrentPeer = Annotated[Peer, Depends(get_current_peer)]


def require_caller(operation_id: str) -> Callable[..., Awaitable[Peer]]:
    """Dependency: the peer may have the relation this operation requires.

    The required relation comes from ``x-grip-caller`` in the contract.
    """
    caller = operation(operation_id).caller
    allowed = _ROLES_FOR_CALLER[caller] if caller else _INSTANCE_ROLES

    async def _peer_check(peer: CurrentPeer) -> Peer:
        if peer.role not in allowed:
            raise FederationProblem(
                403,
                "Geen toegang",
                "Deze peer heeft niet de relatie die voor deze operatie nodig is.",
            )
        return peer

    return _peer_check


# --- lookups ---------------------------------------------------------------


async def find_peer_for_organisation(
    db: AsyncSession, organisation: dict[str, Any]
) -> Peer | None:
    """The grip instance behind an organisation reference, if it runs one.

    Matches on the instance URI when the reference carries one. Falls back
    to the TOOI URI only when exactly one instance is registered for that
    organisation; several instances can share one (a ministry and a unit).
    Returns None for a counterpart without grip.
    """
    instance_uri = organisation.get("instance_uri")
    query = select(Peer).where(
        Peer.is_active.is_(True), Peer.role.in_(sorted(_INSTANCE_ROLES))
    )
    if instance_uri:
        rows = (await db.execute(query)).scalars().all()
        wanted = normalize_uri(instance_uri)
        return next((p for p in rows if normalize_uri(p.base_uri) == wanted), None)
    tooi_uri = organisation.get("tooi_uri")
    if not tooi_uri:
        return None
    rows = (
        (await db.execute(query.where(Peer.organisation_tooi_uri == tooi_uri)))
        .scalars()
        .all()
    )
    return rows[0] if len(rows) == 1 else None


async def find_corpus_peer(db: AsyncSession, uri: str) -> Peer | None:
    """The corpus system that minted ``uri``: longest matching base wins."""
    rows = (
        (
            await db.execute(
                select(Peer).where(
                    Peer.is_active.is_(True), Peer.role == PEER_ROLE_CORPUS
                )
            )
        )
        .scalars()
        .all()
    )
    wanted = normalize_uri(uri)
    matches = [
        peer
        for peer in rows
        if wanted == normalize_uri(peer.base_uri)
        or wanted.startswith(normalize_uri(peer.base_uri) + "/")
    ]
    return max(
        matches, key=lambda peer: len(normalize_uri(peer.base_uri)), default=None
    )


# --- keys of a peer --------------------------------------------------------


class PeerKeysUnavailableError(Exception):
    """The public keys of a peer could not be obtained."""


async def get_peer_jwks(
    db: AsyncSession,
    peer: Peer,
    outway: OutwayClient,
    settings: Settings,
    *,
    kid: str | None = None,
) -> dict[str, Any]:
    """The JWKS of a peer, from cache or fetched through the outway.

    Fetches when nothing is cached, when the cache is older than the TTL, or
    when ``kid`` is not among the cached keys (the peer rotated its key).
    Keys that were entered by hand and never fetched are kept as they are
    when the peer cannot be reached.
    """
    cached = peer.jwks
    fresh = (
        cached is not None
        and peer.jwks_fetched_at is not None
        and datetime.now(UTC) - peer.jwks_fetched_at
        < timedelta(seconds=settings.FEDERATION_JWKS_TTL_SECONDS)
    )
    has_kid = kid is None or any(
        key.get("kid") == kid for key in (cached or {}).get("keys", [])
    )
    if cached is not None and has_kid and (fresh or peer.jwks_fetched_at is None):
        return cached

    try:
        response = await outway.request(
            peer,
            SERVICE_OPDRACHTVERKEER,
            "GET",
            operation("getJwks").url_path(),
        )
        response.raise_for_status()
        jwks = response.json()
    except Exception as exc:
        if cached is not None and has_kid:
            logger.warning("JWKS of peer %s not refreshed: %s", peer.peer_id, exc)
            return cached
        raise PeerKeysUnavailableError(str(exc)) from exc
    if validation_errors("jwks", jwks):
        raise PeerKeysUnavailableError("The peer returned a JWKS that is not valid")
    peer.jwks = jwks
    peer.jwks_fetched_at = datetime.now(UTC)
    await db.flush()
    return jwks
