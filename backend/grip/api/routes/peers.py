"""Peer management, for the beheerder of an instance.

A peer is another grip instance or a corpus system, known by its FSC peer
id. Without a row here nothing is accepted from it and nothing is sent to
it. The grant hash per service comes from the FSC contract with the peer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from grip.access import Action, Resource
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.federation.contract_loader import (
    SERVICE_CORPUS_CONTEXT,
    SERVICE_OPDRACHTVERKEER,
    operation,
    validation_errors,
)
from grip.federation.models import Peer
from grip.federation.outway import (
    MissingGrantError,
    OutwayClient,
    OutwayNotConfiguredError,
)
from grip.federation.routes import get_outway_client
from grip.schema.peers import (
    ConnectionTestOut,
    PeerIn,
    PeerListOut,
    PeerOut,
    PeerUpdate,
)
from grip.services.errors import DomainValidationError, NotFoundError

router = APIRouter(prefix="/peers", tags=["peers"])

SERVICES = [SERVICE_OPDRACHTVERKEER, SERVICE_CORPUS_CONTEXT]
_AUDITED = (
    "peer_id",
    "name",
    "organisation_tooi_uri",
    "base_uri",
    "role",
    "grant_hashes",
    "financial_inspection",
    "is_active",
)


async def _require_beheerder(access: RequestAccess) -> None:
    # Who this instance trusts is part of managing who has access to it.
    await access.require(Action.MANAGE_USERS, Resource.instance())


def _out(peer: Peer) -> dict[str, Any]:
    return {
        "id": peer.id,
        "peer_id": peer.peer_id,
        "name": peer.name,
        "organisation_tooi_uri": peer.organisation_tooi_uri or "",
        "base_uri": peer.base_uri,
        "role": peer.role,
        "grant_hashes": dict(peer.grant_hashes or {}),
        "financial_inspection": bool(peer.financial_inspection),
        "is_active": peer.is_active,
        "key_count": len((peer.jwks or {}).get("keys", [])),
        "jwks_fetched_at": peer.jwks_fetched_at,
        "created_at": peer.created_at,
        "updated_at": peer.updated_at,
    }


def _audit_values(peer: Peer) -> dict[str, Any]:
    return {name: getattr(peer, name) for name in _AUDITED}


async def _get(db: DbSession, peer_row_id: UUID) -> Peer:
    peer = await db.get(Peer, peer_row_id)
    if peer is None:
        raise NotFoundError("Peer", peer_row_id)
    return peer


@router.get("", response_model=PeerListOut)
async def list_peers(
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    await _require_beheerder(access)
    peers = (await db.execute(select(Peer).order_by(Peer.name))).scalars().all()
    return {
        "items": [_out(peer) for peer in peers],
        "services": SERVICES,
        "outway_configured": bool(settings.OUTWAY_URL),
    }


@router.post("", response_model=PeerOut, status_code=status.HTTP_201_CREATED)
async def create_peer(
    body: PeerIn, access: RequestAccess, db: DbSession, person: CurrentPerson
) -> dict[str, Any]:
    await _require_beheerder(access)
    existing = await db.scalar(select(Peer.id).where(Peer.peer_id == body.peer_id))
    if existing is not None:
        raise DomainValidationError("Er bestaat al een peer met dit peer-id.")
    peer = Peer(**body.model_dump())
    db.add(peer)
    await db.flush()
    await db.refresh(peer)
    record_audit(
        db,
        actor=person,
        action=CREATE,
        entity="peer",
        entity_id=peer.id,
        new_value=_audit_values(peer),
    )
    return _out(peer)


@router.get("/{peer_row_id}", response_model=PeerOut)
async def get_peer(
    peer_row_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    await _require_beheerder(access)
    return _out(await _get(db, peer_row_id))


@router.patch("/{peer_row_id}", response_model=PeerOut)
async def update_peer(
    peer_row_id: UUID,
    body: PeerUpdate,
    access: RequestAccess,
    db: DbSession,
    person: CurrentPerson,
) -> dict[str, Any]:
    """Change a peer. Deactivating is a change of ``is_active``: the row
    stays, because messages refer to it."""
    await _require_beheerder(access)
    peer = await _get(db, peer_row_id)
    old = _audit_values(peer)
    for name, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(peer, name, value)
    await db.flush()
    await db.refresh(peer)
    new = _audit_values(peer)
    changed = {name for name in _AUDITED if old[name] != new[name]}
    if changed:
        record_audit(
            db,
            actor=person,
            action=UPDATE,
            entity="peer",
            entity_id=peer.id,
            old_value={name: old[name] for name in changed},
            new_value={name: new[name] for name in changed},
        )
    return _out(peer)


@router.post("/{peer_row_id}/test-connection", response_model=ConnectionTestOut)
async def test_connection(
    peer_row_id: UUID,
    access: RequestAccess,
    db: DbSession,
    outway: OutwayClient = Depends(get_outway_client),
) -> dict[str, Any]:
    """Ask the peer for its public keys, through the outway.

    That exercises the whole path: the outway, the grant hash, the inway of
    the peer and its listener. The keys are kept when the call succeeds.
    """
    await _require_beheerder(access)
    peer = await _get(db, peer_row_id)

    def result(
        ok: bool, detail: str, status_code: int | None = None, keys: int = 0
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "detail": detail,
            "status_code": status_code,
            "key_count": keys,
        }

    if peer.role == "corpus":
        service, path, schema = (
            SERVICE_CORPUS_CONTEXT,
            operation("getCorpus", SERVICE_CORPUS_CONTEXT).url_path(),
            None,
        )
    else:
        service, path, schema = (
            SERVICE_OPDRACHTVERKEER,
            operation("getJwks").url_path(),
            "jwks",
        )
    try:
        response = await outway.request(peer, service, "GET", path)
    except OutwayNotConfiguredError:
        return result(False, "Er is geen outway ingesteld (OUTWAY_URL).")
    except MissingGrantError:
        return result(
            False, f"Er is geen grant hash vastgelegd voor de dienst {service}."
        )
    except httpx.HTTPError as exc:
        return result(False, f"De outway is niet bereikbaar ({type(exc).__name__}).")
    if response.status_code != 200:
        return result(
            False,
            f"De peer antwoordde met status {response.status_code}.",
            response.status_code,
        )
    if schema is None:
        return result(True, "Het corpus-systeem is bereikbaar.", 200)
    try:
        jwks = response.json()
    except ValueError:
        return result(False, "Het antwoord van de peer is geen JSON.", 200)
    if validation_errors(schema, jwks):
        return result(False, "De peer gaf geen geldige sleutelset terug.", 200)
    peer.jwks = jwks
    peer.jwks_fetched_at = datetime.now(UTC)
    await db.flush()
    keys = len(jwks.get("keys", []))
    return result(True, f"Verbinding in orde; {keys} sleutel(s) ontvangen.", 200, keys)
