"""Steering overview of one year: turnover, occupancy, pipeline, costs, KPI, open roles.

Every function returns the full picture for the ids it is given. The route
decides which assignments and which persons a reader may see and passes
only those, so an aggregate is never taken over more than the reader sees.

Turnover per month is the sum of the per-month inzet amounts the calculation
module returns: closed months at the established percentage (realised), open
months at the planned percentage (forecast). Inzet on an assignment that is
not agreed yet counts as pipeline, not as forecast.

Occupancy has no money in it. It is the planned FTE percentage times the
month fraction from the calculation module, and the established percentage
for a closed month, which counts for the whole month (docs/domein.md,
Maandafsluiting). Available is one FTE per person per month; the model has
no part-time factor.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
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
from grip.services import cost_overview, pricing
from grip.services.pricing import DEFAULT_OPTIONS, PricingOptions
from grip.services.vacancies import service as vacancies

# Agreed with the client, or carried out: inzet in open months is forecast.
COMMITTED_STATUSES = frozenset({"accepted", "in_progress", "completed", "accounted"})
# Not agreed yet: inzet in open months is pipeline.
PIPELINE_STATUSES = frozenset({"draft", "requested", "quoted"})

QUOTE_STATUSES = ("issued", "accepted", "rejected", "superseded")


def months_of(year: int) -> tuple[Month, ...]:
    return calc.months_of_year(year)


# -- turnover -----------------------------------------------------------------


@dataclass(frozen=True)
class TurnoverMonth:
    month: Month
    realised_cents: int
    forecast_cents: int
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
        realised = forecast = pipeline = 0
        for assignment_id, by_month in per_assignment.items():
            if month not in by_month:
                continue
            closed, planned = by_month[month]
            status = by_id[assignment_id].status
            # A closed month is realised whatever the status became later.
            realised += closed
            if status in COMMITTED_STATUSES:
                forecast += planned
            elif status in PIPELINE_STATUSES:
                pipeline += planned
        months.append(
            TurnoverMonth(
                month=month,
                realised_cents=realised,
                forecast_cents=forecast,
                pipeline_cents=pipeline,
            )
        )
    return Turnover(
        months=tuple(months),
        unpriced=tuple(sorted(by_id[i].name for i in unpriced)),
    )


# -- occupancy ----------------------------------------------------------------


@dataclass(frozen=True)
class PersonOccupancy:
    person_id: UUID
    person_name: str
    # Allocated FTE percentage per month of the year, twelve values. ``None``
    # in a month the person was not available for inzet.
    months: tuple[Decimal | None, ...]

    @property
    def available_months(self) -> int:
        return sum(1 for pct in self.months if pct is not None)

    @property
    def average_pct(self) -> Decimal | None:
        values = [pct for pct in self.months if pct is not None]
        if not values:
            return None
        return _round_pct(Fraction(sum(Fraction(v) for v in values), len(values)))


@dataclass(frozen=True)
class OccupancyMonth:
    month: Month
    allocated_fte: Decimal
    available_fte: Decimal
    # Persons below, at and above 100 percent in this month.
    under: int
    full: int
    over: int

    @property
    def pct(self) -> Decimal | None:
        if self.available_fte == 0:
            return None
        return _round_pct(
            Fraction(self.allocated_fte) / Fraction(self.available_fte) * 100
        )


def _round_pct(value: Fraction) -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal("0.1")
    )


async def occupancy(
    session: AsyncSession,
    year: int,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[PersonOccupancy]:
    """Allocated FTE percentage per person and month, for everyone deployable.

    A person is available in a month with a billing scale valid in it, or
    with inzet in it. Persons with neither in the whole year are left out.
    """
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    year_months = months_of(year)

    allocations = list(
        (
            await session.execute(
                select(Allocation).where(
                    Allocation.start_date <= year_end, Allocation.end_date >= year_start
                )
            )
        ).scalars()
    )
    established = {
        (allocation_id, Month.of(month)): Decimal(str(pct))
        for allocation_id, month, pct in await MonthCloseRepository(
            session
        ).established([a.id for a in allocations])
    }

    allocated: dict[UUID, dict[Month, Fraction]] = defaultdict(
        lambda: defaultdict(Fraction)
    )
    for allocation in allocations:
        for month, fraction in calc.month_fractions(
            allocation.start_date, allocation.end_date, options.partial_months
        ):
            if month.year != year:
                continue
            actual = established.get((allocation.id, month))
            if actual is not None:
                allocated[allocation.person_id][month] += Fraction(actual)
            else:
                allocated[allocation.person_id][month] += (
                    Fraction(Decimal(allocation.fte_pct)) * fraction
                )

    scales = list(
        (
            await session.execute(
                select(PersonScale).where(
                    PersonScale.valid_from <= year_end,
                    (PersonScale.valid_to.is_(None))
                    | (PersonScale.valid_to >= year_start),
                )
            )
        ).scalars()
    )
    available: dict[UUID, set[Month]] = defaultdict(set)
    for scale in scales:
        for month in year_months:
            if scale.valid_from <= month.last_day and (
                scale.valid_to is None or scale.valid_to >= month.first_day
            ):
                available[scale.person_id].add(month)
    for person_id, by_month in allocated.items():
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
        months: list[Decimal | None] = []
        for month in year_months:
            if month not in available[person_id]:
                months.append(None)
            else:
                months.append(_round_pct(allocated[person_id].get(month, Fraction(0))))
        rows.append(
            PersonOccupancy(person_id=person_id, person_name=name, months=tuple(months))
        )
    return rows


def occupancy_months(
    year: int, rows: Iterable[PersonOccupancy]
) -> list[OccupancyMonth]:
    """Totals per month over exactly the persons given."""
    rows = list(rows)
    result: list[OccupancyMonth] = []
    for index, month in enumerate(months_of(year)):
        values = [row.months[index] for row in rows if row.months[index] is not None]
        result.append(
            OccupancyMonth(
                month=month,
                allocated_fte=(sum(values, Decimal(0)) / Decimal(100)).quantize(
                    Decimal("0.01")
                ),
                available_fte=Decimal(len(values)),
                under=sum(1 for v in values if v < 100),
                full=sum(1 for v in values if v == 100),
                over=sum(1 for v in values if v > 100),
            )
        )
    return result


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
