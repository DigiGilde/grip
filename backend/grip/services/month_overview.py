"""Read functions for the monthly close and the billing data screens.

Closing, reopening and exporting go through ``grip.services.month_close``.
This module assembles what a screen shows: the months of an assignment with
their state, one month with the planned and the established inzet per
person, and an export run as a table or as a CSV file.

CSV of an export run
--------------------

The file is UTF-8, comma separated, with a header row and one row per
line of the export. Decimals use a point. The columns are stable; a new
column is only ever added at the end.

====================  ====================================================
Column                Content
====================  ====================================================
export_id             Id of the export run
exported_at           Moment of the export, ISO 8601 in UTC
assignment_uri        URI of the assignment
assignment_name       Name of the assignment
client_name           Name of the client organisation, empty if unknown
month                 Month the amounts are about, ``YYYY-MM``
line_number           1, 2, 3, in the order of the export
description           Role of the budget line; never a person's name
fte_pct               Established FTE percentage of the month
rate_category         Rate category, A to E
monthly_rate          Monthly rate per FTE, in euros
amount                Amount of the line, in euros
currency              ``EUR``
====================  ====================================================
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip import calc
from grip.calc import Month
from grip.core import clock
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.month_close import BillingExport, MonthClose
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.services import month_close
from grip.services.assignments import get_assignment
from grip.services.errors import DomainValidationError, NotFoundError

CSV_COLUMNS = (
    "export_id",
    "exported_at",
    "assignment_uri",
    "assignment_name",
    "client_name",
    "month",
    "line_number",
    "description",
    "fte_pct",
    "rate_category",
    "monthly_rate",
    "amount",
    "currency",
)


def parse_month(text: str) -> Month:
    """``YYYY-MM`` as a month; anything else is a validation error."""
    try:
        year_text, month_text = text.split("-")
        if len(year_text) != 4 or len(month_text) != 2:
            raise ValueError(text)
        return Month(int(year_text), int(month_text))
    except ValueError as exc:
        raise DomainValidationError(
            "Een maand heeft de vorm JJJJ-MM, bijvoorbeeld 2026-03."
        ) from exc


@dataclass(frozen=True)
class MonthState:
    month: Month
    closed: bool
    closed_at: datetime | None
    closed_by_name: str | None
    # How often this month was reopened before.
    reopen_count: int
    # A month that has not ended yet cannot be closed.
    closable: bool


@dataclass(frozen=True)
class MonthLine:
    allocation_id: UUID
    budget_line_id: UUID
    person_id: UUID
    person_name: str
    description: str
    planned_fte_pct: Decimal
    # None while the month is open.
    established_fte_pct: Decimal | None
    category: str
    monthly_rate_cents: int
    planned_amount_cents: int
    established_amount_cents: int | None


@dataclass(frozen=True)
class CloseRecord:
    closed_at: datetime
    closed_by_name: str | None
    reopened_at: datetime | None
    reopened_by_name: str | None
    reopen_reason: str | None


@dataclass(frozen=True)
class MonthDetail:
    assignment_id: UUID
    month: Month
    closed: bool
    closable: bool
    closed_at: datetime | None
    closed_by_name: str | None
    lines: tuple[MonthLine, ...]
    history: tuple[CloseRecord, ...]
    # Set when the amounts cannot be computed (for example no rate card).
    pricing_problem: str | None

    @property
    def planned_total_cents(self) -> int:
        return sum(line.planned_amount_cents for line in self.lines)

    @property
    def established_total_cents(self) -> int | None:
        if not self.closed:
            return None
        return sum(line.established_amount_cents or 0 for line in self.lines)


def _months(start: date, end: date) -> list[Month]:
    months: list[Month] = []
    current, last = Month.of(start), Month.of(end)
    while (current.year, current.month) <= (last.year, last.month):
        months.append(current)
        current = current.next()
    return months


def _closable(month: Month, today: date) -> bool:
    return month.last_day < today


async def _names(session: AsyncSession, person_ids: set[UUID]) -> dict[UUID, str]:
    if not person_ids:
        return {}
    result = await session.execute(
        select(Person.id, Person.name).where(Person.id.in_(person_ids))
    )
    return {row.id: row.name for row in result}


async def _closes(session: AsyncSession, assignment_id: UUID) -> list[MonthClose]:
    result = await session.execute(
        select(MonthClose)
        .where(MonthClose.assignment_id == assignment_id)
        .order_by(MonthClose.month, MonthClose.closed_at)
        .options(selectinload(MonthClose.lines))
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def _period(
    session: AsyncSession, assignment: Assignment
) -> tuple[date, date] | None:
    """The span of months to show: the assignment period, else that of its inzet."""
    row = (
        await session.execute(
            select(func.min(Allocation.start_date), func.max(Allocation.end_date))
            .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
            .where(BudgetLine.assignment_id == assignment.id)
        )
    ).one()
    starts = [d for d in (assignment.start_date, row[0]) if d is not None]
    ends = [d for d in (assignment.end_date, row[1]) if d is not None]
    if not starts or not ends:
        return None
    return min(starts), max(ends)


async def timeline(
    session: AsyncSession, assignment_id: UUID, *, today: date | None = None
) -> list[MonthState]:
    """Every month of the assignment with its state, in order."""
    today = today or clock.today()
    assignment = await get_assignment(session, assignment_id)
    closes = await _closes(session, assignment_id)
    period = await _period(session, assignment)
    months = set(_months(*period)) if period else set()
    months |= {Month.of(close.month) for close in closes}

    in_force = {
        Month.of(close.month): close for close in closes if close.reopened_at is None
    }
    reopened: dict[Month, int] = {}
    for close in closes:
        if close.reopened_at is not None:
            key = Month.of(close.month)
            reopened[key] = reopened.get(key, 0) + 1
    names = await _names(
        session, {c.closed_by_id for c in in_force.values() if c.closed_by_id}
    )
    states = []
    for month in sorted(months, key=lambda m: (m.year, m.month)):
        close = in_force.get(month)
        states.append(
            MonthState(
                month=month,
                closed=close is not None,
                closed_at=close.closed_at if close else None,
                closed_by_name=names.get(close.closed_by_id)
                if close and close.closed_by_id
                else None,
                reopen_count=reopened.get(month, 0),
                closable=close is None and _closable(month, today),
            )
        )
    return states


async def month_detail(
    session: AsyncSession,
    assignment_id: UUID,
    month: Month,
    *,
    today: date | None = None,
) -> MonthDetail:
    """One month: the planned inzet and, once closed, the established inzet."""
    today = today or clock.today()
    await get_assignment(session, assignment_id)
    all_closes = [
        close
        for close in await _closes(session, assignment_id)
        if Month.of(close.month) == month
    ]
    close = next((c for c in all_closes if c.reopened_at is None), None)

    pricing_problem: str | None = None
    planned: tuple[calc.BillingLine, ...] = ()
    established: dict[str, calc.BillingLine] = {}
    try:
        planned = await month_close.proposal(session, assignment_id, month)
        if close is not None:
            data = await month_close.billing_data(session, assignment_id, month)
            established = {line.allocation_id: line for line in data.lines}
    except calc.CalcError as exc:
        from grip.services.quote_views import describe_calc_error

        pricing_problem = describe_calc_error(exc)

    established_pct = (
        {str(line.allocation_id): line.established_fte_pct for line in close.lines}
        if close is not None
        else {}
    )
    allocation_ids = {UUID(line.allocation_id) for line in planned}
    allocations = {
        a.id: a
        for a in (
            await session.execute(
                select(Allocation).where(Allocation.id.in_(allocation_ids))
            )
        ).scalars()
    }
    budget_lines = {
        b.id: b
        for b in (
            await session.execute(
                select(BudgetLine).where(BudgetLine.assignment_id == assignment_id)
            )
        ).scalars()
    }
    person_ids = {a.person_id for a in allocations.values()}
    close_people = {
        pid
        for c in all_closes
        for pid in (c.closed_by_id, c.reopened_by_id)
        if pid is not None
    }
    names = await _names(session, person_ids | close_people)

    lines = []
    for line in planned:
        allocation = allocations[UUID(line.allocation_id)]
        budget_line = budget_lines.get(allocation.budget_line_id)
        done = established.get(line.allocation_id)
        lines.append(
            MonthLine(
                allocation_id=allocation.id,
                budget_line_id=allocation.budget_line_id,
                person_id=allocation.person_id,
                person_name=names.get(allocation.person_id, ""),
                description=(budget_line.role or budget_line.description)
                if budget_line
                else "",
                planned_fte_pct=allocation.fte_pct,
                established_fte_pct=established_pct.get(line.allocation_id),
                category=line.category,
                monthly_rate_cents=line.monthly_rate_cents,
                planned_amount_cents=line.amount_cents,
                established_amount_cents=done.amount_cents if done else None,
            )
        )
    lines.sort(key=lambda entry: (entry.description, entry.person_name))

    history = tuple(
        CloseRecord(
            closed_at=c.closed_at,
            closed_by_name=names.get(c.closed_by_id) if c.closed_by_id else None,
            reopened_at=c.reopened_at,
            reopened_by_name=names.get(c.reopened_by_id) if c.reopened_by_id else None,
            reopen_reason=c.reopen_reason,
        )
        for c in all_closes
    )
    return MonthDetail(
        assignment_id=assignment_id,
        month=month,
        closed=close is not None,
        closable=close is None and _closable(month, today),
        closed_at=close.closed_at if close else None,
        closed_by_name=names.get(close.closed_by_id)
        if close and close.closed_by_id
        else None,
        lines=tuple(lines),
        history=history,
        pricing_problem=pricing_problem,
    )


async def ensure_closable(month: Month, *, today: date | None = None) -> None:
    """A month can be closed once it has ended."""
    today = today or clock.today()
    if not _closable(month, today):
        raise DomainValidationError(
            f"De maand {month} is nog niet voorbij en kan nog niet worden afgesloten."
        )


async def exports_of_assignment(
    session: AsyncSession, assignment_id: UUID
) -> list[tuple[BillingExport, str | None]]:
    """Export runs of an assignment, newest first, with who made them."""
    result = await session.execute(
        select(BillingExport)
        .where(BillingExport.assignment_id == assignment_id)
        .order_by(BillingExport.created_at.desc())
        .options(selectinload(BillingExport.lines))
    )
    exports = list(result.scalars())
    names = await _names(
        session, {e.exported_by_id for e in exports if e.exported_by_id}
    )
    return [
        (e, names.get(e.exported_by_id) if e.exported_by_id else None) for e in exports
    ]


async def get_export(session: AsyncSession, export_id: UUID) -> BillingExport:
    result = await session.execute(
        select(BillingExport)
        .where(BillingExport.id == export_id)
        .options(selectinload(BillingExport.lines))
    )
    export = result.scalar_one_or_none()
    if export is None:
        raise NotFoundError("Export van factuurgegevens", export_id)
    return export


def _euros(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return f"{sign}{whole}.{fraction:02d}"


def _safe_cell(value: str) -> str:
    """Keep a spreadsheet from reading a text cell as a formula."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


