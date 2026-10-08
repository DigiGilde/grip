"""Whose period a budget line and an allocation have.

Most of the time the lines of a budget run as long as the assignment, and
the inzet on a line as long as the line. So that is the default: a budget
line follows the assignment unless it is given a period of its own, and an
allocation follows its line unless it is given one.

The source is stored (``period_source``). The two dates of a line or an
allocation always hold the period in force, so everything that needs a
period (pricing, the timeline, a quote, a vacancy, the Wies export) reads
the dates and need not know where they come from. This module is the one
place that keeps the dates of followers in step:

- when a line is created or changed (``line_period``),
- when an allocation is created or changed (``allocation_period``),
- when the period of a line changes (``follow_line``),
- when the period of an assignment changes (``follow_assignment``).

An assignment without a complete period leaves its following lines without
dates. Such a line cannot be priced and cannot carry inzet yet; setting the
period of the assignment is the one action that gives every following line
its dates.

Nothing moves inside a closed month: a change that would make inzet enter or
leave a closed month is refused as a whole, with the line and the month
named. A quote that was issued keeps the period it was issued with: its
content is frozen at issue and never resolved again.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.repositories.domain import MonthCloseRepository
from grip.services.errors import DomainValidationError, MonthClosedError
from grip.services.guards import ensure_years_open, years_between

FOLLOWS_ASSIGNMENT = "assignment"
FOLLOWS_LINE = "line"
OWN = "own"

Period = tuple[date | None, date | None]


class PeriodChangeBlockedError(MonthClosedError):
    """A change of period would move inzet into or out of a closed month."""

    def __init__(self, month: str, line_description: str) -> None:
        super().__init__(month)
        self.args = (
            f"De periode kan niet zo wijzigen: de inzet op '{line_description}' zou "
            f"dan in de afgesloten maand {month} beginnen of eruit verdwijnen. Wat "
            "in een afgesloten maand is vastgesteld blijft staan. Heropen de "
            "maand, of geef die inzet een eigen periode.",
        )
        self.line_description = line_description


def assignment_period(assignment: Assignment) -> Period:
    """The period lines can follow: both dates, or nothing."""
    if assignment.start_date is None or assignment.end_date is None:
        return (None, None)
    return (assignment.start_date, assignment.end_date)


def line_period(
    assignment: Assignment,
    source: str | None,
    start: date | None,
    end: date | None,
) -> tuple[str, date | None, date | None]:
    """The source and dates of a personnel line, from what was sent.

    Without a source: no dates means the line follows the assignment, and so
    do dates equal to the assignment's; other dates are a period of its own.
    """
    follows = assignment_period(assignment)
    if source is None:
        if start is None and end is None:
            source = FOLLOWS_ASSIGNMENT
        elif follows != (None, None) and (start, end) == follows:
            source = FOLLOWS_ASSIGNMENT
        else:
            source = OWN
    if source == FOLLOWS_ASSIGNMENT:
        return (FOLLOWS_ASSIGNMENT, *follows)
    if source != OWN:
        raise DomainValidationError(f"Onbekende bron voor de periode: {source}")
    if start is None or end is None:
        raise DomainValidationError(
            "Een regel met een eigen periode heeft een begin- en een einddatum nodig."
        )
    if end < start:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    return (OWN, start, end)


def allocation_period(
    line: BudgetLine,
    source: str | None,
    start: date | None,
    end: date | None,
) -> tuple[str, date, date]:
    """The source and dates of an allocation, from what was sent."""
    if source is None:
        if start is None and end is None:
            source = FOLLOWS_LINE
        elif (start, end) == (line.start_date, line.end_date):
            source = FOLLOWS_LINE
        else:
            source = OWN
    if source == FOLLOWS_LINE:
        if line.start_date is None or line.end_date is None:
            raise DomainValidationError(
                "Deze begrotingsregel heeft nog geen periode. Vul eerst de periode "
                "van de opdracht in, of geef de inzet een eigen periode."
            )
        return (FOLLOWS_LINE, line.start_date, line.end_date)
    if source != OWN:
        raise DomainValidationError(f"Onbekende bron voor de periode: {source}")
    if start is None or end is None:
        raise DomainValidationError(
            "Inzet met een eigen periode heeft een begin- en een einddatum nodig."
        )
    return (OWN, start, end)


def _covers(period: tuple[date, date], month: date) -> bool:
    m = Month.of(month)
    return period[0] <= m.last_day and period[1] >= m.first_day


async def follow_line(
    session: AsyncSession,
    line: BudgetLine,
    *,
    allow_closed_year: bool = False,
    closed_months: list[date] | None = None,
) -> list[UUID]:
    """Give the allocations that follow a line the period the line now has.

    Returns the ids of the allocations that moved. Refuses, changing nothing,
    when one of them would enter or leave a closed month.
    """
    result = await session.execute(
        select(Allocation).where(
            Allocation.budget_line_id == line.id,
            Allocation.period_source == FOLLOWS_LINE,
        )
    )
    followers = [
        a
        for a in result.scalars()
        if (a.start_date, a.end_date) != (line.start_date, line.end_date)
    ]
    if not followers:
        return []
    if line.start_date is None or line.end_date is None:
        raise DomainValidationError(
            f"Op '{line.description}' staat inzet die de regel volgt. De periode "
            "kan daarom niet leeg worden."
        )
    new = (line.start_date, line.end_date)
    if closed_months is None:
        closed_months = await MonthCloseRepository(session).closed_months(
            line.assignment_id
        )
    years: set[int] = years_between(*new)
    for allocation in followers:
        old = (allocation.start_date, allocation.end_date)
        years |= years_between(*old)
        for month in closed_months:
            if _covers(old, month) != _covers(new, month):
                raise PeriodChangeBlockedError(str(Month.of(month)), line.description)
    await ensure_years_open(session, years, allow_closed_year=allow_closed_year)
    for allocation in followers:
        allocation.start_date, allocation.end_date = new
    await session.flush()
    return [a.id for a in followers]


async def follow_assignment(
    session: AsyncSession,
    assignment: Assignment,
    *,
    allow_closed_year: bool = False,
) -> dict[str, Any]:
    """Give the lines that follow an assignment the period it now has.

    The inzet that follows those lines moves along. Returns what moved, for
    the one audit row at the assignment. Refuses as a whole when anything
    would change inside a closed month or a closed year.
    """
    new = assignment_period(assignment)
    result = await session.execute(
        select(BudgetLine)
        .where(
            BudgetLine.assignment_id == assignment.id,
            BudgetLine.kind == "personnel",
            BudgetLine.period_source == FOLLOWS_ASSIGNMENT,
        )
        .order_by(BudgetLine.position)
    )
    lines = [
        line for line in result.scalars() if (line.start_date, line.end_date) != new
    ]
    if not lines:
        return {}
    closed_months = await MonthCloseRepository(session).closed_months(assignment.id)
    years: set[int] = set()
    for line in lines:
        years |= years_between(line.start_date, line.end_date) | years_between(*new)
    await ensure_years_open(session, years, allow_closed_year=allow_closed_year)
    moved_allocations: list[UUID] = []
    for line in lines:
        line.start_date, line.end_date = new
    await session.flush()
    for line in lines:
        moved_allocations += await follow_line(
            session,
            line,
            allow_closed_year=allow_closed_year,
            closed_months=closed_months,
        )
    return {
        "moved_budget_lines": [str(line.id) for line in lines],
        "moved_allocations": [str(a) for a in moved_allocations],
    }


async def lines_without_period(
    session: AsyncSession, assignment_id: UUID
) -> list[BudgetLine]:
    """Personnel lines that wait for the assignment to get a period."""
    result = await session.execute(
        select(BudgetLine).where(
            BudgetLine.assignment_id == assignment_id,
            BudgetLine.kind == "personnel",
            BudgetLine.start_date.is_(None),
        )
    )
    return list(result.scalars())


NO_PERIOD_MESSAGE = "Nog geen periode: vul de periode van de opdracht in."
