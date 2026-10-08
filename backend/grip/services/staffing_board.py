"""The read model of the planner's board: people over months.

One row per person with what they are allocated per month, every allocation
as a bar with its period and percentage, and the roles nobody fills yet.
Totals per month come from the occupancy read model of the reports, so the
board and the reports always show the same percentage.

Nothing here is money, and nothing here decides who may see what.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.models.person import Person
from grip.repositories.domain import MonthCloseRepository
from grip.services import assignment_views as views
from grip.services.phase import VERBALLY_AGREED
from grip.services.reports import steering
from grip.services.vacancies import service as vacancies

MAX_MONTHS = 24


def window(start: Month, count: int) -> tuple[Month, ...]:
    """``count`` consecutive months from ``start``."""
    months = [start]
    while len(months) < count:
        months.append(months[-1].next())
    return tuple(months)


@dataclass(frozen=True)
class BoardCell:
    month: date
    # False in a month the person could not be deployed.
    available: bool
    pct: Decimal
    tentative_pct: Decimal
    over: bool
    # Everything in this month comes from a closed month.
    established: bool


@dataclass(frozen=True)
class BoardBar:
    allocation_id: UUID
    person_id: UUID
    person_name: str
    assignment_id: UUID
    assignment_name: str
    budget_line_id: UUID
    line_description: str
    role: str | None
    start_date: date
    end_date: date
    fte_pct: Decimal
    # On an assignment that is still potential: it may not happen.
    tentative: bool
    verbally_agreed: bool
    # First days of the months of this allocation that are closed; those
    # months cannot be changed.
    closed_months: tuple[date, ...]
    # R14, with the categories for whoever may see them.
    category_mismatch: bool
    line_category: str | None
    person_category: str | None


@dataclass(frozen=True)
class BoardPerson:
    person_id: UUID
    person_name: str
    manager_id: UUID | None
    manager_name: str | None
    # One cell per month of the window; empty when the person has no row in
    # the occupancy (no billing scale and no inzet in the window).
    cells: tuple[BoardCell, ...]
    # Percentage in the current month; None outside the window.
    now_pct: Decimal | None
    # First month from the current one with less than 100 percent.
    room_from: date | None
    # First month from which the person has no inzet at all in the window.
    idle_from: date | None
    over_months: tuple[date, ...]
    bars: tuple[BoardBar, ...]


@dataclass(frozen=True)
class BoardOpenRole:
    budget_line_id: UUID
    assignment_id: UUID
    assignment_name: str
    description: str
    role: str | None
    fte: Decimal
    unfilled_fte: Decimal
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True)
class Board:
    months: tuple[date, ...]
    current_month: date
    persons: tuple[BoardPerson, ...]
    open_roles: tuple[BoardOpenRole, ...]


def _first(month: Month) -> date:
    return date(month.year, month.month, 1)


def _summary(
    cells: Sequence[BoardCell], current: date
) -> tuple[Decimal | None, date | None, date | None]:
    """Now, the first month with room, and the month the person falls idle."""
    ahead = [cell for cell in cells if cell.month >= current and cell.available]
    now = next((cell.pct for cell in cells if cell.month == current), None)
    room = next((cell.month for cell in ahead if cell.pct < 100), None)
    idle: date | None = None
    for cell in reversed(ahead):
        if cell.pct > 0:
            break
        idle = cell.month
    return now, room, idle


async def board(
    session: AsyncSession,
    start: Month,
    *,
    months: int = 12,
    today: date | None = None,
) -> Board:
    """The board for ``months`` consecutive months from ``start``."""
    span = window(start, max(1, min(months, MAX_MONTHS)))
    first_day, last_day = span[0].first_day, span[-1].last_day
    current = _first(Month.of(today or date.today()))

    occupancy = {row.person_id: row for row in await steering.occupancy(session, span)}
    allocations = [
        view
        for view in await views.allocation_views(session)
        if view.allocation.start_date <= last_day
        and view.allocation.end_date >= first_day
    ]
    statuses = await views.assignment_statuses(
        session, {view.assignment_id for view in allocations}
    )
    # Inzet on an assignment that was rejected or cancelled will not happen.
    allocations = [
        view
        for view in allocations
        if statuses.get(view.assignment_id) not in ("rejected", "cancelled")
    ]
    closed: dict[UUID, list[date]] = {}
    for allocation_id, month, _pct in await MonthCloseRepository(session).established(
        [view.allocation.id for view in allocations]
    ):
        closed.setdefault(allocation_id, []).append(month)

    person_ids = set(occupancy) | {view.allocation.person_id for view in allocations}
    people: dict[UUID, tuple[str, UUID | None]] = {}
    if person_ids:
        rows = await session.execute(
            select(Person.id, Person.name, Person.manager_id).where(
                Person.id.in_(person_ids)
            )
        )
        people = {row[0]: (row[1], row[2]) for row in rows}
    manager_ids = {m for _name, m in people.values() if m is not None}
    manager_names: dict[UUID, str] = {}
    if manager_ids:
        rows = await session.execute(
            select(Person.id, Person.name).where(Person.id.in_(manager_ids))
        )
        manager_names = {row[0]: row[1] for row in rows}

    bars: dict[UUID, list[BoardBar]] = {}
    for view in allocations:
        allocation = view.allocation
        mismatch = view.mismatch
        bars.setdefault(allocation.person_id, []).append(
            BoardBar(
                allocation_id=allocation.id,
                person_id=allocation.person_id,
                person_name=view.person_name,
                assignment_id=view.assignment_id,
                assignment_name=view.assignment_name,
                budget_line_id=view.line.id,
                line_description=view.line.description,
                role=view.line.role,
                start_date=allocation.start_date,
                end_date=allocation.end_date,
                fte_pct=Decimal(allocation.fte_pct),
                tentative=view.tentative,
                verbally_agreed=statuses.get(view.assignment_id) == VERBALLY_AGREED,
                closed_months=tuple(sorted(closed.get(allocation.id, []))),
                category_mismatch=mismatch is not None,
                line_category=mismatch.line_category if mismatch else None,
                person_category=mismatch.person_category if mismatch else None,
            )
        )

    persons: list[BoardPerson] = []
    for person_id in person_ids:
        name, manager_id = people.get(person_id, ("", None))
        row = occupancy.get(person_id)
        cells = tuple(
            BoardCell(
                month=_first(cell.month),
                available=cell.available,
                pct=cell.pct,
                tentative_pct=cell.tentative_pct,
                over=cell.over,
                established=cell.established,
            )
            for cell in (row.cells if row else ())
        )
        now, room, idle = _summary(cells, current)
        persons.append(
            BoardPerson(
                person_id=person_id,
                person_name=name,
                manager_id=manager_id,
                manager_name=manager_names.get(manager_id) if manager_id else None,
                cells=cells,
                now_pct=now,
                room_from=room,
                idle_from=idle,
                over_months=tuple(cell.month for cell in cells if cell.over),
                bars=tuple(
                    sorted(
                        bars.get(person_id, []),
                        key=lambda bar: (bar.start_date, str(bar.allocation_id)),
                    )
                ),
            )
        )
    persons.sort(key=lambda person: (person.person_name.lower(), str(person.person_id)))

    open_roles = tuple(
        BoardOpenRole(
            budget_line_id=role.budget_line_id,
            assignment_id=role.assignment_id,
            assignment_name=role.assignment_name,
            description=role.description,
            role=role.role,
            fte=role.fte,
            unfilled_fte=role.unfilled_fte,
            start_date=role.start_date,
            end_date=role.end_date,
        )
        for role in await vacancies.unfilled_roles(session, today=today)
        if (role.start_date is None or role.start_date <= last_day)
        and (role.end_date is None or role.end_date >= first_day)
    )
    return Board(
        months=tuple(_first(month) for month in span),
        current_month=current,
        persons=tuple(persons),
        open_roles=open_roles,
    )


# -- the staffing of one assignment -------------------------------------------


@dataclass(frozen=True)
class RoleMonth:
    month: date
    # What the role asks in this month, as a percentage of a full week; zero
    # outside the role's own period.
    asked_pct: Decimal
    # What is on the role in this month: the established percentage of a
    # closed month, the planned one otherwise. A month that is partly covered
    # counts as covered.
    filled_pct: Decimal
    closed: bool

    @property
    def open_pct(self) -> Decimal:
        return max(Decimal(0), self.asked_pct - self.filled_pct)

    @property
    def over(self) -> bool:
        return self.filled_pct > self.asked_pct


@dataclass(frozen=True)
class RoleGap:
    """A stretch of months in which the same amount of a role is unfilled."""

    start: date
    end: date
    open_fte: Decimal


@dataclass(frozen=True)
class RoleBar:
    bar: BoardBar
    # The person is hired but has not started yet.
    starts_on: date | None
    # The inzet begins before the person starts.
    before_start: bool
    # The inzet lies partly outside the period of the role.
    outside_role_period: bool


@dataclass(frozen=True)
class RoleStaffing:
    budget_line_id: UUID
    description: str
    role: str | None
    fte: Decimal
    start_date: date | None
    end_date: date | None
    months: tuple[RoleMonth, ...]
    bars: tuple[RoleBar, ...]
    gaps: tuple[RoleGap, ...]

    @property
    def fully_staffed(self) -> bool:
        return not self.gaps

    @property
    def over_months(self) -> tuple[date, ...]:
        return tuple(m.month for m in self.months if m.over)


@dataclass(frozen=True)
class AssignmentStaffing:
    assignment_id: UUID
    months: tuple[date, ...]
    current_month: date
    closed_months: tuple[date, ...]
    # The assignment is still potential: all of this may not happen.
    tentative: bool
    roles: tuple[RoleStaffing, ...]
    # Open FTE in the first month, from the current one, in which anything
    # is open; None when every role is covered from now on.
    open_fte: Decimal | None
    open_from: date | None
    # People on this assignment who are above 100 percent in a month in which
    # they work on it, counting everything they do.
    overbooked_person_ids: tuple[UUID, ...]

    @property
    def staffed_count(self) -> int:
        return sum(1 for role in self.roles if role.fully_staffed)


_FTE = Decimal("0.01")


def _gaps(months: Sequence[RoleMonth]) -> tuple[RoleGap, ...]:
    gaps: list[RoleGap] = []
    run: list[RoleMonth] = []

    def close() -> None:
        if run:
            gaps.append(
                RoleGap(
                    start=run[0].month,
                    end=run[-1].month,
                    open_fte=(run[0].open_pct / 100).quantize(_FTE),
                )
            )
            run.clear()

    for month in months:
        if month.open_pct > 0 and (not run or run[-1].open_pct == month.open_pct):
            run.append(month)
        else:
            close()
            if month.open_pct > 0:
                run.append(month)
    close()
    return tuple(gaps)


async def assignment_staffing(
    session: AsyncSession, assignment_id: UUID, *, today: date | None = None
) -> AssignmentStaffing:
    """Per role of an assignment: what is asked, who fills it, what is open.

    The months are those of the assignment's own period, or of its roles and
    inzet when it has none.
    """
    from grip.models.person_standing import PersonStanding, Stage
    from grip.repositories.domain import AssignmentRepository
    from grip.services.phase import is_tentative

    row = await views.assignment_row(session, assignment_id)
    assignment = row.assignment
    repo = AssignmentRepository(session)
    lines = [
        line
        for line in await repo.budget_lines([assignment_id])
        if line.kind == "personnel"
    ]
    allocation_views = await views.allocation_views(
        session, assignment_ids=[assignment_id]
    )
    current = _first(Month.of(today or date.today()))

    starts = [d for d in [assignment.start_date] if d] or [
        d for d in [line.start_date for line in lines] if d
    ]
    ends = [d for d in [assignment.end_date] if d] or [
        d for d in [line.end_date for line in lines] if d
    ]
    starts += [v.allocation.start_date for v in allocation_views] if not starts else []
    ends += [v.allocation.end_date for v in allocation_views] if not ends else []
    if not starts or not ends:
        span: tuple[Month, ...] = (Month.of(current),)
    else:
        first, last = Month.of(min(starts)), Month.of(max(ends))
        months_list = [first]
        while months_list[-1] < last and len(months_list) < 60:
            months_list.append(months_list[-1].next())
        span = tuple(months_list)

    closed_months = set(
        await MonthCloseRepository(session).closed_months(assignment_id)
    )
    established: dict[tuple[UUID, date], Decimal] = {}
    closed_by_allocation: dict[UUID, list[date]] = {}
    for allocation_id, month, pct in await MonthCloseRepository(session).established(
        [v.allocation.id for v in allocation_views]
    ):
        established[(allocation_id, month)] = Decimal(str(pct))
        closed_by_allocation.setdefault(allocation_id, []).append(month)

    person_ids = {v.allocation.person_id for v in allocation_views}
    prospective: dict[UUID, date | None] = {}
    if person_ids:
        rows = await session.execute(
            select(PersonStanding.person_id, PersonStanding.start_date).where(
                PersonStanding.person_id.in_(person_ids),
                PersonStanding.stage == Stage.prospective.value,
            )
        )
        prospective = {r[0]: r[1] for r in rows}

    tentative = is_tentative(assignment.status)
    roles: list[RoleStaffing] = []
    for line in lines:
        on_line = [
            v for v in allocation_views if v.allocation.budget_line_id == line.id
        ]
        asked = Decimal(line.fte or 0) * 100
        role_months: list[RoleMonth] = []
        for month in span:
            first_day = _first(month)
            in_period = (
                line.start_date is not None
                and line.end_date is not None
                and line.start_date <= month.last_day
                and line.end_date >= month.first_day
            )
            filled = Decimal(0)
            for view in on_line:
                allocation = view.allocation
                if (
                    allocation.start_date <= month.last_day
                    and allocation.end_date >= month.first_day
                ):
                    filled += established.get(
                        (allocation.id, first_day), Decimal(allocation.fte_pct)
                    )
            role_months.append(
                RoleMonth(
                    month=first_day,
                    asked_pct=asked if in_period else Decimal(0),
                    filled_pct=filled,
                    closed=first_day in closed_months,
                )
            )
        bars: list[RoleBar] = []
        for view in on_line:
            allocation = view.allocation
            mismatch = view.mismatch
            starts_on = prospective.get(allocation.person_id)
            bars.append(
                RoleBar(
                    bar=BoardBar(
                        allocation_id=allocation.id,
                        person_id=allocation.person_id,
                        person_name=view.person_name,
                        assignment_id=assignment_id,
                        assignment_name=assignment.name,
                        budget_line_id=line.id,
                        line_description=line.description,
                        role=line.role,
                        start_date=allocation.start_date,
                        end_date=allocation.end_date,
                        fte_pct=Decimal(allocation.fte_pct),
                        tentative=tentative,
                        verbally_agreed=assignment.status == VERBALLY_AGREED,
                        closed_months=tuple(
                            sorted(closed_by_allocation.get(allocation.id, []))
                        ),
                        category_mismatch=mismatch is not None,
                        line_category=mismatch.line_category if mismatch else None,
                        person_category=mismatch.person_category if mismatch else None,
                    ),
                    starts_on=starts_on,
                    before_start=starts_on is not None
                    and allocation.start_date < starts_on,
                    outside_role_period=bool(
                        (line.start_date and allocation.start_date < line.start_date)
                        or (line.end_date and allocation.end_date > line.end_date)
                    ),
                )
            )
        bars.sort(key=lambda b: (b.bar.start_date, str(b.bar.allocation_id)))
        roles.append(
            RoleStaffing(
                budget_line_id=line.id,
                description=line.description,
                role=line.role,
                fte=Decimal(line.fte or 0),
                start_date=line.start_date,
                end_date=line.end_date,
                months=tuple(role_months),
                bars=tuple(bars),
                # What lies behind us cannot be filled any more.
                gaps=_gaps([m for m in role_months if m.month >= current]),
            )
        )

    open_from = min((gap.start for role in roles for gap in role.gaps), default=None)
    open_fte = (
        sum(
            (
                gap.open_fte
                for role in roles
                for gap in role.gaps
                if gap.start <= open_from <= gap.end
            ),
            Decimal(0),
        )
        if open_from is not None
        else None
    )

    overbooked: set[UUID] = set()
    if person_ids and span:
        for person in await steering.occupancy(session, span):
            if person.person_id not in person_ids:
                continue
            over = {_first(cell.month) for cell in person.cells if cell.over}
            for view in allocation_views:
                allocation = view.allocation
                if allocation.person_id != person.person_id:
                    continue
                if any(
                    allocation.start_date <= Month.of(m).last_day
                    and allocation.end_date >= m
                    for m in over
                ):
                    overbooked.add(person.person_id)

    return AssignmentStaffing(
        assignment_id=assignment_id,
        months=tuple(_first(month) for month in span),
        current_month=current,
        closed_months=tuple(sorted(closed_months)),
        tentative=tentative,
        roles=tuple(roles),
        open_fte=open_fte,
        open_from=open_from,
        overbooked_person_ids=tuple(sorted(overbooked, key=str)),
    )
