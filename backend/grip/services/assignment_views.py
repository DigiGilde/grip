"""Read models for the assignment screens: lists, the budget, the overview, inzet.

The routes of the assignment slice read through this module, so they never
query tables or call the calculation module themselves. Nothing here decides
who may see what: every view carries all data and the route leaves out the
fields of the data classes the subject may not read.

A calculation that cannot be made (a month without an active rate card, a
person without a billing scale) does not fail the whole view. The amounts
that depend on it are ``None`` and the view carries a sentence that says why.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.models.assignment import (
    ROLE_OWNER,
    Allocation,
    Assignment,
    AssignmentRole,
    BudgetLine,
)
from grip.models.audit_log import AuditLog
from grip.models.cost import CostItem
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote import Quote
from grip.repositories.domain import AssignmentRepository
from grip.services.errors import NotFoundError
from grip.services.phase import (
    Phase,
    assignment_phase,
    is_tentative,
    statuses_in_phase,
)
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    CalcInputs,
    LineOverview,
    PricingOptions,
    load_inputs_for_lines,
    overview_from_inputs,
)

# -- calculation errors -------------------------------------------------------


def describe_calc_error(exc: calc.CalcError, *, personal: bool = False) -> str:
    """A sentence for the user about why an amount could not be computed.

    Without ``personal`` the sentence never names a scale or a person: a
    budget total is class B, and a scale is class D.
    """
    if isinstance(exc, calc.MissingRateCardError):
        return f"Er is geen actieve tarievenkaart voor {exc.year}."
    if isinstance(exc, calc.MissingRateError):
        return (
            f"De tarievenkaart van {exc.year} heeft geen tarief voor "
            f"categorie {exc.category}."
        )
    if isinstance(exc, calc.MissingScaleBandError):
        if personal:
            return (
                f"De tarievenkaart van {exc.year} koppelt schaal {exc.scale} "
                "niet aan een categorie."
            )
        return (
            f"De tarievenkaart van {exc.year} koppelt een inzetschaal niet "
            "aan een categorie."
        )
    if isinstance(exc, calc.MissingPersonScaleError):
        if personal:
            return f"Deze persoon heeft geen inzetschaal op {exc.day.isoformat()}."
        return "Voor iemand op deze opdracht ontbreekt een inzetschaal."
    if isinstance(exc, calc.CoverageExceededError):
        return "Een kostenpost is voor meer dan 100 procent gedekt."
    return "De bedragen konden niet worden berekend."


# -- views --------------------------------------------------------------------


@dataclass(frozen=True)
class RoleView:
    person_id: UUID
    person_name: str
    role: str


@dataclass(frozen=True)
class AssignmentRow:
    assignment: Assignment
    client_name: str | None
    contractor_name: str | None
    roles: tuple[RoleView, ...]
    # When the assignment got its current status.
    status_since: datetime | None = None
    # Total of the latest quote that was issued; None without one.
    latest_quote_cents: int | None = None

    @property
    def phase(self) -> Phase:
        return assignment_phase(self.assignment)

    @property
    def owner(self) -> RoleView | None:
        return next((r for r in self.roles if r.role == ROLE_OWNER), None)


@dataclass(frozen=True)
class AllocationView:
    allocation: Allocation
    person_name: str
    line: BudgetLine
    assignment_id: UUID
    assignment_name: str
    # None when the amount could not be computed; see ``pricing_error``.
    amount_cents: int | None
    pricing_error: str | None
    # R14: the first run of months in which the person bills in another
    # category than the line assumes. None when there is none.
    mismatch: calc.CategoryMismatch | None
    # The assignment is still potential, so this inzet may not happen.
    tentative: bool = False


@dataclass(frozen=True)
class CoverageView:
    coverage_id: UUID
    cost_item_id: UUID
    description: str
    pct: object
    amount_cents: int | None


@dataclass(frozen=True)
class LineView:
    line: BudgetLine
    # None when the line could not be priced.
    overview: LineOverview | None
    budgeted_by_year: dict[int, int]
    pricing_error: str | None
    allocations: tuple[AllocationView, ...]
    coverages: tuple[CoverageView, ...]


@dataclass(frozen=True)
class Totals:
    budgeted_cents: int
    realised_cents: int
    forecast_cents: int
    coverage_cents: int

    @property
    def used_cents(self) -> int:
        return self.realised_cents + self.forecast_cents + self.coverage_cents

    @property
    def available_cents(self) -> int:
        return self.budgeted_cents - self.used_cents

    @property
    def overrun(self) -> bool:
        return self.available_cents < 0

    @classmethod
    def of(cls, overviews: Iterable[LineOverview | Totals]) -> Totals:
        items = list(overviews)
        return cls(
            budgeted_cents=sum(i.budgeted_cents for i in items),
            realised_cents=sum(i.realised_cents for i in items),
            forecast_cents=sum(i.forecast_cents for i in items),
            coverage_cents=sum(i.coverage_cents for i in items),
        )


@dataclass(frozen=True)
class AssignmentView:
    row: AssignmentRow
    # None means the whole period.
    year: int | None
    lines: tuple[LineView, ...]
    # None when at least one line could not be priced.
    totals: Totals | None
    budgeted_by_year: dict[int, int]
    pricing_error: str | None


@dataclass(frozen=True)
class PersonOption:
    person_id: UUID
    name: str
    # The day a hired colleague starts; None for someone who already works here.
    starts_on: date | None = None


@dataclass(frozen=True)
class LineOption:
    line: BudgetLine
    assignment_id: UUID
    assignment_name: str


# -- assignments --------------------------------------------------------------


async def _organisation_names(
    session: AsyncSession, ids: Iterable[UUID | None]
) -> dict[UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(
        select(Organisation.id, Organisation.name).where(Organisation.id.in_(wanted))
    )
    return {row[0]: row[1] for row in rows}


async def _roles(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> dict[UUID, tuple[RoleView, ...]]:
    ids = list(set(assignment_ids))
    if not ids:
        return {}
    rows = await session.execute(
        select(
            AssignmentRole.assignment_id,
            AssignmentRole.person_id,
            Person.name,
            AssignmentRole.role,
        )
        .join(Person, Person.id == AssignmentRole.person_id)
        .where(AssignmentRole.assignment_id.in_(ids))
        .order_by(AssignmentRole.role.desc(), Person.name)
    )
    grouped: dict[UUID, list[RoleView]] = {}
    for assignment_id, person_id, name, role in rows:
        grouped.setdefault(assignment_id, []).append(RoleView(person_id, name, role))
    return {k: tuple(v) for k, v in grouped.items()}


async def _status_since(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> dict[UUID, datetime]:
    """The moment of the last change of status, from the audit log."""
    ids = [str(i) for i in set(assignment_ids)]
    if not ids:
        return {}
    rows = await session.execute(
        select(AuditLog.entity_id, func.max(AuditLog.occurred_at))
        .where(
            AuditLog.entity == "assignment",
            AuditLog.entity_id.in_(ids),
            AuditLog.new_value.has_key("status"),
        )
        .group_by(AuditLog.entity_id)
    )
    return {UUID(row[0]): row[1] for row in rows}


async def _latest_quote_totals(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> dict[UUID, int]:
    ids = list(set(assignment_ids))
    if not ids:
        return {}
    rows = await session.execute(
        select(Quote.assignment_id, Quote.total_cents)
        .where(Quote.assignment_id.in_(ids), Quote.issued_at.is_not(None))
        .order_by(Quote.issued_at)
    )
    # Later rows overwrite earlier ones, so the latest quote wins.
    return {row[0]: row[1] for row in rows}


async def assignment_rows(
    session: AsyncSession,
    *,
    status: str | None = None,
    only_ids: Iterable[UUID] | None = None,
) -> list[AssignmentRow]:
    """Assignments with the names of their parties and role holders.

    ``only_ids`` limits the list; an empty collection gives an empty list.
    """
    stmt = select(Assignment).order_by(Assignment.name, Assignment.id)
    if status is not None:
        stmt = stmt.where(Assignment.status == status)
    if only_ids is not None:
        ids = list(set(only_ids))
        if not ids:
            return []
        stmt = stmt.where(Assignment.id.in_(ids))
    found = list((await session.execute(stmt)).scalars())
    names = await _organisation_names(
        session,
        [a.client_organisation_id for a in found]
        + [a.contractor_organisation_id for a in found],
    )
    roles = await _roles(session, [a.id for a in found])
    since = await _status_since(session, [a.id for a in found])
    quoted = await _latest_quote_totals(session, [a.id for a in found])
    return [
        AssignmentRow(
            assignment=a,
            client_name=names.get(a.client_organisation_id)
            if a.client_organisation_id
            else None,
            contractor_name=names.get(a.contractor_organisation_id)
            if a.contractor_organisation_id
            else None,
            roles=roles.get(a.id, ()),
            status_since=since.get(a.id) or a.created_at,
            latest_quote_cents=quoted.get(a.id),
        )
        for a in found
    ]


async def assignment_row(session: AsyncSession, assignment_id: UUID) -> AssignmentRow:
    rows = await assignment_rows(session, only_ids=[assignment_id])
    if not rows:
        raise NotFoundError("Opdracht", assignment_id)
    return rows[0]


async def organisations(session: AsyncSession) -> list[Organisation]:
    result = await session.execute(
        select(Organisation).order_by(Organisation.name, Organisation.id)
    )
    return list(result.scalars())


async def person_options(session: AsyncSession) -> list[PersonOption]:
    """Active persons, for a picker; a prospective colleague with the start date."""
    from grip.models.person_standing import PersonStanding, Stage

    rows = await session.execute(
        select(Person.id, Person.name, PersonStanding.start_date)
        .outerjoin(
            PersonStanding,
            (PersonStanding.person_id == Person.id)
            & (PersonStanding.stage == Stage.prospective.value),
        )
        .where(Person.is_active.is_(True))
        .order_by(Person.name, Person.id)
    )
    return [PersonOption(row[0], row[1], row[2]) for row in rows]


async def direct_report_ids(session: AsyncSession, person_id: UUID) -> set[UUID]:
    rows = await session.execute(
        select(Person.id).where(Person.manager_id == person_id)
    )
    return {row[0] for row in rows}


async def managed_assignment_ids(session: AsyncSession, person_id: UUID) -> set[UUID]:
    """Assignments the person owns or manages."""
    rows = await session.execute(
        select(AssignmentRole.assignment_id).where(
            AssignmentRole.person_id == person_id
        )
    )
    return {row[0] for row in rows}


async def line_options(
    session: AsyncSession, *, only_assignment_ids: Iterable[UUID] | None = None
) -> list[LineOption]:
    """Personnel budget lines people can be put on, with their assignment."""
    stmt = (
        select(BudgetLine, Assignment.name)
        .join(Assignment, Assignment.id == BudgetLine.assignment_id)
        .where(
            BudgetLine.kind == "personnel",
            # No new inzet on an assignment that has ended.
            Assignment.status.notin_(statuses_in_phase(Phase.CLOSED)),
        )
        .order_by(Assignment.name, BudgetLine.position)
    )
    if only_assignment_ids is not None:
        ids = list(set(only_assignment_ids))
        if not ids:
            return []
        stmt = stmt.where(BudgetLine.assignment_id.in_(ids))
    rows = await session.execute(stmt)
    return [LineOption(line, line.assignment_id, name) for line, name in rows]


# -- pricing views ------------------------------------------------------------


def _allocation_views(
    allocations: Iterable[Allocation],
    lines: dict[UUID, BudgetLine],
    assignment_names: dict[UUID, str],
    person_names: dict[UUID, str],
    inputs: CalcInputs,
    options: PricingOptions,
    year: int | None,
    tentative_ids: frozenset[UUID] = frozenset(),
) -> list[AllocationView]:
    calc_allocations = {a.id: a for a in inputs.allocations}
    calc_lines = {line.id: line for line in inputs.lines}
    views: list[AllocationView] = []
    for allocation in allocations:
        line = lines[allocation.budget_line_id]
        calc_allocation = calc_allocations[str(allocation.id)]
        amount: int | None = None
        error: str | None = None
        mismatch: calc.CategoryMismatch | None = None
        try:
            amount = calc.allocation_amount(
                calc_allocation,
                inputs.rates,
                inputs.scales,
                partial_months=options.partial_months,
                actuals=inputs.actuals,
                year=year,
            )
            found = calc.category_mismatches(
                calc_lines[str(line.id)],
                [calc_allocation],
                inputs.rates,
                inputs.scales,
            )
            mismatch = found[0] if found else None
        except calc.CalcError as exc:
            error = describe_calc_error(exc, personal=True)
        views.append(
            AllocationView(
                allocation=allocation,
                person_name=person_names.get(allocation.person_id, ""),
                line=line,
                assignment_id=line.assignment_id,
                assignment_name=assignment_names.get(line.assignment_id, ""),
                amount_cents=amount,
                pricing_error=error,
                mismatch=mismatch,
                tentative=line.assignment_id in tentative_ids,
            )
        )
    return views


async def _person_names(session: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, str]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = await session.execute(
        select(Person.id, Person.name).where(Person.id.in_(wanted))
    )
    return {row[0]: row[1] for row in rows}


async def _tentative_ids(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> frozenset[UUID]:
    """The assignments among these that are still potential."""
    wanted = set(assignment_ids)
    if not wanted:
        return frozenset()
    rows = await session.execute(
        select(Assignment.id, Assignment.status).where(Assignment.id.in_(wanted))
    )
    return frozenset(row[0] for row in rows if is_tentative(row[1]))


async def assignment_statuses(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> dict[UUID, str]:
    wanted = set(assignment_ids)
    if not wanted:
        return {}
    rows = await session.execute(
        select(Assignment.id, Assignment.status).where(Assignment.id.in_(wanted))
    )
    return {row[0]: row[1] for row in rows}


async def _assignment_names(
    session: AsyncSession, ids: Iterable[UUID]
) -> dict[UUID, str]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = await session.execute(
        select(Assignment.id, Assignment.name).where(Assignment.id.in_(wanted))
    )
    return {row[0]: row[1] for row in rows}


async def allocation_views(
    session: AsyncSession,
    *,
    person_ids: Iterable[UUID] | None = None,
    assignment_ids: Iterable[UUID] | None = None,
    budget_line_id: UUID | None = None,
    year: int | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[AllocationView]:
    """Allocations with their amount and R14 signal.

    The filters narrow the result and are combined with AND; an empty
    collection gives an empty list. Without any filter every allocation is
    returned.
    """
    stmt = (
        select(Allocation)
        .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
        .order_by(Allocation.start_date, Allocation.id)
    )
    if person_ids is not None:
        ids = list(set(person_ids))
        if not ids:
            return []
        stmt = stmt.where(Allocation.person_id.in_(ids))
    if assignment_ids is not None:
        ids = list(set(assignment_ids))
        if not ids:
            return []
        stmt = stmt.where(BudgetLine.assignment_id.in_(ids))
    if budget_line_id is not None:
        stmt = stmt.where(Allocation.budget_line_id == budget_line_id)
    allocations = list((await session.execute(stmt)).scalars())
    if not allocations:
        return []
    line_list = await AssignmentRepository(session).budget_lines_by_id(
        {a.budget_line_id for a in allocations}
    )
    lines = {line.id: line for line in line_list}
    inputs = await load_inputs_for_lines(session, line_list, options=options)
    return _allocation_views(
        allocations,
        lines,
        await _assignment_names(session, {line.assignment_id for line in line_list}),
        await _person_names(session, {a.person_id for a in allocations}),
        inputs,
        options,
        year,
        await _tentative_ids(session, {line.assignment_id for line in line_list}),
    )


async def allocation_view(
    session: AsyncSession,
    allocation_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> AllocationView:
    allocation = await session.get(Allocation, allocation_id)
    if allocation is None:
        raise NotFoundError("Inzet", allocation_id)
    line_list = await AssignmentRepository(session).budget_lines_by_id(
        [allocation.budget_line_id]
    )
    inputs = await load_inputs_for_lines(session, line_list, options=options)
    return _allocation_views(
        [allocation],
        {line.id: line for line in line_list},
        await _assignment_names(session, {line.assignment_id for line in line_list}),
        await _person_names(session, {allocation.person_id}),
        inputs,
        options,
        None,
        await _tentative_ids(session, {line.assignment_id for line in line_list}),
    )[0]


def _coverage_views(
    line: BudgetLine,
    inputs: CalcInputs,
    descriptions: dict[str, str],
    options: PricingOptions,
    year: int | None,
) -> tuple[CoverageView, ...]:
    items = {item.id: item for item in inputs.cost_items}
    views: list[CoverageView] = []
    for coverage in inputs.coverages:
        if coverage.budget_line_id != str(line.id):
            continue
        invoice_lines = inputs.invoice_lines
        if year is not None and options.coverage_basis is calc.CoverageBasis.FORECAST:
            # Same rule as the pricing bridge: with a year filter a coverage
            # follows the invoice lines of that year.
            invoice_lines = tuple(
                i
                for i in inputs.invoice_lines
                if i.period is not None and i.period.year == year
            )
        try:
            amount: int | None = calc.coverage_amount(
                coverage,
                items[coverage.cost_item_id],
                invoice_lines,
                basis=options.coverage_basis,
            )
        except calc.CalcError:
            amount = None
        views.append(
            CoverageView(
                coverage_id=UUID(coverage.id),
                cost_item_id=UUID(coverage.cost_item_id),
                description=descriptions.get(coverage.cost_item_id, ""),
                pct=coverage.pct,
                amount_cents=amount,
            )
        )
    return tuple(views)


async def assignment_view(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    year: int | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> AssignmentView:
    """An assignment with its budget lines, and per line the team and the costs.

    ``year=None`` covers the whole period.
    """
    row = await assignment_row(session, assignment_id)
    line_list = await AssignmentRepository(session).budget_lines([assignment_id])
    inputs = await load_inputs_for_lines(session, line_list, options=options)
    lines = {line.id: line for line in line_list}

    allocations = await AssignmentRepository(session).allocations_on_lines(lines)
    allocation_list = _allocation_views(
        allocations,
        lines,
        {assignment_id: row.assignment.name},
        await _person_names(session, {a.person_id for a in allocations}),
        inputs,
        options,
        year,
        frozenset({assignment_id})
        if is_tentative(row.assignment.status)
        else frozenset(),
    )
    item_ids = [UUID(item.id) for item in inputs.cost_items]
    descriptions: dict[str, str] = {}
    if item_ids:
        rows = await session.execute(
            select(CostItem.id, CostItem.description).where(CostItem.id.in_(item_ids))
        )
        descriptions = {str(r[0]): r[1] for r in rows}

    calc_lines = {UUID(line.id): line for line in inputs.lines}
    line_views: list[LineView] = []
    first_error: str | None = None
    by_year: dict[int, int] = {}
    for line in line_list:
        overview: LineOverview | None = None
        line_by_year: dict[int, int] = {}
        error: str | None = None
        try:
            overview = overview_from_inputs(
                assignment_id,
                CalcInputs(
                    rates=inputs.rates,
                    scales=inputs.scales,
                    lines=(calc_lines[line.id],),
                    allocations=inputs.allocations,
                    cost_items=inputs.cost_items,
                    invoice_lines=inputs.invoice_lines,
                    coverages=inputs.coverages,
                    actuals=inputs.actuals,
                ),
                year=year,
                options=options,
            ).lines[0]
        except calc.CalcError as exc:
            error = describe_calc_error(exc)
            first_error = first_error or error
        try:
            line_by_year = calc.budgeted_by_year(
                calc_lines[line.id],
                inputs.rates,
                partial_months=options.partial_months,
            )
            for line_year, cents in line_by_year.items():
                by_year[line_year] = by_year.get(line_year, 0) + cents
        except calc.CalcError as exc:
            error = error or describe_calc_error(exc)
            first_error = first_error or error
        line_views.append(
            LineView(
                line=line,
                overview=overview,
                budgeted_by_year=dict(sorted(line_by_year.items())),
                pricing_error=error,
                allocations=tuple(
                    a for a in allocation_list if a.allocation.budget_line_id == line.id
                ),
                coverages=_coverage_views(line, inputs, descriptions, options, year),
            )
        )

    priced = [v.overview for v in line_views if v.overview is not None]
    return AssignmentView(
        row=row,
        year=year,
        lines=tuple(line_views),
        totals=Totals.of(priced) if len(priced) == len(line_views) else None,
        budgeted_by_year=dict(sorted(by_year.items())),
        pricing_error=first_error,
    )


async def budgeted_total(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> int | None:
    """The whole budget of an assignment; None when it cannot be priced."""
    line_list = await AssignmentRepository(session).budget_lines([assignment_id])
    inputs = await load_inputs_for_lines(session, line_list, options=options)
    try:
        return sum(
            calc.budgeted(line, inputs.rates, partial_months=options.partial_months)
            for line in inputs.lines
        )
    except calc.CalcError:
        return None
