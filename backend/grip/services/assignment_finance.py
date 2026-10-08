"""The financial read model of one assignment: what an analyst reads.

Every figure on the Financieel tab comes from here, so the screen never
computes money. The figures say what state the money is in:

- ``budgeted``: the budget (R4, R5).
- ``realised``: inzet of closed months, at the established percentage.
- ``planned``: inzet of open months, at the planned percentage.
- ``costs_realised`` and ``costs_forecast``: covered external costs (R7),
  split by whether the invoice lines behind them are actual or estimated.
- ``expected_total``: realised plus planned plus costs. This is what R9 calls
  ``used``: the estimate at completion.
- ``variance``: budgeted minus expected total. Positive is room, negative is
  an overrun.
- ``realised_pct``: the share of the budget already realised (inzet and
  costs), the uitputting.

Totals tie out by construction. An amount is rounded once, per calendar month
of one allocation and per coverage; a line is the integer sum of its detail
and the total the integer sum of its lines. Percentages are rounded to one
decimal, half up, here and nowhere else.

Nothing in this module decides who may see what; the route does.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import AmountSource, InvoiceLineKind, Month
from grip.core import clock
from grip.models.assignment import Allocation, BudgetLine
from grip.models.cost import CostItem
from grip.models.person import Person
from grip.models.quote import Quote
from grip.repositories.domain import AssignmentRepository, MonthCloseRepository
from grip.services import assignment_views as views
from grip.services.outgoing_invoices import billing_position
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    CalcInputs,
    PricingOptions,
    load_inputs_for_lines,
)

# A line with at least this share of its budget free is worth a look.
FREE_ROOM_THRESHOLD_PCT = Decimal("10")

_ONE_DECIMAL = Decimal("0.1")


def percentage(part: int, whole: int) -> Decimal | None:
    """``part`` as a percentage of ``whole``, one decimal; None without a whole."""
    if whole == 0:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(
        _ONE_DECIMAL, rounding=ROUND_HALF_UP
    )


@dataclass(frozen=True)
class Figures:
    budgeted_cents: int = 0
    realised_cents: int = 0
    planned_cents: int = 0
    costs_realised_cents: int = 0
    costs_forecast_cents: int = 0

    @property
    def costs_cents(self) -> int:
        return self.costs_realised_cents + self.costs_forecast_cents

    @property
    def expected_total_cents(self) -> int:
        return self.realised_cents + self.planned_cents + self.costs_cents

    @property
    def variance_cents(self) -> int:
        return self.budgeted_cents - self.expected_total_cents

    @property
    def variance_pct(self) -> Decimal | None:
        return percentage(self.variance_cents, self.budgeted_cents)

    @property
    def overrun(self) -> bool:
        return self.variance_cents < 0

    @property
    def realised_total_cents(self) -> int:
        return self.realised_cents + self.costs_realised_cents

    @property
    def realised_pct(self) -> Decimal | None:
        return percentage(self.realised_total_cents, self.budgeted_cents)

    @classmethod
    def sum(cls, items: Iterable[Figures]) -> Figures:
        items = list(items)
        return cls(
            budgeted_cents=sum(i.budgeted_cents for i in items),
            realised_cents=sum(i.realised_cents for i in items),
            planned_cents=sum(i.planned_cents for i in items),
            costs_realised_cents=sum(i.costs_realised_cents for i in items),
            costs_forecast_cents=sum(i.costs_forecast_cents for i in items),
        )


@dataclass(frozen=True)
class PersonAmount:
    allocation_id: UUID
    person_id: UUID
    person_name: str
    start_date: date
    end_date: date
    realised_cents: int
    planned_cents: int
    category_mismatch: bool

    @property
    def total_cents(self) -> int:
        return self.realised_cents + self.planned_cents


@dataclass(frozen=True)
class CostAmount:
    cost_item_id: UUID
    description: str
    pct: Decimal
    realised_cents: int
    forecast_cents: int

    @property
    def total_cents(self) -> int:
        return self.realised_cents + self.forecast_cents


@dataclass(frozen=True)
class FinanceLine:
    line: BudgetLine
    # None when the line could not be priced; see ``pricing_error``.
    figures: Figures | None
    pricing_error: str | None
    persons: tuple[PersonAmount, ...]
    costs: tuple[CostAmount, ...]


@dataclass(frozen=True)
class MonthRow:
    """Inzet of one calendar month, over the personnel lines."""

    month: date
    closed: bool
    budgeted_cents: int
    # At the planned percentage, whether the month is closed or not.
    planned_cents: int
    # None while the month is open.
    realised_cents: int | None
    cumulative_budgeted_cents: int
    # Realised of closed months so far.
    cumulative_realised_cents: int
    # Planned of open months so far; on top of the realised it is the
    # expected inzet up to and including this month.
    cumulative_planned_open_cents: int

    @property
    def cumulative_expected_cents(self) -> int:
        return self.cumulative_realised_cents + self.cumulative_planned_open_cents

    @property
    def cumulative_variance_cents(self) -> int:
        return self.cumulative_budgeted_cents - self.cumulative_expected_cents


@dataclass(frozen=True)
class Signal:
    """Something an analyst wants called out above the table."""

    kind: str
    budget_line_id: UUID | None = None
    description: str | None = None
    amount_cents: int | None = None
    pct: Decimal | None = None
    count: int | None = None
    months: tuple[date, ...] = ()


@dataclass(frozen=True)
class KeyFigures:
    """Whole period, whatever the year filter says."""

    # Total of the accepted quote; None without one.
    agreed_cents: int | None
    budgeted_cents: int | None
    expected_total_cents: int | None
    # Realised inzet of closed months.
    realised_cents: int | None
    realised_pct: Decimal | None
    # Aangeleverd: billing data exported for the financial administration,
    # the delivery in force of each closed month.
    delivered_cents: int
    # Gefactureerd: only what someone recorded as actually invoiced.
    invoiced_cents: int
    # Nog aan te leveren: established inzet of closed months, priced, minus
    # what was delivered. None when a closed month cannot be priced.
    to_deliver_cents: int | None

    @property
    def agreed_minus_budgeted_cents(self) -> int | None:
        if self.agreed_cents is None or self.budgeted_cents is None:
            return None
        return self.agreed_cents - self.budgeted_cents

    @property
    def budgeted_minus_expected_cents(self) -> int | None:
        if self.budgeted_cents is None or self.expected_total_cents is None:
            return None
        return self.budgeted_cents - self.expected_total_cents

    @property
    def to_invoice_cents(self) -> int:
        """Nog te factureren: delivered, and no invoice recorded for it."""
        return self.delivered_cents - self.invoiced_cents


@dataclass(frozen=True)
class AssignmentFinance:
    row: views.AssignmentRow
    # None means the whole period.
    year: int | None
    # First day of the last closed month; None when no month is closed.
    reference_month: date | None
    key_figures: KeyFigures
    lines: tuple[FinanceLine, ...]
    # None when at least one line could not be priced.
    totals: Figures | None
    months: tuple[MonthRow, ...]
    # Fixed lines and costs are not in the monthly rows; this says how much
    # budget that leaves out, so the reader can tie the two tables.
    budgeted_outside_months_cents: int
    signals: tuple[Signal, ...]
    pricing_error: str | None
    free_room_threshold_pct: Decimal = field(default=FREE_ROOM_THRESHOLD_PCT)


# -- building blocks ----------------------------------------------------------


def _in_year(month: Month, year: int | None) -> bool:
    return year is None or month.year == year


def _person_amounts(
    line: BudgetLine,
    allocations: Iterable[Allocation],
    names: dict[UUID, str],
    inputs: CalcInputs,
    options: PricingOptions,
    year: int | None,
) -> tuple[PersonAmount, ...]:
    calc_allocations = {a.id: a for a in inputs.allocations}
    calc_line = next(c for c in inputs.lines if c.id == str(line.id))
    result: list[PersonAmount] = []
    for allocation in allocations:
        if allocation.budget_line_id != line.id:
            continue
        calc_allocation = calc_allocations[str(allocation.id)]
        realised = planned = 0
        for amount in calc.allocation_months(
            calc_allocation,
            inputs.rates,
            inputs.scales,
            partial_months=options.partial_months,
            actuals=inputs.actuals,
        ):
            if not _in_year(amount.month, year):
                continue
            if amount.source is AmountSource.ACTUAL:
                realised += amount.cents
            else:
                planned += amount.cents
        mismatch = bool(
            calc.category_mismatches(
                calc_line, [calc_allocation], inputs.rates, inputs.scales
            )
        )
        result.append(
            PersonAmount(
                allocation_id=allocation.id,
                person_id=allocation.person_id,
                person_name=names.get(allocation.person_id, ""),
                start_date=allocation.start_date,
                end_date=allocation.end_date,
                realised_cents=realised,
                planned_cents=planned,
                category_mismatch=mismatch,
            )
        )
    return tuple(result)


def _cost_amounts(
    line: BudgetLine,
    inputs: CalcInputs,
    descriptions: dict[str, str],
    options: PricingOptions,
    year: int | None,
) -> tuple[CostAmount, ...]:
    items = {item.id: item for item in inputs.cost_items}
    result: list[CostAmount] = []
    for coverage in inputs.coverages:
        if coverage.budget_line_id != str(line.id):
            continue
        invoice_lines = inputs.invoice_lines
        if year is not None and options.coverage_basis is calc.CoverageBasis.FORECAST:
            invoice_lines = tuple(
                i
                for i in invoice_lines
                if i.period is not None and i.period.year == year
            )
        item = items[coverage.cost_item_id]
        total = calc.coverage_amount(
            coverage, item, invoice_lines, basis=options.coverage_basis
        )
        # The realised part is the coverage of the actual invoice lines; the
        # forecast is the remainder, so the two always add up to the total.
        realised = calc.coverage_amount(
            coverage,
            item,
            tuple(i for i in invoice_lines if i.kind is InvoiceLineKind.ACTUAL),
            basis=calc.CoverageBasis.FORECAST,
        )
        result.append(
            CostAmount(
                cost_item_id=UUID(coverage.cost_item_id),
                description=descriptions.get(coverage.cost_item_id, ""),
                pct=Decimal(coverage.pct),
                realised_cents=realised,
                forecast_cents=total - realised,
            )
        )
    return tuple(result)


def _finance_line(
    line: BudgetLine,
    allocations: list[Allocation],
    names: dict[UUID, str],
    descriptions: dict[str, str],
    inputs: CalcInputs,
    options: PricingOptions,
    year: int | None,
) -> FinanceLine:
    calc_line = next(c for c in inputs.lines if c.id == str(line.id))
    try:
        persons = _person_amounts(line, allocations, names, inputs, options, year)
        costs = _cost_amounts(line, inputs, descriptions, options, year)
        figures = Figures(
            budgeted_cents=calc.budgeted(
                calc_line,
                inputs.rates,
                partial_months=options.partial_months,
                year=year,
            ),
            realised_cents=sum(p.realised_cents for p in persons),
            planned_cents=sum(p.planned_cents for p in persons),
            costs_realised_cents=sum(c.realised_cents for c in costs),
            costs_forecast_cents=sum(c.forecast_cents for c in costs),
        )
    except calc.CalcError as exc:
        return FinanceLine(line, None, views.describe_calc_error(exc), (), ())
    return FinanceLine(line, figures, None, persons, costs)


def _month_rows(
    inputs: CalcInputs,
    options: PricingOptions,
    closed: set[date],
    year: int | None,
) -> tuple[MonthRow, ...]:
    """Budget, planned and realised inzet per month over the personnel lines.

    Lines that cannot be priced are left out; the caller reports them.
    """
    budgeted: dict[Month, int] = {}
    planned: dict[Month, int] = {}
    realised: dict[Month, int] = {}
    priced_line_ids: set[str] = set()
    for calc_line in inputs.lines:
        try:
            months = calc.budget_line_months(
                calc_line, inputs.rates, partial_months=options.partial_months
            )
        except calc.CalcError:
            continue
        priced_line_ids.add(calc_line.id)
        for amount in months:
            budgeted[amount.month] = budgeted.get(amount.month, 0) + amount.cents
    for allocation in inputs.allocations:
        if allocation.budget_line_id not in priced_line_ids:
            continue
        try:
            plan = calc.allocation_months(
                allocation,
                inputs.rates,
                inputs.scales,
                partial_months=options.partial_months,
            )
            actual = calc.allocation_months(
                allocation,
                inputs.rates,
                inputs.scales,
                partial_months=options.partial_months,
                actuals=inputs.actuals,
            )
        except calc.CalcError:
            continue
        for amount in plan:
            planned[amount.month] = planned.get(amount.month, 0) + amount.cents
        for amount in actual:
            if amount.source is AmountSource.ACTUAL:
                realised[amount.month] = realised.get(amount.month, 0) + amount.cents

    months = sorted(m for m in set(budgeted) | set(planned) if _in_year(m, year))
    rows: list[MonthRow] = []
    cum_budget = cum_realised = cum_open = 0
    for month in months:
        first_day = date(month.year, month.month, 1)
        is_closed = first_day in closed
        month_planned = planned.get(month, 0)
        month_realised = realised.get(month, 0) if is_closed else None
        cum_budget += budgeted.get(month, 0)
        if is_closed:
            cum_realised += month_realised or 0
        else:
            cum_open += month_planned
        rows.append(
            MonthRow(
                month=first_day,
                closed=is_closed,
                budgeted_cents=budgeted.get(month, 0),
                planned_cents=month_planned,
                realised_cents=month_realised,
                cumulative_budgeted_cents=cum_budget,
                cumulative_realised_cents=cum_realised,
                cumulative_planned_open_cents=cum_open,
            )
        )
    return tuple(rows)


def _overdue_months(
    inputs: CalcInputs, closed: set[date], today: date
) -> tuple[date, ...]:
    """Months before the current one with inzet that are not closed."""
    this_month = date(today.year, today.month, 1)
    with_inzet: set[date] = set()
    for allocation in inputs.allocations:
        month = Month.of(allocation.start_date)
        last = Month.of(allocation.end_date)
        while month <= last:
            with_inzet.add(date(month.year, month.month, 1))
            month = month.next()
    return tuple(sorted(m for m in with_inzet if m < this_month and m not in closed))


def _signals(
    lines: Iterable[FinanceLine],
    overdue: tuple[date, ...],
) -> tuple[Signal, ...]:
    signals: list[Signal] = []
    lines = list(lines)
    for item in lines:
        figures = item.figures
        if figures is None:
            continue
        if figures.overrun:
            signals.append(
                Signal(
                    kind="overrun",
                    budget_line_id=item.line.id,
                    description=item.line.description,
                    amount_cents=-figures.variance_cents,
                    pct=-figures.variance_pct
                    if figures.variance_pct is not None
                    else None,
                )
            )
    for item in lines:
        figures = item.figures
        if figures is None or figures.variance_pct is None:
            continue
        if (
            figures.variance_cents > 0
            and figures.variance_pct >= FREE_ROOM_THRESHOLD_PCT
        ):
            signals.append(
                Signal(
                    kind="free_room",
                    budget_line_id=item.line.id,
                    description=item.line.description,
                    amount_cents=figures.variance_cents,
                    pct=figures.variance_pct,
                )
            )
    mismatches = sum(1 for item in lines for p in item.persons if p.category_mismatch)
    if mismatches:
        signals.append(Signal(kind="rate_mismatch", count=mismatches))
    if overdue:
        signals.append(
            Signal(kind="months_not_closed", count=len(overdue), months=overdue)
        )
    unpriced = [item for item in lines if item.figures is None]
    if unpriced:
        signals.append(
            Signal(
                kind="not_priced",
                count=len(unpriced),
                description=unpriced[0].pricing_error,
            )
        )
    return tuple(signals)


async def _agreed(session: AsyncSession, assignment_id: UUID) -> int | None:
    """Total of the accepted quote; the latest if there are several."""
    result = await session.execute(
        select(Quote.total_cents)
        .where(Quote.assignment_id == assignment_id, Quote.status == "accepted")
        .order_by(Quote.issued_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# -- the read model -----------------------------------------------------------


async def assignment_finance(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    year: int | None = None,
    today: date | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> AssignmentFinance:
    """The financial state of an assignment, for a year or the whole period."""
    row = await views.assignment_row(session, assignment_id)
    repo = AssignmentRepository(session)
    line_list = await repo.budget_lines([assignment_id])
    inputs = await load_inputs_for_lines(session, line_list, options=options)
    allocations = await repo.allocations_on_lines([line.id for line in line_list])

    names: dict[UUID, str] = {}
    person_ids = {a.person_id for a in allocations}
    if person_ids:
        rows = await session.execute(
            select(Person.id, Person.name).where(Person.id.in_(person_ids))
        )
        names = {r[0]: r[1] for r in rows}
    descriptions: dict[str, str] = {}
    item_ids = [UUID(item.id) for item in inputs.cost_items]
    if item_ids:
        rows = await session.execute(
            select(CostItem.id, CostItem.description).where(CostItem.id.in_(item_ids))
        )
        descriptions = {str(r[0]): r[1] for r in rows}

    closed = set(await MonthCloseRepository(session).closed_months(assignment_id))

    def build(for_year: int | None) -> tuple[FinanceLine, ...]:
        return tuple(
            _finance_line(
                line, allocations, names, descriptions, inputs, options, for_year
            )
            for line in line_list
        )

    lines = build(year)
    whole = lines if year is None else build(None)
    priced = [item.figures for item in lines if item.figures is not None]
    totals = Figures.sum(priced) if len(priced) == len(lines) else None
    whole_priced = [item.figures for item in whole if item.figures is not None]
    whole_totals = (
        Figures.sum(whole_priced) if len(whole_priced) == len(whole) else None
    )

    months = _month_rows(inputs, options, closed, year)
    in_months = sum(m.budgeted_cents for m in months)
    first_error = next((i.pricing_error for i in lines if i.pricing_error), None)

    # Delivered and invoiced are facts of the whole period, like the other
    # key figures.
    position = await billing_position(session, assignment_id, options=options)

    return AssignmentFinance(
        row=row,
        year=year,
        reference_month=max(closed) if closed else None,
        key_figures=KeyFigures(
            agreed_cents=await _agreed(session, assignment_id),
            budgeted_cents=whole_totals.budgeted_cents if whole_totals else None,
            expected_total_cents=whole_totals.expected_total_cents
            if whole_totals
            else None,
            realised_cents=whole_totals.realised_cents if whole_totals else None,
            realised_pct=whole_totals.realised_pct if whole_totals else None,
            delivered_cents=position.delivered_cents,
            invoiced_cents=position.invoiced_cents,
            to_deliver_cents=position.to_deliver_cents,
        ),
        lines=lines,
        totals=totals,
        months=months,
        budgeted_outside_months_cents=(totals.budgeted_cents - in_months)
        if totals is not None
        else 0,
        signals=_signals(
            lines, _overdue_months(inputs, closed, today or clock.today())
        ),
        pricing_error=first_error,
    )


# -- CSV ----------------------------------------------------------------------

LINE_CSV_COLUMNS = (
    "assignment_uri",
    "period",
    "reference_month",
    "budget_line_id",
    "description",
    "kind",
    "budgeted",
    "realised",
    "planned",
    "costs_realised",
    "costs_forecast",
    "expected_total",
    "variance",
    "variance_pct",
    "realised_pct",
    "currency",
)

MONTH_CSV_COLUMNS = (
    "assignment_uri",
    "month",
    "closed",
    "budgeted",
    "planned",
    "realised",
    "cumulative_budgeted",
    "cumulative_realised",
    "cumulative_planned_open",
    "cumulative_expected",
    "cumulative_variance",
    "currency",
)


def _euros(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _safe_cell(value: str | None) -> str:
    """Keep a spreadsheet from reading a cell as a formula."""
    text = value or ""
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _pct(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _figure_cells(figures: Figures | None) -> list[str]:
    if figures is None:
        return [""] * 9
    return [
        _euros(figures.budgeted_cents),
        _euros(figures.realised_cents),
        _euros(figures.planned_cents),
        _euros(figures.costs_realised_cents),
        _euros(figures.costs_forecast_cents),
        _euros(figures.expected_total_cents),
        _euros(figures.variance_cents),
        _pct(figures.variance_pct),
        _pct(figures.realised_pct),
    ]


def lines_csv(finance: AssignmentFinance) -> str:
    """The table per budget line, with a last row ``total``. No persons."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(LINE_CSV_COLUMNS)
    uri = finance.row.assignment.uri
    period = "all" if finance.year is None else str(finance.year)
    reference = (
        finance.reference_month.strftime("%Y-%m") if finance.reference_month else ""
    )
    for item in finance.lines:
        writer.writerow(
            [
                uri,
                period,
                reference,
                str(item.line.id),
                _safe_cell(item.line.description),
                item.line.kind,
                *_figure_cells(item.figures),
                "EUR",
            ]
        )
    writer.writerow(
        [uri, period, reference, "", "total", "", *_figure_cells(finance.totals), "EUR"]
    )
    return buffer.getvalue()


