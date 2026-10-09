"""Refusing a save on top of someone else's change.

A form that edits a stored record reads the record's ``version`` and sends
it back with the save, as ``If-Match: "<id>:<version>"``. The service that
loads the record calls ``check`` before changing it. When the record moved
on in between, the save is refused with who changed it and when, and the
form shows both sets of values and lets the person choose. Nothing is
overwritten unseen and nothing typed is lost.

A request without the header is not checked: scripts and older screens keep
working, they just do not get the protection.

Models take part by mixing in ``grip.models._columns.Versioned``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.models.person import Person
from grip.models.stream_event import StreamEvent
from grip.services.errors import DomainError

HEADER = "if-match"

_expected: ContextVar[tuple[str, int] | None] = ContextVar(
    "expected_version", default=None
)


class StaleWriteError(DomainError):
    """The record changed after the person opened it."""

    http_status = 409

    def __init__(self, what: str, by: str | None, at: datetime | None) -> None:
        who = by or "Een collega"
        when = ""
        if at is not None:
            local = at.astimezone(clock.zone())
            when = f" op {local.strftime('%d-%m-%Y')} om {local.strftime('%H:%M')}"
        super().__init__(
            f"{who} heeft {what} intussen gewijzigd{when}. Er is niets overschreven."
        )
        self.changed_by = by
        self.changed_at = at
        # Extra members of the problem document, for the form.
        self.problem_extra = {
            "changed_by": by,
            "changed_at": at.isoformat() if at is not None else None,
        }


def parse(raw: str | None) -> tuple[str, int] | None:
    """``"<id>:<version>"`` as a pair, or None for anything else."""
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("W/"):
        value = value[2:]
    value = value.strip('"')
    record, _, number = value.rpartition(":")
    if not record or not number.isdigit():
        return None
    return record, int(number)


@contextmanager
def expecting(raw: str | None) -> Iterator[None]:
    """What the request says it started from, for the length of the request."""
    token = _expected.set(parse(raw))
    try:
        yield
    finally:
        _expected.reset(token)


async def last_change(
    session: AsyncSession, record_id: Any
) -> tuple[str | None, datetime | None]:
    """Who last changed a record and when, from the event stream."""
    row = (
        await session.execute(
            select(StreamEvent.occurred_at, Person.name)
            .outerjoin(Person, Person.id == StreamEvent.actor_person_id)
            .where(StreamEvent.subject_id == str(record_id))
            .where(StreamEvent.action.is_not(None))
            .order_by(StreamEvent.seq.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None
    return row[1], row[0]


async def check(
    session: AsyncSession, row: Any, what: str, *, trail: Any = None
) -> None:
    """Refuse the change when the request started from an older version of
    this record. ``what`` names the record in the sentence: "deze
    begrotingsregel". ``trail`` is the record its changes are written under
    in the event stream, when that is not the record itself."""
    expected = _expected.get()
    if expected is None or expected[0] != str(row.id):
        return
    if expected[1] != row.version:
        by, at = await last_change(session, trail or row.id)
        raise StaleWriteError(what, by, at)
