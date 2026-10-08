"""Guards shared by the services: closed years, closed months, audit values."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.repositories.domain import MonthCloseRepository, RateRepository
from grip.services.errors import ClosedYearError, MonthClosedError

Span = tuple[date, date]


def years_between(start: date | None, end: date | None) -> set[Any]:
    """The period between two dates, as what ``ensure_years_open`` checks.

    The name dates from when a rate card was a calendar year and a period
    was checked per year. It now returns the period itself.
    """
    if start is None and end is None:
        return set()
    first = start or end
    last = end or start
    assert first is not None and last is not None
    return {(first, last)}


async def ensure_years_open(
    session: AsyncSession, years: Iterable[Any], *, allow_closed_year: bool
) -> list[str]:
    """Refuse a change in a period priced by a closed rate card, unless the
    caller allows it.

    ``years`` holds periods (from ``years_between``) and, for a fixed budget
    line or an older caller, bare years. Returns the names of the closed
    cards the change touches, so the caller can put them in the audit row.
    Only a caller that has checked the function beheerder may pass
    ``allow_closed_year=True``.
    """
    spans = [
        (date(item, 1, 1), date(item, 12, 31)) if isinstance(item, int) else item
        for item in years
    ]
    closed = await RateRepository(session).closed_touching(spans)
    if closed and not allow_closed_year:
        raise ClosedYearError(closed[0].valid_from.year, closed[0].name)
    return [card.name for card in closed]


def _covers(period: tuple[date, date] | None, month: date) -> bool:
    if period is None:
        return False
    m = Month.of(month)
    return period[0] <= m.last_day and period[1] >= m.first_day


async def ensure_closed_months_unchanged(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    old_period: tuple[date, date] | None,
    new_period: tuple[date, date] | None,
) -> None:
    """An allocation may not start or stop covering a closed month.

    The planned percentage may change freely: a closed month counts with its
    established percentage. What may not change is whether the allocation
    runs in a closed month, because the close has a line per allocation.
    """
    for month in await MonthCloseRepository(session).closed_months(assignment_id):
        if _covers(old_period, month) != _covers(new_period, month):
            raise MonthClosedError(str(Month.of(month)))


def audit_value(value: Any) -> Any:
    """Make a value JSON-safe for the audit log."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        # Same text whether the value came from the caller or the database.
        return format(value.normalize(), "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [audit_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): audit_value(v) for k, v in value.items()}
    return value


def audit_fields(obj: Any, fields: Iterable[str]) -> dict[str, Any]:
    return {name: audit_value(getattr(obj, name)) for name in fields}
