"""The rate book as it stood: a chronicle of its own.

Rate cards stay ordinary tables. Each time what prices changes (an active or
closed card, its bands) a fact holds the whole book from then on, so a look
back prices with what was known at that moment. A draft prices nothing and
leaves no fact.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.chronicle.writer import (
    RATE_BOOK,
    SUBJECT_KIND,
    event_type,
    record_without_rows,
)
from grip.models.person import Person
from grip.models.stream_event import StreamEvent

FACT = "rates_established"
# The book before the first fact: every writer of a card records one.
NO_CARDS: Mapping[str, Any] = {"cards": []}


def book_of(cards: Iterable[calc.RateCard]) -> dict[str, Any]:
    """The cards that price, as plain values, in one order."""
    pricing = [card for card in cards if card.status is not calc.RateCardStatus.DRAFT]
    return {
        "cards": [
            {
                "id": card.id,
                "name": card.name,
                "valid_from": card.valid_from.isoformat(),
                "valid_to": card.valid_to.isoformat() if card.valid_to else None,
                "status": card.status.value,
                "rate_bands": sorted(
                    (
                        {
                            "category": band.category,
                            "monthly_rate_cents": band.monthly_rate_cents,
                        }
                        for band in card.rate_bands
                    ),
                    key=lambda item: item["category"],
                ),
                "scale_bands": sorted(
                    (
                        {"scale": band.scale, "category": band.category}
                        for band in card.scale_bands
                    ),
                    key=lambda item: item["scale"],
                ),
            }
            for card in sorted(pricing, key=lambda item: item.valid_from)
        ]
    }


def rate_book_from(book: Mapping[str, Any]) -> calc.RateBook:
    """The rate book back from what a fact holds."""
    return calc.RateBook(
        cards=tuple(
            calc.RateCard(
                id=card["id"],
                name=card["name"],
                valid_from=date.fromisoformat(card["valid_from"]),
                valid_to=date.fromisoformat(card["valid_to"])
                if card["valid_to"]
                else None,
                status=calc.RateCardStatus(card["status"]),
                rate_bands=tuple(
                    calc.RateBand(
                        category=band["category"],
                        monthly_rate_cents=band["monthly_rate_cents"],
                    )
                    for band in card["rate_bands"]
                ),
                scale_bands=tuple(
                    calc.ScaleBand(scale=band["scale"], category=band["category"])
                    for band in card["scale_bands"]
                ),
            )
            for card in book["cards"]
        ),
    )


def _hash(book: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(book, sort_keys=True).encode()).hexdigest()


async def _last_hash(session: AsyncSession) -> str | None:
    value = await session.scalar(
        select(StreamEvent.new_value)
        .where(
            StreamEvent.subject_kind == SUBJECT_KIND,
            StreamEvent.subject_id == RATE_BOOK,
            StreamEvent.type == event_type(FACT),
        )
        .order_by(StreamEvent.seq.desc())
        .limit(1)
    )
    return ((value or {}).get("fields") or {}).get("book_hash")


async def record_rate_book(
    session: AsyncSession,
    *,
    actor: Person | None,
    cause: str,
    effective_on: date | None = None,
) -> bool:
    """Record the book when what prices is no longer what the last fact says.

    ``cause`` says in words what changed. Call it at the end of whatever
    changed a rate card, in its transaction.
    """
    # Imported here: pricing reads the rate tables, and the rate service that
    # calls this function builds on pricing.
    from grip.repositories.domain import RateRepository
    from grip.services.pricing import to_calc_rate_card

    await session.flush()
    cards = await RateRepository(session).all_cards()
    book = book_of(to_calc_rate_card(card) for card in cards)
    digest = _hash(book)
    if digest == (await _last_hash(session) or _hash(NO_CARDS)):
        return False
    record_without_rows(
        session,
        FACT,
        subject_id=RATE_BOOK,
        assignment_id=None,
        fields={"book": book, "book_hash": digest, "cause": cause},
        actor=actor,
        effective_on=effective_on,
    )
    await session.flush()
    return True
