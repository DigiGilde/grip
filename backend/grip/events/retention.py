"""Retention and erasure on an append-only stream.

An event is never removed and its fixed facts never change: that would
break the chain. What can go are its values (old, new, payload, note),
together with the salt of their digests. The digests stay, so the chain
still verifies, and without the salt a digest of a small value cannot be
guessed back. Every erasure is itself an event in the stream, so values
that vanish without one are a sign of tampering.

Erasing by age never reaches an event of an assignment: those go with
their case (ADR 0057). The worker runs retention once a day
(grip.services.retention); by hand::

    python -m grip.events.retention
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, null, select, update
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle import rates
from grip.chronicle.writer import event_type
from grip.events import context, stream
from grip.models.stream_event import CASE_ASSIGNMENT, StreamEvent
from grip.services import instance_settings, quote_approval
from grip.services.errors import DomainValidationError

READ_TYPE = "data.read"
ERASED_TYPE = "stream.erased"


# A hundred years; much more and now - timedelta(days) leaves the calendar.
MAX_DAYS = 36500


def _days(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_DAYS
    ):
        raise DomainValidationError(
            "Een bewaartermijn is een geheel aantal dagen, "
            f"van 0 tot en met {MAX_DAYS}."
        )
    return value


# Zero keeps values for as long as the instance exists.
RETENTION_DAYS = instance_settings.declare(
    "events.retention_days",
    0,
    _days,
    "Na hoeveel dagen de waarden uit de geschiedenis worden gewist, buiten een "
    "opdracht (0 is nooit)",
)
READ_RETENTION_DAYS = instance_settings.declare(
    "events.read_retention_days",
    0,
    _days,
    "Na hoeveel dagen wie-wat-inzag wordt gewist (0 is nooit)",
)


async def _erase(
    db: AsyncSession, condition: Any, *, reason: str, about: dict[str, Any]
) -> int:
    """Erase the values of the events that match; returns how many."""
    await db.flush()
    seqs = list(
        await db.scalars(
            select(StreamEvent.seq)
            .where(condition, StreamEvent.erased_at.is_(None))
            .order_by(StreamEvent.seq)
        )
    )
    if not seqs:
        return 0
    await db.execute(
        update(StreamEvent)
        .where(StreamEvent.seq.in_(seqs))
        .values(
            # SQL NULL, not the JSON value null.
            old_value=null(),
            new_value=null(),
            payload=null(),
            note=None,
            salt=None,
            erased_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )
    stream.append(
        db,
        ERASED_TYPE,
        subject=("stream", "values"),
        new={
            "reason": reason,
            "count": len(seqs),
            "first_seq": seqs[0],
            "last_seq": seqs[-1],
            **about,
        },
    )
    await db.flush()
    return len(seqs)


async def erase_events(
    db: AsyncSession,
    seqs: Iterable[int],
    *,
    reason: str,
    about: dict[str, Any] | None = None,
) -> int:
    """Erase the values of these events; returns how many still had them."""
    wanted = sorted(set(seqs))
    if not wanted:
        return 0
    return await _erase(
        db, StreamEvent.seq.in_(wanted), reason=reason, about=about or {}
    )


async def erase_person(db: AsyncSession, person_id: UUID, *, reason: str) -> int:
    """Erase the values of every event about this person's data."""
    return await _erase(
        db,
        # The record of an erasure holds no values of the person.
        (StreamEvent.person_id == person_id) & (StreamEvent.type != ERASED_TYPE),
        reason=reason,
        about={"person_id": str(person_id)},
    )


def _needed_to_look_back() -> Any:
    """What every later stand prices and weighs with. Holds no personal data."""
    approval_rule = array([quote_approval.MODE.key, quote_approval.THRESHOLD.key])
    return (StreamEvent.type == event_type(rates.FACT)) | (
        (StreamEvent.subject_kind == "instance_setting")
        # A row migrated without new values gives NULL, which no NOT makes true.
        & StreamEvent.new_value.has_any(approval_rule).is_(True)
    )


async def apply_retention(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Erase the values that are older than the instance keeps them."""
    now = now or datetime.now(UTC)
    erased = 0
    days = await instance_settings.get(db, RETENTION_DAYS.key)
    if days:
        erased += await _erase(
            db,
            (StreamEvent.occurred_at < now - timedelta(days=days))
            & (StreamEvent.type != ERASED_TYPE)
            & StreamEvent.case_kind.is_distinct_from(CASE_ASSIGNMENT)
            & ~_needed_to_look_back(),
            reason="retention",
            about={"retention_days": days},
        )
    read_days = await instance_settings.get(db, READ_RETENTION_DAYS.key)
    if read_days:
        erased += await _erase(
            db,
            (StreamEvent.occurred_at < now - timedelta(days=read_days))
            & (StreamEvent.type == READ_TYPE),
            reason="read_retention",
            about={"retention_days": read_days},
        )
    return erased


async def _main() -> None:
    from grip.core.database import async_session, close_db

    try:
        with context.scope(job="events.retention"):
            async with async_session() as db:
                erased = await apply_retention(db)
                await db.commit()
        print(f"{erased} gebeurtenissen gewist")  # noqa: T201
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(_main())
