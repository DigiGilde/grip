"""Messages that do not arrive: what the beheerder sees of them, sending one
again, and what the domain hears (ADR 0061).

A message counts as not arriving from its third failure in a row, or from a
final answer, until it arrives (``FederationOutbox.failing_since``). Per
peer the domain hears how many there are, since when, why and until when
grip keeps trying, through the reporter the bridge registers. Why is a code
from ``FAILURES``: what the receiver answered stays in the outbox.
"""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.federation.models import (
    FAILURE_OTHER,
    OUTBOX_DEAD,
    OUTBOX_PENDING,
    OUTBOX_REJECTED,
    OUTBOX_SENT,
    FederationOutbox,
)
from grip.federation.registry import (
    PeerDeliveries,
    delivery_reporter,
    get_resend_hook,
)
from grip.services.errors import DomainValidationError, NotFoundError

# What a message is, in the words of the beheerder.
KINDS: dict[str, str] = {
    "sendAssignmentRequest": "Aanvraag",
    "sendQuote": "Offerte",
    "sendAcceptance": "Akkoord op een offerte",
    "sendRejection": "Afwijzing van een offerte",
    "sendBillingDetails": "Factuurinformatie",
    "sendFinalReport": "Eindrapport",
    "sendVacancy": "Vacature",
    "sendVacancyOffer": "Aanbod op een vacature",
    "requestCostItem": "Verzoek om een kostenpost",
}

NOT_FINAL = "Grip probeert dit bericht nog te versturen."
ALREADY_SENT = "Dit bericht is al aangekomen."

_FINAL = (OUTBOX_REJECTED, OUTBOX_DEAD)
_NOT_SENT = (OUTBOX_PENDING, *_FINAL)


def kind_words(operation: str) -> str:
    return KINDS.get(operation, "Bericht")


def is_final(row: FederationOutbox) -> bool:
    return row.status in _FINAL


def _not_arriving() -> tuple[ColumnElement[bool], ...]:
    return (
        FederationOutbox.failing_since.is_not(None),
        FederationOutbox.status.in_(_NOT_SENT),
    )


async def of_peer(db: AsyncSession, peer_id: UUID) -> list[FederationOutbox]:
    """The messages to one peer that do not arrive, the longest first."""
    rows = await db.scalars(
        select(FederationOutbox)
        .where(FederationOutbox.peer_id == peer_id, *_not_arriving())
        .order_by(FederationOutbox.failing_since, FederationOutbox.created_at)
    )
    return list(rows)


async def counts(db: AsyncSession) -> dict[UUID, int]:
    """How many messages do not arrive, per peer that has any."""
    rows = await db.execute(
        select(FederationOutbox.peer_id, func.count())
        .where(*_not_arriving())
        .group_by(FederationOutbox.peer_id)
    )
    return {peer_id: count for peer_id, count in rows}


async def resend(db: AsyncSession, peer_id: UUID, row_id: UUID) -> FederationOutbox:
    """Put a final message to this peer back in the queue, as it was.

    The same row, so the receiver sees the same message id: one it refused
    was not stored, and one it stored after all answers as a repeat. The
    window starts again at the next failure; until the message arrives it
    still counts as not arriving.
    """
    row = await db.get(FederationOutbox, row_id)
    if row is None or row.peer_id != peer_id:
        raise NotFoundError("Bericht", row_id)
    if row.status == OUTBOX_SENT:
        raise DomainValidationError(ALREADY_SENT)
    if not is_final(row):
        raise DomainValidationError(NOT_FINAL)
    row.status = OUTBOX_PENDING
    row.attempts = 0
    row.retry_until = None
    row.next_attempt_at = clock.now()
    hook = get_resend_hook(row.operation)
    if hook is not None:
        await hook(db, row)
    await db.flush()
    await report(db, {peer_id})
    return row


async def standings(
    db: AsyncSession, peer_ids: Collection[UUID] | None = None
) -> list[PeerDeliveries]:
    """Per peer what does not arrive; a peer without such messages is absent."""
    query = select(FederationOutbox).where(*_not_arriving())
    if peer_ids is not None:
        query = query.where(FederationOutbox.peer_id.in_(list(peer_ids)))
    by_peer: dict[UUID, list[FederationOutbox]] = {}
    for row in await db.scalars(query):
        by_peer.setdefault(row.peer_id, []).append(row)
    found = []
    for peer_id, rows in by_peer.items():
        # A final message first: that is what needs a hand.
        first = min(rows, key=lambda row: (not is_final(row), row.failing_since))
        tried = [
            row.retry_until
            for row in rows
            if row.status == OUTBOX_PENDING and row.retry_until is not None
        ]
        found.append(
            PeerDeliveries(
                peer_id=peer_id,
                peer_name=rows[0].peer.name,
                since=min(row.failing_since for row in rows if row.failing_since),
                count=len(rows),
                final=any(is_final(row) for row in rows),
                failure=first.failure or FAILURE_OTHER,
                retry_until=min(tried, default=None),
            )
        )
    return sorted(found, key=lambda item: str(item.peer_id))


async def report(db: AsyncSession, peer_ids: Collection[UUID] | None = None) -> None:
    """Tell the domain what does not arrive: at every peer, or at these."""
    reporter = delivery_reporter()
    if reporter is None:
        return
    scope = None if peer_ids is None else set(peer_ids)
    await reporter(db, await standings(db, scope), scope)
