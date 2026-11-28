"""The peer registry as the FSC bootstrap of the example group fills it.

The bootstrap knows, once a connection contract is valid, which other example
instance is behind it and with which grant hash. It enters that here, through
grip, instead of in the database (ADR 0062). A person keeps managing the
registry under Beheer > Koppelingen; what is that person's to decide stays so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.federation.models import Peer
from grip.services import stale

SOURCE = "fsc-bootstrap"
# What the bootstrap may set on a row that exists. Whether the peer is
# active and whether it may inspect the finances is the beheerder's call.
_UPDATED = ("name", "organisation_tooi_uri", "base_uri", "role")


@dataclass(frozen=True)
class Registered:
    peer: Peer
    created: bool


def _values(peer: Peer) -> dict[str, Any]:
    return {
        "peer_id": peer.peer_id,
        "name": peer.name,
        "organisation_tooi_uri": peer.organisation_tooi_uri,
        "base_uri": peer.base_uri,
        "role": peer.role,
        "grant_hashes": dict(peer.grant_hashes or {}),
        "financial_inspection": bool(peer.financial_inspection),
        "is_example": bool(peer.is_example),
        "is_active": peer.is_active,
    }


async def by_peer_id(db: AsyncSession, peer_id: str) -> Peer | None:
    return await db.scalar(select(Peer).where(Peer.peer_id == peer_id))


async def register(
    db: AsyncSession,
    *,
    peer_id: str,
    name: str,
    organisation_tooi_uri: str,
    base_uri: str,
    role: str,
    grant_hashes: dict[str, str],
    financial_inspection: bool,
    is_example: bool,
) -> Registered:
    """Create the peer, or bring an existing row in line with the contract.

    Idempotent: a call that changes nothing writes nothing.
    """
    peer = await by_peer_id(db, peer_id)
    if peer is None:
        peer = Peer(
            peer_id=peer_id,
            name=name,
            organisation_tooi_uri=organisation_tooi_uri,
            base_uri=base_uri,
            role=role,
            grant_hashes=dict(grant_hashes),
            financial_inspection=financial_inspection,
            is_example=is_example,
            is_active=True,
        )
        db.add(peer)
        await db.flush()
        await db.refresh(peer)
        record_audit(
            db,
            actor=None,
            action=CREATE,
            entity="peer",
            entity_id=peer.id,
            new_value={**_values(peer), "source": SOURCE},
        )
        return Registered(peer, True)

    old = _values(peer)
    wanted = {
        "name": name,
        "organisation_tooi_uri": organisation_tooi_uri,
        "base_uri": base_uri,
        "role": role,
    }
    for field in _UPDATED:
        setattr(peer, field, wanted[field])
    merged = {**(peer.grant_hashes or {}), **grant_hashes}
    if merged != (peer.grant_hashes or {}):
        peer.grant_hashes = merged
    if peer.is_example != is_example:
        peer.is_example = is_example
    new = _values(peer)
    changed = {key for key in new if new[key] != old[key]}
    if changed:
        # A beheerder with an older form of this peer open must not save over it.
        stale.touch(peer)
        await db.flush()
        await db.refresh(peer)
        record_audit(
            db,
            actor=None,
            action=UPDATE,
            entity="peer",
            entity_id=peer.id,
            old_value={key: old[key] for key in changed},
            new_value={**{key: new[key] for key in changed}, "source": SOURCE},
        )
    return Registered(peer, False)
