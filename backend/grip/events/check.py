"""Check the hash chain of the stream and say where it breaks::

    python -m grip.events.check

Exit code 0 when the chain is whole, 1 when it is not.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.events import chain
from grip.models.stream_event import StreamEvent

_BATCH = 1000

_REASONS = {
    "prev_hash": "sluit niet aan op de vorige gebeurtenis "
    "(er is iets verwijderd, tussengevoegd of verplaatst)",
    "hash": "de gebeurtenis zelf is gewijzigd",
    "value": "een waarde past niet meer bij wat is vastgelegd",
    "gap": "er ontbreekt een volgnummer voor deze gebeurtenis",
}


async def _rows(db: AsyncSession, from_seq: int) -> AsyncIterator[dict[str, Any]]:
    table = StreamEvent.__table__
    after = from_seq - 1
    while True:
        rows = (
            (
                await db.execute(
                    select(table)
                    .where(table.c.seq > after)
                    .order_by(table.c.seq)
                    .limit(_BATCH)
                )
            )
            .mappings()
            .all()
        )
        if not rows:
            return
        for row in rows:
            yield dict(row)
        after = rows[-1]["seq"]


async def verify_stream(db: AsyncSession, *, from_seq: int = 1) -> chain.Verdict:
    """Verify the stored stream from ``from_seq`` to its head."""
    table = StreamEvent.__table__
    expected = chain.GENESIS
    if from_seq > 1:
        previous = await db.scalar(
            select(table.c.hash).where(table.c.seq == from_seq - 1)
        )
        if previous is None:
            return chain.Verdict(0, None, None, (chain.Break(from_seq, "gap"),))
        expected = previous
    events = [row async for row in _rows(db, from_seq)]
    verdict = chain.verify(events, expected_prev=expected)
    if from_seq == 1 and events and events[0]["seq"] != 1:
        return chain.Verdict(
            verdict.checked,
            verdict.head_seq,
            verdict.head_hash,
            (chain.Break(events[0]["seq"], "gap"), *verdict.breaks),
        )
    return verdict


def describe(verdict: chain.Verdict) -> list[str]:
    if verdict.intact:
        if verdict.checked == 0:
            return ["De stroom is leeg."]
        return [
            f"De keten klopt: {verdict.checked} gebeurtenissen gecontroleerd.",
            f"Laatste: {verdict.head_seq}, hash {verdict.head_hash}.",
        ]
    lines = [f"De keten is gebroken ({verdict.checked} gebeurtenissen gecontroleerd)."]
    lines += [
        f"  gebeurtenis {found.seq}: {_REASONS.get(found.reason, found.reason)}"
        for found in verdict.breaks
    ]
    return lines


async def _main(argv: list[str]) -> int:
    from grip.core.database import async_session, close_db

    from_seq = int(argv[0]) if argv else 1
    try:
        async with async_session() as db:
            verdict = await verify_stream(db, from_seq=from_seq)
    finally:
        await close_db()
    print("\n".join(describe(verdict)))  # noqa: T201
    return 0 if verdict.intact else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
