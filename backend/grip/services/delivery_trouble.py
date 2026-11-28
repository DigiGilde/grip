"""Messages to another instance that do not arrive: what grip keeps (ADR 0061).

The part of grip that sends messages reports here per peer, after every
round of its outbox and after a message was sent again. This side keeps one
row per peer while messages to it do not arrive, and records every change
as an event, so the tasks look again at once. It knows nothing of how
messages travel: a peer is an id with a name, and why is a code from a
fixed list, with words for the beheerder.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.delivery_trouble import (
    CONFIGURATION,
    CONFLICT,
    GONE,
    INVALID,
    NO_CONNECTION,
    NOT_FOUND,
    OTHER,
    RECEIVER_ERROR,
    TIMEOUT,
    UNKNOWN_SENDER,
    DeliveryTrouble,
)

# Why messages do not arrive, as the end of a sentence for the beheerder.
# Said of one message or of several alike.
REASON_WORDS: dict[str, str] = {
    NO_CONNECTION: "grip kan de ontvanger niet bereiken",
    TIMEOUT: "de ontvanger antwoordt niet op tijd",
    UNKNOWN_SENDER: "de ontvanger kent deze instantie niet",
    NOT_FOUND: "de ontvanger kent niet waar het over gaat",
    RECEIVER_ERROR: "er gaat iets mis bij de ontvanger",
    CONFIGURATION: "een instelling voor het versturen ontbreekt of klopt niet",
    INVALID: "de ontvanger weigert wat grip stuurt, omdat het niet klopt",
    CONFLICT: "wat grip stuurt, botst met wat de ontvanger al heeft",
    GONE: "waar het over gaat, is er bij de ontvanger niet meer",
    OTHER: "de ontvanger geeft een antwoord dat grip niet kent",
}


def reason_words(reason: str | None) -> str:
    return REASON_WORDS.get(reason or OTHER, REASON_WORDS[OTHER])


@dataclass(frozen=True)
class Trouble:
    """What does not arrive at one peer."""

    peer_id: UUID
    peer_name: str
    since: datetime
    message_count: int
    final: bool
    reason: str
    retry_until: datetime | None


_FIELDS = ("peer_name", "since", "message_count", "final", "reason", "retry_until")


def _values(source: Any) -> dict[str, Any]:
    return {name: getattr(source, name) for name in _FIELDS}


async def report(
    db: AsyncSession,
    troubles: Sequence[Trouble],
    *,
    peer_ids: Collection[UUID] | None = None,
) -> None:
    """What does not arrive, per peer, as the sending part sees it now.

    ``peer_ids`` None: the list is complete, and a peer that is not in it
    has no trouble any more. Otherwise only those peers are looked at.
    """
    reported = {trouble.peer_id: trouble for trouble in troubles}
    query = select(DeliveryTrouble)
    if peer_ids is not None:
        query = query.where(
            DeliveryTrouble.peer_id.in_(list(set(peer_ids) | set(reported)))
        )
    kept = {row.peer_id: row for row in await db.scalars(query)}
    for peer_id in sorted(reported, key=str):
        new = _values(reported[peer_id])
        row = kept.get(peer_id)
        if row is None:
            db.add(DeliveryTrouble(peer_id=peer_id, **new))
            await db.flush()
            record_audit(
                db,
                actor=None,
                action=CREATE,
                entity="delivery_trouble",
                entity_id=peer_id,
                new_value=new,
            )
            continue
        old = _values(row)
        changed = [name for name in _FIELDS if old[name] != new[name]]
        if not changed:
            continue
        for name in changed:
            setattr(row, name, new[name])
        await db.flush()
        record_audit(
            db,
            actor=None,
            action=UPDATE,
            entity="delivery_trouble",
            entity_id=peer_id,
            old_value={name: old[name] for name in changed},
            new_value={name: new[name] for name in changed},
        )
    for peer_id in sorted(set(kept) - set(reported), key=str):
        row = kept[peer_id]
        old = _values(row)
        await db.delete(row)
        await db.flush()
        record_audit(
            db,
            actor=None,
            action=DELETE,
            entity="delivery_trouble",
            entity_id=peer_id,
            old_value=old,
        )


__all__ = ["REASON_WORDS", "Trouble", "reason_words", "report"]
