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

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from grip.core import clock
from grip.models.person import Person
from grip.models.stream_event import StreamEvent
from grip.services.errors import DomainError

HEADER = "if-match"

# Short month names, as the screens write a date.
_MONTHS = (
    "jan",
    "feb",
    "mrt",
    "apr",
    "mei",
    "jun",
    "jul",
    "aug",
    "sep",
    "okt",
    "nov",
    "dec",
)

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
            when = (
                f" op {local.day} {_MONTHS[local.month - 1]} {local.year}"
                f" om {local.strftime('%H:%M')}"
            )
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
    session: AsyncSession,
    row: Any,
    what: str,
    *,
    trail: Any = None,
    key: Any = None,
) -> None:
    """Refuse the change when the request started from an older version of
    this record. ``what`` names the record in the sentence: "deze
    begrotingsregel". ``trail`` is the record its changes are written under
    in the event stream, when that is not the record itself. ``key`` is what
    the form calls the record when that is not its ``id`` (a setting is
    known by its key)."""
    expected = _expected.get()
    name = str(key if key is not None else row.id)
    if expected is None or expected[0] != name:
        return
    if expected[1] != row.version:
        by, at = await last_change(session, trail or name)
        raise StaleWriteError(what, by, at)


async def check_value(
    session: AsyncSession, key: str, version: int, what: str, *, trail: Any = None
) -> None:
    """The same refusal for something that is not one row: a set of settings
    counts as one thing with one version."""
    expected = _expected.get()
    if expected is None or expected[0] != key:
        return
    if expected[1] != version:
        by, at = await last_change(session, trail or key)
        raise StaleWriteError(what, by, at)


def touch(row: Any) -> None:
    """A person changed this record: the next save from an older version is
    stale. For a record that counts every update itself (``Versioned``) this
    makes sure the row is written even when the change is in a row beside
    it; for one that counts only people's edits (``EditCounted``) it is the
    count."""
    mapper = sa_inspect(type(row))
    if mapper.version_id_col is not None:
        if "updated_at" in mapper.column_attrs:
            row.updated_at = clock.now()
        else:
            flag_modified(row, mapper.version_id_col.key)
        return
    row.version = (row.version or 1) + 1
