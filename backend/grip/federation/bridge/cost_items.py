"""Cost items another organisation keeps (ADR 0052): the bridge.

The domain keeps references and the requests it made; this module carries
them across. Before every round of the outbox it queues each request that
waits and is not queued yet, so a request made before the executor was
connected goes out once it is. It tells the domain what became of a sent
request. And it reads what the executor has, with one call per executor.

What is read is remembered for a few seconds, so the several reads of one
page ask once. It is never a source: after that it is read again.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import get_settings
from grip.federation import terms
from grip.federation.bridge.organisations import organisation_by_id, own_reference
from grip.federation.contract_loader import (
    SERVICE_OPDRACHTVERKEER,
    operation,
    validation_errors,
)
from grip.federation.models import (
    OUTBOX_DEAD,
    OUTBOX_REJECTED,
    OUTBOX_SENT,
    FederationOutbox,
    Peer,
)
from grip.federation.outbox import enqueue
from grip.federation.outway import OutwayClient
from grip.federation.peers import find_peer_for_organisation, normalize_uri
from grip.models.cost import (
    REQUEST_APPLIED,
    REQUEST_REFUSED,
    REQUEST_UNDELIVERED,
    CostItem,
)
from grip.repositories.domain import AssignmentRepository
from grip.services import cost_references
from grip.services.cost_references import FetchedItem, FetchedLine

REQUEST = "requestCostItem"
READ = "getCostItems"
# What the contract allows in one call.
_BATCH = 50
_REMEMBER_SECONDS = 10.0

_OUTCOMES = {
    OUTBOX_SENT: REQUEST_APPLIED,
    OUTBOX_REJECTED: REQUEST_REFUSED,
    OUTBOX_DEAD: REQUEST_UNDELIVERED,
}

# (peer id, reference URI) to when it was read and what the executor had.
_read: dict[tuple[str, str], tuple[float, FetchedItem | None]] = {}


def forget() -> None:
    """Forget what was read. For tests."""
    _read.clear()


def outway_client() -> OutwayClient:
    """The outway of this process. Looked up per call so tests can swap it."""
    from grip.federation.routes import get_outway_client

    return get_outway_client()


async def _executor_peer(db: AsyncSession, organisation_id: UUID) -> Peer | None:
    organisation = await organisation_by_id(db, organisation_id)
    if organisation is None or not organisation.instance_uri:
        return None
    peer = await find_peer_for_organisation(
        db, {"instance_uri": organisation.instance_uri}
    )
    if peer is None or not (peer.grant_hashes or {}).get(SERVICE_OPDRACHTVERKEER):
        return None
    return peer


def _message_id(reference_uri: str, sequence: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{reference_uri}#verzoek#{sequence}")


async def _assignment_uri(db: AsyncSession, executor_id: UUID) -> str | None:
    """The assignment the executor works under, when that is unambiguous."""
    running = await AssignmentRepository(db).running_with_contractor(executor_id)
    return running[0].uri if len(running) == 1 else None


async def _request_message(
    db: AsyncSession, item: CostItem, reference_uri: str, message_id: uuid.UUID
) -> dict[str, Any]:
    assert item.description is not None and item.budgeted_cents is not None
    assert item.executor_organisation_id is not None
    message: dict[str, Any] = {
        "id": str(message_id),
        "reference_uri": reference_uri,
        "sequence": item.request_sequence,
        "organisation": own_reference(),
        "description": item.description,
        "budgeted": {"amount_cents": item.budgeted_cents, "currency": "EUR"},
        "sent_at": datetime.now(UTC).isoformat(),
    }
    if item.request_period is not None:
        message["period"] = item.request_period.isoformat()
    assignment_uri = await _assignment_uri(db, item.executor_organisation_id)
    if assignment_uri:
        message["assignment_uri"] = assignment_uri
    return message


async def queue_requests(db: AsyncSession) -> None:
    """Queue every request that waits and is not in the outbox yet.

    A request to an organisation that is not connected stays waiting. Without
    its own TOOI URI this instance cannot name itself in a message.
    """
    if not get_settings().INSTANCE_TOOI_URI:
        return
    for item in await cost_references.waiting(db):
        assert item.executor_organisation_id is not None
        peer = await _executor_peer(db, item.executor_organisation_id)
        if peer is None:
            continue
        reference_uri = cost_references.reference_uri(item.id)
        message_id = _message_id(reference_uri, item.request_sequence)
        queued = await db.scalar(
            select(FederationOutbox.id).where(
                FederationOutbox.peer_id == peer.id,
                FederationOutbox.message_id == message_id,
            )
        )
        if queued is not None:
            continue
        message = await _request_message(db, item, reference_uri, message_id)
        await enqueue(db, peer, REQUEST, message)


def _own_cost_item_id(reference_uri: str) -> UUID | None:
    prefix = f"{normalize_uri(get_settings().INSTANCE_BASE_URI)}/id/kostenpost/"
    if not reference_uri.startswith(prefix):
        return None
    try:
        return UUID(reference_uri[len(prefix) :])
    except ValueError:
        return None


async def request_answered(db: AsyncSession, row: FederationOutbox) -> None:
    """Tell the domain what became of a request that was sent."""
    outcome = _OUTCOMES.get(row.status)
    message = terms.from_contract(row.payload)
    cost_item_id = _own_cost_item_id(message.get("reference_uri", ""))
    if outcome is None or cost_item_id is None:
        return
    await cost_references.answered(db, cost_item_id, message["sequence"], outcome)


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _fetched(entry: dict[str, Any]) -> FetchedItem | None:
    if not entry.get("created"):
        return None
    return FetchedItem(
        description=entry["description"],
        budgeted_cents=entry["budgeted"]["amount_cents"],
        lines=tuple(
            FetchedLine(
                kind=line["kind"],
                amount_cents=line["amount"]["amount_cents"],
                reference=line.get("reference"),
                description=line.get("description"),
                period=_date(line.get("period")),
            )
            for line in entry.get("lines") or ()
        ),
    )


async def _ask(peer: Peer, uris: list[str]) -> dict[str, FetchedItem | None] | None:
    """One call to the executor. None when it gives no usable answer."""
    try:
        response = await outway_client().request(
            peer,
            SERVICE_OPDRACHTVERKEER,
            "GET",
            operation(READ).url_path(),
            params={terms.contract_parameter("referenceUri"): uris},
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    if validation_errors(terms.schema("cost-items"), body):
        return None
    entries = terms.from_contract(body)["cost_items"]
    by_uri = {entry["reference_uri"]: _fetched(entry) for entry in entries}
    return {uri: by_uri.get(uri) for uri in uris}


async def read_items(
    db: AsyncSession, executor_id: UUID, cost_item_ids: list[UUID]
) -> dict[UUID, FetchedItem | None] | None:
    """What the executor has behind these references, by cost item id here.

    None when the executor cannot be read: no connection, no answer, or an
    answer outside the contract.
    """
    peer = await _executor_peer(db, executor_id)
    if peer is None:
        return None
    uris = {cost_references.reference_uri(i): i for i in cost_item_ids}
    now = time.monotonic()
    for key in [k for k, (at, _) in _read.items() if now - at >= _REMEMBER_SECONDS]:
        del _read[key]
    found: dict[UUID, FetchedItem | None] = {}
    wanted: list[str] = []
    for uri, cost_item_id in uris.items():
        remembered = _read.get((peer.peer_id, uri))
        if remembered is not None and now - remembered[0] < _REMEMBER_SECONDS:
            found[cost_item_id] = remembered[1]
        else:
            wanted.append(uri)
    for start in range(0, len(wanted), _BATCH):
        part = wanted[start : start + _BATCH]
        answer = await _ask(peer, part)
        if answer is None:
            return None
        for uri, content in answer.items():
            _read[(peer.peer_id, uri)] = (now, content)
            found[uris[uri]] = content
    return found


__all__ = [
    "forget",
    "outway_client",
    "queue_requests",
    "read_items",
    "request_answered",
]