async def export_csv(session: AsyncSession, export: BillingExport) -> str:
    """The export run as CSV text. See the module docstring for the columns."""
    assignment = await get_assignment(session, export.assignment_id)
    client_name = ""
    if assignment.client_organisation_id is not None:
        client = await session.get(Organisation, assignment.client_organisation_id)
        client_name = client.name if client is not None else ""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    month = str(Month.of(export.month))
    exported_at = export.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ordered = sorted(export.lines, key=lambda line: (line.description, str(line.id)))
    for number, line in enumerate(ordered, start=1):
        writer.writerow(
            [
                str(export.id),
                exported_at,
                assignment.uri,
                _safe_cell(assignment.name),
                _safe_cell(client_name),
                month,
                number,
                _safe_cell(line.description),
                format(Decimal(line.fte_pct).normalize(), "f"),
                line.category,
                _euros(line.monthly_rate_cents),
                _euros(line.amount_cents),
                "EUR",
            ]
        )
    return buffer.getvalue()


__all__ = [
    "CSV_COLUMNS",
    "CloseRecord",
    "MonthDetail",
    "MonthLine",
    "MonthState",
    "ensure_closable",
    "export_csv",
    "exports_of_assignment",
    "get_export",
    "month_detail",
    "parse_month",
    "timeline",
]
