"""What an inzet would do to the load of a person, before it is saved.

Planning someone above 100 percent is allowed; doing it without knowing is
not. This tells, for the months the inzet covers, where the person would end
up above 100 percent. Nothing is saved by asking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import Month
from grip.models.assignment import Allocation, BudgetLine
from grip.models.person import Person
from grip.services import periods
from grip.services.pricing import DEFAULT_OPTIONS, PricingOptions
from grip.services.reports import steering

FULL = Fraction(100)


@dataclass(frozen=True)
class OverMonth:
    month: Month
    # What the person is planned for now, and with this inzet.
    current_pct: Decimal
    new_pct: Decimal


def _pct(value: Fraction) -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal("0.1")
    )


def period_of(
    line: BudgetLine,
    period_source: str | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[date | None, date | None]:
    """The period the inzet would get: its own, or that of the line."""
    _source, start, end = periods.allocation_period(
        line, period_source, start_date, end_date
    )
    return start, end


async def person_name(session: AsyncSession, person_id: UUID) -> str:
    person = await session.get(Person, person_id)
    return person.name if person is not None else ""


async def over_months(
    session: AsyncSession,
    *,
    person_id: UUID,
    start: date,
    end: date,
    fte_pct: Decimal,
    replaces: Allocation | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[OverMonth]:
    """The months in which the person would be above 100 percent.

    ``replaces`` is the inzet being changed: its share of the current load
    makes room for the new one.
    """
    added = dict(calc.month_fractions(start, end, options.partial_months))
    if not added:
        return []
    months = sorted(added)
    rows = await steering.occupancy(session, months, options=options)
    cells = next((row.cells for row in rows if row.person_id == person_id), ())
    now = {cell.month: cell.exact for cell in cells}
    leaving: dict[Month, Fraction] = {}
    if replaces is not None:
        leaving = {
            month: Fraction(Decimal(replaces.fte_pct)) * fraction
            for month, fraction in calc.month_fractions(
                replaces.start_date, replaces.end_date, options.partial_months
            )
        }
    result = []
    for month in months:
        current = now.get(month, Fraction(0))
        new = (
            current - leaving.get(month, Fraction(0)) + Fraction(fte_pct) * added[month]
        )
        if new > FULL:
            result.append(OverMonth(month, _pct(current), _pct(new)))
    return result