def months_csv(finance: AssignmentFinance) -> str:
    """The inzet per month, as on the tab."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(MONTH_CSV_COLUMNS)
    uri = finance.row.assignment.uri
    for month in finance.months:
        writer.writerow(
            [
                uri,
                month.month.strftime("%Y-%m"),
                "true" if month.closed else "false",
                _euros(month.budgeted_cents),
                _euros(month.planned_cents),
                _euros(month.realised_cents),
                _euros(month.cumulative_budgeted_cents),
                _euros(month.cumulative_realised_cents),
                _euros(month.cumulative_planned_open_cents),
                _euros(month.cumulative_expected_cents),
                _euros(month.cumulative_variance_cents),
                "EUR",
            ]
        )
    return buffer.getvalue()


# -- a budget line before it is saved -----------------------------------------


@dataclass(frozen=True)
class LinePreview:
    # None when the line cannot be priced yet; ``reason`` then says why.
    budgeted_cents: int | None
    budgeted_by_year: dict[int, int]
    reason: str | None


def _missing_text(missing: list[str]) -> str:
    # What still has to be filled in before the line can be priced.
    if len(missing) == 1:
        return f"Nog niet te berekenen: {missing[0]} ontbreekt."
    listed = ", ".join(missing[:-1]) + " en " + missing[-1]
    return f"Nog niet te berekenen: {listed} ontbreken."


async def preview_budget_line(
    session: AsyncSession,
    *,
    kind: str,
    fte: Decimal | None = None,
    rate_category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    amount_cents: int | None = None,
    year: int | None = None,
    period_name: str = "de periode",
    options: PricingOptions = DEFAULT_OPTIONS,
) -> LinePreview:
    """What a line with these values would be budgeted at. Saves nothing.

    The same calculation as for a saved line (R4, R5). Without an amount the
    reason always says what is missing.
    """
    from grip.services.pricing import load_rate_book

    if kind == "fixed":
        missing = [
            name
            for name, value in (("het bedrag", amount_cents), ("het jaar", year))
            if value is None
        ]
        if amount_cents is None or year is None:
            return LinePreview(None, {}, _missing_text(missing))
        return LinePreview(amount_cents, {year: amount_cents}, None)
    missing = [
        name
        for name, value in (
            ("de omvang", fte),
            ("de schaal", rate_category),
            (period_name, start_date and end_date),
        )
        if not value
    ]
    if not (fte and rate_category and start_date and end_date):
        return LinePreview(None, {}, _missing_text(missing))
    if end_date < start_date:
        return LinePreview(None, {}, "De einddatum ligt voor de begindatum.")
    line = calc.BudgetLine(
        id="preview",
        assignment_id="preview",
        kind=calc.BudgetLineKind.PERSONNEL,
        fte=fte,
        rate_category=rate_category,
        start_date=start_date,
        end_date=end_date,
    )
    rates = await load_rate_book(session, include_draft=options.include_draft)
    try:
        by_year = calc.budgeted_by_year(
            line, rates, partial_months=options.partial_months
        )
    except calc.CalcError as exc:
        return LinePreview(None, {}, views.describe_calc_error(exc))
    return LinePreview(sum(by_year.values()), dict(sorted(by_year.items())), None)
