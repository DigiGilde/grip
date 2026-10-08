"""The one clock of the instance: what moment it is and what day it is.

Two things, never mixed:

- An *instant* (something happened at this moment) is stored in UTC.
- A *date* of the domain (a right holds from this day, a rate card ends on
  that day, a month is over, a link expires, a task is due) is a day on the
  calendar of the organisation, so it is the date in the instance's time zone.

Every "today" and every day taken from an instant comes from here. Before
this module some code asked the process for its local day and other code took
the day in UTC; between midnight and the offset of the zone those two differ,
and a right granted "today" did not count yet. Tests set the moment with
``at``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

_frozen: datetime | None = None


def zone() -> ZoneInfo:
    """The time zone whose calendar the instance's dates are on."""
    from grip.core.config import get_settings

    return ZoneInfo(get_settings().INSTANCE_TIMEZONE)


def now() -> datetime:
    """This moment, as an instant in UTC."""
    return _frozen if _frozen is not None else datetime.now(UTC)


def today() -> date:
    """Today on the calendar of the instance."""
    return local_date(now())


def local_date(moment: datetime) -> date:
    """The day on the instance's calendar on which an instant fell.

    An instant without a zone is read as UTC, which is how they are stored.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(zone()).date()


@contextmanager
def at(moment: datetime) -> Iterator[None]:
    """Hold the clock at a moment, for a test."""
    global _frozen
    if moment.tzinfo is None:
        raise ValueError("Give the moment with its time zone.")
    previous, _frozen = _frozen, moment.astimezone(UTC)
    try:
        yield
    finally:
        _frozen = previous
