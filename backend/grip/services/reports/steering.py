"""Steering overview of one year: turnover, occupancy, pipeline, costs, KPI, open roles.

Every function returns the full picture for the ids it is given. The route
decides which assignments and which persons a reader may see and passes
only those, so an aggregate is never taken over more than the reader sees.

Turnover per month is the sum of the per-month inzet amounts the calculation
module returns: closed months at the established percentage (realised), open
months at the planned percentage (forecast). How firm the forecast is comes
from the phase service: committed and verbally agreed assignments count in
the forecast, with the verbal part shown apart; an assignment that is not
agreed yet counts as pipeline.

Occupancy has no money in it. A cell is what a person is allocated in a
month, in percent of one FTE, built from the parts per assignment: the
planned percentage times the month fraction from the calculation module, or
the established percentage of a closed month, which counts for the whole
month (docs/domein.md, Maandafsluiting). Inzet on a potential assignment is
tentative; that comes from the staffing service. Available is one FTE per
person per month; the model has no part-time factor.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import AmountSource, Month
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.person_details import BillabilityTarget, PersonScale
from grip.models.quote import Quote
from grip.repositories.domain import AssignmentRepository, MonthCloseRepository
from grip.services import (
    assignment_finance,
    assignment_views,
    cost_overview,
    pricing,
    read_cache,
    staffing,
)
from grip.services.phase import Commitment, commitment_of
from grip.services.pricing import DEFAULT_OPTIONS, PricingOptions
from grip.services.vacancies import service as vacancies

QUOTE_STATUSES = ("issued", "accepted", "rejected", "superseded")


def months_of(year: int) -> tuple[Month, ...]:
    return calc.months_of_year(year)


# -- turnover -----------------------------------------------------------------


@dataclass(frozen=True)
class TurnoverMonth:
    month: Month
    # Closed months, whatever became of the assignment later.
    realised_cents: int
    # Open months of assignments that are agreed, formally or verbally.
    forecast_cents: int
    # The part of the forecast that rests on a verbal agreement only.
    verbal_cents: int
    # Open months of assignments that are not agreed yet.
    pipeline_cents: int


@dataclass(frozen=True)
class Turnover:
    months: tuple[TurnoverMonth, ...]
    # Names of assignments whose inzet could not be priced; they are left out.
    unpriced: tuple[str, ...]

    @property
    def realised_cents(self) -> int:
        return sum(m.realised_cents for m in self.months)

    @property
    def forecast_cents(self) -> int:
        return sum(m.forecast_cents for m in self.months)

    @property
    def verbal_cents(self) -> int:
        return sum(m.verbal_cents for m in self.months)

    @property
    def pipeline_cents(self) -> int:
        return sum(m.pipeline_cents for m in self.months)


async def _assignments(
    session: AsyncSession, assignment_ids: Iterable[UUID] | None
) -> list[Assignment]:
    query = select(Assignment).order_by(func.lower(Assignment.name), Assignment.id)
    if assignment_ids is not None:
        ids = list(assignment_ids)
        if not ids:
            return []
        query = query.where(Assignment.id.in_(ids))
    return list((await session.execute(query)).scalars())


async def turnover(
    session: AsyncSession,
    year: int,
    *,
    assignment_ids: Iterable[UUID] | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> Turnover:
    """Inzet amounts per month of ``year``; ``assignment_ids=None`` means all."""
    wanted = None if assignment_ids is None else frozenset(assignment_ids)
    return await read_cache.remember_all(
        session,
        "turnover",
        (year, wanted, options),
        lambda: _turnover(session, year, wanted, options),
    )


async def _turnover(
    session: AsyncSession,
    year: int,
    assignment_ids: frozenset[UUID] | None,
    options: PricingOptions,
) -> Turnover:
    assignments = await _assignments(session, assignment_ids)
    by_id = {a.id: a for a in assignments}
    lines = await AssignmentRepository(session).budget_lines(list(by_id))
    inputs = await pricing.load_inputs_for_lines(session, lines, options=options)
    line_assignment = {str(line.id): line.assignment_id for line in lines}

    # Per assignment and month: (realised, open). An assignment that cannot
    # be priced is left out as a whole, like on the stand van zaken.
    per_assignment: dict[UUID, dict[Month, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )
    unpriced: set[UUID] = set()
    for allocation in inputs.allocations:
        assignment_id = line_assignment[allocation.budget_line_id]
        if assignment_id in unpriced:
            continue
        try:
            amounts = calc.allocation_months(
                allocation,
                inputs.rates,
                inputs.scales,
                partial_months=options.partial_months,
                actuals=inputs.actuals,
            )
        except calc.CalcError:
            unpriced.add(assignment_id)
            per_assignment.pop(assignment_id, None)
            continue
        for amount in amounts:
            if amount.month.year != year:
                continue
            slot = per_assignment[assignment_id][amount.month]
            slot[0 if amount.source is AmountSource.ACTUAL else 1] += amount.cents

    months: list[TurnoverMonth] = []
    for month in months_of(year):
        realised = forecast = verbal = pipeline = 0
        for assignment_id, by_month in per_assignment.items():
            if month not in by_month:
                continue
            closed, planned = by_month[month]
            commitment = commitment_of(by_id[assignment_id].status)
            # A closed month is realised whatever the status became later.
            realised += closed
            if commitment is Commitment.COMMITTED:
                forecast += planned
            elif commitment is Commitment.VERBAL:
                forecast += planned
                verbal += planned
            elif commitment is Commitment.PIPELINE:
                pipeline += planned
        months.append(
            TurnoverMonth(
                month=month,
                realised_cents=realised,
                forecast_cents=forecast,
                verbal_cents=verbal,
                pipeline_cents=pipeline,
            )
        )
    return Turnover(
        months=tuple(months),
        unpriced=tuple(sorted(by_id[i].name for i in unpriced)),
    )


async def agreed_figures(
    session: AsyncSession,
    year: int,
    *,
    assignment_ids: Iterable[UUID] | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> assignment_finance.Figures:
    """The year of the agreed assignments in the words of the assignment pages.

    The sum of the figures the Financieel tab shows per assignment, over the
    assignments that count in the forecast (agreed formally or verbally).
    An assignment that cannot be priced is left out, as in the turnover.
    """
    agreed = [
        assignment.id
        for assignment in await _assignments(session, assignment_ids)
        if commitment_of(assignment.status) in (Commitment.COMMITTED, Commitment.VERBAL)
    ]
    rows = await assignment_views.assignment_rows(session, only_ids=agreed)
    found = await assignment_finance.assignment_finances(
        session, rows, year=year, options=options
    )
    return assignment_finance.Figures.sum(
        data.totals for data in found.values() if data.totals is not None
    )


# -- occupancy ----------------------------------------------------------------


def _round_pct(value: Fraction) -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal("0.1")
    )


def _round_fte(value: Fraction) -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal("0.01")
    )


def next_months(first: Month, count: int) -> tuple[Month, ...]:
    """``count`` consecutive months, starting at ``first``."""
    months = [first]
    while len(months) < count:
        months.append(months[-1].next())
    return tuple(months)


@dataclass(frozen=True)
class OccupancyPart:
    """What one assignment takes of a person in a month."""

    assignment_id: UUID
    assignment_name: str
    exact: Fraction
    # Inzet on a potential assignment: it may not happen.
    tentative: bool
    # Tentative, but the client has said yes.
    verbally_agreed: bool
    # From a closed month: the percentage was established.
    established: bool

    @property
    def pct(self) -> Decimal:
        return _round_pct(self.exact)


@dataclass(frozen=True)
class OccupancyCell:
    month: Month
    # False in a month the person could not be deployed.
    available: bool
    parts: tuple[OccupancyPart, ...]

    @property
    def exact(self) -> Fraction:
        return sum((part.exact for part in self.parts), Fraction(0))

    @property
    def pct(self) -> Decimal:
        return _round_pct(self.exact)

    @property
    def tentative_pct(self) -> Decimal:
        return _round_pct(
            sum((p.exact for p in self.parts if p.tentative), Fraction(0))
        )

    @property
    def established(self) -> bool:
        """Everything in this cell comes from closed months."""
        return bool(self.parts) and all(part.established for part in self.parts)

    @property
    def over(self) -> bool:
        return self.exact > 100


@dataclass(frozen=True)
class PersonOccupancy:
    person_id: UUID
    person_name: str
    # One cell per month asked for, in order.
    cells: tuple[OccupancyCell, ...]

    @property
    def available_cells(self) -> tuple[OccupancyCell, ...]:
        return tuple(cell for cell in self.cells if cell.available)

    @property
    def average_pct(self) -> Decimal | None:
        """Mean over the months the person was available."""
        cells = self.available_cells
        if not cells:
            return None
        return _round_pct(sum((c.exact for c in cells), Fraction(0)) / len(cells))

    @property
    def over_months(self) -> tuple[Month, ...]:
        return tuple(cell.month for cell in self.cells if cell.over)


@dataclass(frozen=True)
class OccupancyMonth:
    """Totals of one month over the persons given."""

    month: Month
    allocated_fte: Decimal
    # The tentative part of what is allocated.
    tentative_fte: Decimal
    available_fte: Decimal
    # Room left, with nobody's overbooking set off against it.
    free_fte: Decimal
    pct: Decimal | None
    under: int
    full: int
    over: int


@dataclass(frozen=True)
class OccupancySummary:
    """The answer before the table, over exactly the persons given."""

    person_count: int
    # Mean occupancy of the year, over every available person-month.
    average_pct: Decimal | None
    over_count: int
    over_months: tuple[Month, ...]
    # Now, whatever year is on screen: this month and the three after it.
    current_month: Month
    window: tuple[OccupancyMonth, ...]
    # Available in the three months after this one, without any inzet in them.
    idle_count: int


async def occupancy(
    session: AsyncSession,
    months: Sequence[Month],
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[PersonOccupancy]:
    """What every deployable person is allocated in ``months`` (consecutive).

    A person is available in a month with a billing scale valid in it, or
    with inzet in it. Persons with neither in the whole span are left out.
    Inzet on a cancelled assignment does not count.
    """
    if not months:
        return []
    wanted = set(months)
    first_day, last_day = months[0].first_day, months[-1].last_day

    allocations = await staffing.staffed_allocations(
        session, start=first_day, end=last_day
    )
    established = {
        (allocation_id, Month.of(month)): Decimal(str(pct))
        for allocation_id, month, pct in await MonthCloseRepository(
            session
        ).established([a.allocation_id for a in allocations])
    }
    names: dict[UUID, str] = {}
    assignment_ids = {a.assignment_id for a in allocations}
    if assignment_ids:
        result = await session.execute(
            select(Assignment.id, Assignment.name).where(
                Assignment.id.in_(assignment_ids)
            )
        )
        names = {row.id: row.name for row in result}

    # Per person and month, per assignment: [exact, tentative, verbal, all established].
    parts: dict[UUID, dict[Month, dict[UUID, list[Any]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for allocation in allocations:
        for month, fraction in calc.month_fractions(
            allocation.start_date, allocation.end_date, options.partial_months
        ):
            if month not in wanted:
                continue
            actual = established.get((allocation.allocation_id, month))
            exact = (
                Fraction(actual)
                if actual is not None
                else Fraction(Decimal(allocation.fte_pct)) * fraction
            )
            slot = parts[allocation.person_id][month].setdefault(
                allocation.assignment_id,
                [Fraction(0), allocation.tentative, allocation.verbally_agreed, True],
            )
            slot[0] += exact
            slot[3] = slot[3] and actual is not None

    scales = list(
        (
            await session.execute(
                select(PersonScale).where(
                    PersonScale.valid_from <= last_day,
                    (PersonScale.valid_to.is_(None))
                    | (PersonScale.valid_to >= first_day),
                )
            )
        ).scalars()
    )
    available: dict[UUID, set[Month]] = defaultdict(set)
    for scale in scales:
        for month in months:
            if scale.valid_from <= month.last_day and (
                scale.valid_to is None or scale.valid_to >= month.first_day
            ):
                available[scale.person_id].add(month)
    for person_id, by_month in parts.items():
        available[person_id].update(by_month)

    if not available:
        return []
    persons = (
        await session.execute(
            select(Person.id, Person.name)
            .where(Person.id.in_(available))
            .order_by(func.lower(Person.name), Person.id)
        )
    ).all()
    rows: list[PersonOccupancy] = []
    for person_id, name in persons:
        cells = []
        for month in months:
            by_assignment = parts[person_id].get(month, {})
            cells.append(
                OccupancyCell(
                    month=month,
                    available=month in available[person_id],
                    parts=tuple(
                        sorted(
                            (
                                OccupancyPart(
                                    assignment_id=assignment_id,
                                    assignment_name=names.get(assignment_id, ""),
                                    exact=slot[0],
                                    tentative=slot[1],
                                    verbally_agreed=slot[2],
                                    established=slot[3],
                                )
                                for assignment_id, slot in by_assignment.items()
                                if slot[0] > 0
                            ),
                            key=lambda part: (-part.exact, part.assignment_name),
                        )
                    ),
                )
            )
        rows.append(
            PersonOccupancy(person_id=person_id, person_name=name, cells=tuple(cells))
        )
    return rows


async def occupancy_of_year(
    session: AsyncSession, year: int, *, options: PricingOptions = DEFAULT_OPTIONS
) -> list[PersonOccupancy]:
    return await occupancy(session, months_of(year), options=options)


async def not_deployable(
    session: AsyncSession, deployable_ids: Iterable[UUID]
) -> list[tuple[UUID, str]]:
    """Active persons who are no row of the occupancy: no billing scale, no inzet."""
    ids = list(deployable_ids)
    query = select(Person.id, Person.name).where(Person.is_active.is_(True))
    if ids:
        query = query.where(Person.id.notin_(ids))
    result = await session.execute(query.order_by(func.lower(Person.name), Person.id))
    return [(row.id, row.name) for row in result]


def occupancy_months(
    months: Sequence[Month], rows: Iterable[PersonOccupancy]
) -> list[OccupancyMonth]:
    """Totals per month over exactly the persons given."""
    rows = list(rows)
    result: list[OccupancyMonth] = []
    for month in months:
        cells = [
            cell
            for row in rows
            for cell in row.cells
            if cell.month == month and cell.available
        ]
        allocated = sum((cell.exact for cell in cells), Fraction(0))
        tentative = sum(
            (p.exact for cell in cells for p in cell.parts if p.tentative), Fraction(0)
        )
        free = sum((max(Fraction(0), 100 - cell.exact) for cell in cells), Fraction(0))
        result.append(
            OccupancyMonth(
                month=month,
                allocated_fte=_round_fte(allocated / 100),
                tentative_fte=_round_fte(tentative / 100),
                available_fte=Decimal(len(cells)),
                free_fte=_round_fte(free / 100),
                pct=_round_pct(allocated / len(cells)) if cells else None,
                under=sum(1 for cell in cells if cell.exact < 100),
                full=sum(1 for cell in cells if cell.exact == 100),
                over=sum(1 for cell in cells if cell.exact > 100),
            )
        )
    return result


def idle_person_ids(
    window_rows: Sequence[PersonOccupancy], window: Sequence[Month]
) -> set[UUID]:
    """Who is available in the months after this one and has no inzet in them.

    These are the people the figure "zonder inzet de komende drie maanden"
    counts; the screen shows exactly them when the figure is opened.
    """
    ahead = set(window[1:])
    idle: set[UUID] = set()
    for row in window_rows:
        coming = [c for c in row.cells if c.month in ahead and c.available]
        if coming and all(cell.exact == 0 for cell in coming):
            idle.add(row.person_id)
    return idle


def occupancy_summary(
    year_rows: Sequence[PersonOccupancy],
    window_rows: Sequence[PersonOccupancy],
    window: Sequence[Month],
) -> OccupancySummary:
    """The figures on top. ``window`` is this month and the three after it.

    The figures about now count the persons of ``year_rows`` only, so every
    figure counts rows that are in the block and can be shown.
    """
    in_block = {row.person_id for row in year_rows}
    window_rows = [row for row in window_rows if row.person_id in in_block]
    available = [cell for row in year_rows for cell in row.available_cells]
    over_months = sorted({month for row in year_rows for month in row.over_months})
    return OccupancySummary(
        person_count=len(year_rows),
        average_pct=_round_pct(
            sum((c.exact for c in available), Fraction(0)) / len(available)
        )
        if available
        else None,
        over_count=sum(1 for row in year_rows if row.over_months),
        over_months=tuple(over_months),
        current_month=window[0],
        window=tuple(occupancy_months(window, window_rows)),
        idle_count=len(idle_person_ids(window_rows, window)),
    )


async def last_inzet_end(
    session: AsyncSession, person_ids: Iterable[UUID]
) -> dict[UUID, date]:
    """Per person the last day of inzet, on any assignment that still counts.

    For the line "vrij, laatste inzet tot ..." of a person without inzet.
    Inzet on a cancelled assignment is left out.
    """
    latest: dict[UUID, date] = {}
    for allocation in await staffing.staffed_allocations(
        session, person_ids=person_ids
    ):
        current = latest.get(allocation.person_id)
        if current is None or allocation.end_date > current:
            latest[allocation.person_id] = allocation.end_date
    return latest


# -- pipeline of quotes -------------------------------------------------------


@dataclass(frozen=True)
class QuoteRow:
    quote_id: UUID
    assignment_id: UUID
    assignment_name: str
    client_name: str | None
    status: str
    total_cents: int
    issued_at: datetime
    valid_until: str | None


async def quotes_of_year(
    session: AsyncSession,
    year: int,
    *,
    assignment_ids: Iterable[UUID] | None = None,
) -> list[QuoteRow]:
    """Quotes issued in ``year``, newest first."""
    query = (
        select(Quote, Assignment, Organisation.name)
        .join(Assignment, Assignment.id == Quote.assignment_id)
        .outerjoin(Organisation, Organisation.id == Assignment.client_organisation_id)
        .where(func.extract("year", Quote.issued_at) == year)
        .order_by(Quote.issued_at.desc(), Quote.id)
    )
    if assignment_ids is not None:
        ids = list(assignment_ids)
        if not ids:
            return []
        query = query.where(Quote.assignment_id.in_(ids))
    rows: list[QuoteRow] = []
    for quote, assignment, client_name in (await session.execute(query)).all():
        valid_until = (quote.snapshot or {}).get("valid_until")
        rows.append(
            QuoteRow(
                quote_id=quote.id,
                assignment_id=assignment.id,
                assignment_name=assignment.name,
                client_name=client_name,
                status=quote.status,
                total_cents=quote.total_cents,
                issued_at=quote.issued_at,
                valid_until=valid_until if isinstance(valid_until, str) else None,
            )
        )
    return rows


# -- costs --------------------------------------------------------------------


async def cost_items(
    session: AsyncSession, year: int, *, options: PricingOptions = DEFAULT_OPTIONS
) -> list[cost_overview.CostItemOverview]:
    """Cost items with the forecast, coverage and remainder of ``year``."""
    return await cost_overview.cost_item_overviews(session, year=year, options=options)


# -- billability --------------------------------------------------------------


@dataclass(frozen=True)
class KpiRow:
    person_id: UUID
    person_name: str
    # ``None`` when the amounts cannot be derived for this person.
    overview: pricing.KpiOverview | None


async def kpi_person_ids(session: AsyncSession, year: int) -> list[tuple[UUID, str]]:
    """Persons with a target for the year or with inzet in it, by name."""
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    with_target = select(BillabilityTarget.person_id).where(
        BillabilityTarget.year == year
    )
    with_inzet = select(Allocation.person_id).where(
        Allocation.start_date <= year_end, Allocation.end_date >= year_start
    )
    result = await session.execute(
        select(Person.id, Person.name)
        .where(Person.id.in_(with_target) | Person.id.in_(with_inzet))
        .order_by(func.lower(Person.name), Person.id)
    )
    return [(row.id, row.name) for row in result]


async def kpi_row(
    session: AsyncSession,
    person_id: UUID,
    person_name: str,
    year: int,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> KpiRow:
    try:
        overview = await pricing.kpi_overview(session, person_id, year, options=options)
    except calc.CalcError:
        overview = None
    return KpiRow(person_id=person_id, person_name=person_name, overview=overview)


async def kpi_rows(
    session: AsyncSession,
    people: Sequence[tuple[UUID, str]],
    year: int,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[KpiRow]:
    """``kpi_row`` for several persons, read together; in the order given."""
    overviews = await pricing.kpi_overviews(
        session, [person_id for person_id, _ in people], year, options=options
    )
    return [
        KpiRow(person_id=person_id, person_name=name, overview=overviews[person_id])
        for person_id, name in people
    ]


# -- open roles ---------------------------------------------------------------


@dataclass(frozen=True)
class OpenRole:
    # ``None`` for a vacancy that hangs on no budget line.
    assignment_id: UUID | None
    assignment_name: str | None
    budget_line_id: UUID | None
    description: str
    unfilled_fte: Decimal
    start_date: date | None
    end_date: date | None
    # The status of the vacancy that runs for this role, if any.
    vacancy_status: str | None


_LIVE_VACANCY_STATUSES = ("draft", "requested", "approved", "open")


async def open_roles(
    session: AsyncSession, *, today: date | None = None
) -> list[OpenRole]:
    """Roles with room left: unfilled budget lines, and vacancies that run.

    "Unfilled" is the definition of the vacancy service. A line with a running
    vacancy is not in that list, so the running vacancies are added here.
    """
    roles: list[OpenRole] = [
        OpenRole(
            assignment_id=role.assignment_id,
            assignment_name=role.assignment_name,
            budget_line_id=role.budget_line_id,
            description=role.role or role.description,
            unfilled_fte=role.unfilled_fte,
            start_date=role.start_date,
            end_date=role.end_date,
            vacancy_status=None,
        )
        for role in await vacancies.unfilled_roles(session, today=today)
    ]
    running = [
        vacancy
        for vacancy in await vacancies.list_vacancies(session)
        if vacancy.status in _LIVE_VACANCY_STATUSES
    ]
    line_ids = [v.budget_line_id for v in running if v.budget_line_id is not None]
    on_line: dict[UUID, tuple[UUID, str]] = {}
    if line_ids:
        result = await session.execute(
            select(BudgetLine.id, Assignment.id, Assignment.name)
            .join(Assignment, Assignment.id == BudgetLine.assignment_id)
            .where(BudgetLine.id.in_(line_ids))
        )
        on_line = {row[0]: (row[1], row[2]) for row in result}
    for vacancy in running:
        assignment = (
            on_line.get(vacancy.budget_line_id) if vacancy.budget_line_id else None
        )
        roles.append(
            OpenRole(
                assignment_id=assignment[0] if assignment else None,
                assignment_name=assignment[1] if assignment else None,
                budget_line_id=vacancy.budget_line_id,
                description=vacancy.function_title,
                unfilled_fte=Decimal(vacancy.fte),
                start_date=vacancy.start_date,
                end_date=vacancy.end_date,
                vacancy_status=vacancy.status,
            )
        )
    roles.sort(key=lambda r: ((r.assignment_name or "").lower(), r.description.lower()))
    return roles
