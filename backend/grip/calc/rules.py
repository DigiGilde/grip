"""Calculation rules R1 to R14.

Pure functions: no database, no HTTP, standard library only. Nothing else in
grip may implement one of these rules again.

Rounding. Arithmetic is exact (Fraction). An amount is rounded to cents at
the smallest total that is recorded: one calendar month of an allocation or
a personnel budget line, one coverage amount, one KPI target. Every larger
total is an integer sum of those, so months add up to years and years to the
whole period. The mode is half away from zero (commercial rounding).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

from grip.calc.periods import (
    Month,
    PartialMonths,
    month_fractions,
    months_between,
    months_of_year,
    overlap,
)
from grip.calc.types import (
    Allocation,
    AmountSource,
    AssignmentTotals,
    BillabilityTarget,
    BillingLine,
    BudgetLine,
    BudgetLineKind,
    BudgetLineStatus,
    CategoryMismatch,
    CostCoverage,
    CostItem,
    CostItemCoverage,
    CoverageBasis,
    CoverageExceededError,
    InvalidInputError,
    InvoiceLine,
    MismatchDirection,
    MissingPeriodError,
    MissingPersonScaleError,
    MonthAmount,
    PersonScale,
    RateBook,
)

# Established actual FTE percentage per (allocation id, month), set at the
# monthly close. It overrides the planned percentage for that month.
Actuals = Mapping[tuple[str, Month], Decimal]

_HUNDRED = Fraction(100)


def _exact(value: Decimal | int | Fraction) -> Fraction:
    if isinstance(value, float):
        raise InvalidInputError("floats are not allowed in amounts or percentages")
    return Fraction(value)


def round_cents(value: Fraction) -> int:
    """Round an exact amount in cents, half away from zero."""
    sign = -1 if value < 0 else 1
    magnitude = abs(value)
    return sign * (
        (2 * magnitude.numerator + magnitude.denominator) // (2 * magnitude.denominator)
    )


def subtotals_by_year(months: Iterable[MonthAmount]) -> dict[int, int]:
    totals: dict[int, int] = {}
    for amount in months:
        totals[amount.month.year] = totals.get(amount.month.year, 0) + amount.cents
    return dict(sorted(totals.items()))


# R1


def billing_scale(
    scales: Iterable[PersonScale], person_id: str, start: date, end: date
) -> int | None:
    """Billing scale for the inclusive period: the one valid on `start`, or
    else the earliest one that becomes valid within the period."""
    own = sorted(
        (s for s in scales if s.person_id == person_id), key=lambda s: s.valid_from
    )
    for scale in own:
        if scale.valid_from <= start and (
            scale.valid_to is None or scale.valid_to >= start
        ):
            return scale.billing_scale
    for scale in own:
        if start < scale.valid_from <= end:
            return scale.billing_scale
    return None


def rate_category(
    rates: RateBook,
    scales: Iterable[PersonScale],
    person_id: str,
    month: Month,
    *,
    start: date | None = None,
    end: date | None = None,
) -> str:
    """Rate category of a person in a month, optionally for part of it."""
    first = start or month.first_day
    last = end or month.last_day
    scale = billing_scale(scales, person_id, first, last)
    if scale is None:
        raise MissingPersonScaleError(person_id, first)
    return rates.category_for_scale(month.year, scale)


def person_monthly_rate(
    rates: RateBook, scales: Iterable[PersonScale], person_id: str, month: Month
) -> int:
    """R1: monthly rate in cents of a person in a month."""
    category = rate_category(rates, scales, person_id, month)
    return rates.monthly_rate_cents(month.year, category)


# R2, R3


def _month_amount(
    month: Month,
    fte_pct: Decimal,
    fraction: Fraction,
    category: str,
    rate_cents: int,
    source: AmountSource,
) -> MonthAmount:
    exact = _exact(fte_pct) / _HUNDRED * rate_cents * fraction
    return MonthAmount(
        month=month,
        fte_pct=fte_pct,
        fraction=fraction,
        category=category,
        monthly_rate_cents=rate_cents,
        exact=exact,
        cents=round_cents(exact),
        source=source,
    )


def allocation_months(
    allocation: Allocation,
    rates: RateBook,
    scales: Iterable[PersonScale],
    *,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
    actuals: Actuals | None = None,
) -> tuple[MonthAmount, ...]:
    """R2: amount per calendar month of an allocation.

    A month with an established actual percentage uses that percentage over
    the whole month (fraction 1); other months use the planned percentage and
    the month fraction of the chosen strategy.
    """
    scales = tuple(scales)
    planned = dict(
        month_fractions(allocation.start_date, allocation.end_date, partial_months)
    )
    amounts = []
    for month in months_between(allocation.start_date, allocation.end_date):
        actual = actuals.get((allocation.id, month)) if actuals else None
        if actual is None and month not in planned:
            continue
        first, last = overlap(month, allocation.start_date, allocation.end_date)  # type: ignore[misc]
        category = rate_category(
            rates, scales, allocation.person_id, month, start=first, end=last
        )
        rate_cents = rates.monthly_rate_cents(month.year, category)
        if actual is not None:
            amounts.append(
                _month_amount(
                    month,
                    actual,
                    Fraction(1),
                    category,
                    rate_cents,
                    AmountSource.ACTUAL,
                )
            )
        else:
            amounts.append(
                _month_amount(
                    month,
                    allocation.fte_pct,
                    planned[month],
                    category,
                    rate_cents,
                    AmountSource.PLANNED,
                )
            )
    return tuple(amounts)


def allocation_amount(
    allocation: Allocation,
    rates: RateBook,
    scales: Iterable[PersonScale],
    *,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
    actuals: Actuals | None = None,
    year: int | None = None,
) -> int:
    """R3: allocation amount in cents, for the whole period or one year."""
    months = allocation_months(
        allocation, rates, scales, partial_months=partial_months, actuals=actuals
    )
    return sum(m.cents for m in months if year is None or m.month.year == year)


# R4, R5


def _require_personnel(line: BudgetLine) -> tuple[Decimal, str, date, date]:
    if (
        line.fte is not None
        and line.rate_category is not None
        and line.start_date is None
        and line.end_date is None
    ):
        raise MissingPeriodError(line.id)
    if (
        line.fte is None
        or line.rate_category is None
        or line.start_date is None
        or line.end_date is None
    ):
        raise InvalidInputError(
            f"personnel budget line {line.id} needs fte, rate_category, "
            "start_date and end_date"
        )
    return line.fte, line.rate_category, line.start_date, line.end_date


def budget_line_months(
    line: BudgetLine,
    rates: RateBook,
    *,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
) -> tuple[MonthAmount, ...]:
    """Budgeted amount per month of a personnel line; empty for a fixed line."""
    if line.kind is BudgetLineKind.FIXED:
        return ()
    fte, category, start, end = _require_personnel(line)
    fte_pct = fte * 100
    return tuple(
        _month_amount(
            month,
            fte_pct,
            fraction,
            category,
            rates.monthly_rate_cents(month.year, category),
            AmountSource.PLANNED,
        )
        for month, fraction in month_fractions(start, end, partial_months)
    )


def budgeted_by_year(
    line: BudgetLine,
    rates: RateBook,
    *,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
) -> dict[int, int]:
    if line.kind is BudgetLineKind.FIXED:
        if line.amount_cents is None or line.year is None:
            raise InvalidInputError(
                f"fixed budget line {line.id} needs amount_cents and year"
            )
        return {line.year: line.amount_cents}
    return subtotals_by_year(
        budget_line_months(line, rates, partial_months=partial_months)
    )


def budgeted(
    line: BudgetLine,
    rates: RateBook,
    *,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
    year: int | None = None,
) -> int:
    """R4 (personnel) and R5 (fixed): budgeted amount in cents."""
    by_year = budgeted_by_year(line, rates, partial_months=partial_months)
    if year is not None:
        return by_year.get(year, 0)
    return sum(by_year.values())


# R6, R7, R8


def forecast(
    cost_item: CostItem,
    invoice_lines: Iterable[InvoiceLine],
    *,
    year: int | None = None,
) -> int:
    """R6: forecast of a cost item, the sum of its actual and estimate lines.

    With a year, only lines whose period falls in that year count.
    """
    return sum(
        line.amount_cents
        for line in invoice_lines
        if line.cost_item_id == cost_item.id
        and (year is None or (line.period is not None and line.period.year == year))
    )


def _coverage_basis(
    cost_item: CostItem, invoice_lines: Iterable[InvoiceLine], basis: CoverageBasis
) -> int:
    if basis is CoverageBasis.BUDGETED:
        return cost_item.budgeted_cents
    return forecast(cost_item, invoice_lines)


def coverage_amount(
    coverage: CostCoverage,
    cost_item: CostItem,
    invoice_lines: Iterable[InvoiceLine],
    *,
    basis: CoverageBasis = CoverageBasis.FORECAST,
) -> int:
    """R7: amount in cents that a coverage puts on its budget line."""
    if coverage.cost_item_id != cost_item.id:
        raise InvalidInputError(
            f"coverage {coverage.id} does not belong to cost item {cost_item.id}"
        )
    pct = _exact(coverage.pct)
    if pct < 0:
        raise InvalidInputError(f"coverage {coverage.id} has a negative percentage")
    return round_cents(
        pct / _HUNDRED * _coverage_basis(cost_item, invoice_lines, basis)
    )


def cost_item_coverage(
    cost_item: CostItem,
    invoice_lines: Iterable[InvoiceLine],
    coverages: Iterable[CostCoverage],
    *,
    basis: CoverageBasis = CoverageBasis.FORECAST,
) -> CostItemCoverage:
    """R8: covered amount and uncovered remainder of a cost item.

    Raises CoverageExceededError when the percentages add up to more than 100.
    """
    invoice_lines = tuple(invoice_lines)
    own = [c for c in coverages if c.cost_item_id == cost_item.id]
    pct_total = sum((c.pct for c in own), Decimal(0))
    if pct_total > 100:
        raise CoverageExceededError(cost_item.id, pct_total)
    basis_cents = _coverage_basis(cost_item, invoice_lines, basis)
    covered = sum(
        coverage_amount(c, cost_item, invoice_lines, basis=basis) for c in own
    )
    return CostItemCoverage(
        cost_item_id=cost_item.id,
        basis_cents=basis_cents,
        pct_total=pct_total,
        covered_cents=covered,
        uncovered_cents=basis_cents - covered,
    )


# R9, R10, R11


def used(
    line: BudgetLine,
    *,
    allocations: Iterable[Allocation],
    coverages: Iterable[CostCoverage],
    cost_items: Iterable[CostItem],
    invoice_lines: Iterable[InvoiceLine],
    rates: RateBook,
    scales: Iterable[PersonScale],
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
    coverage_basis: CoverageBasis = CoverageBasis.FORECAST,
    actuals: Actuals | None = None,
) -> int:
    """R9: allocation amounts plus coverage amounts on a budget line."""
    scales = tuple(scales)
    invoice_lines = tuple(invoice_lines)
    items = {item.id: item for item in cost_items}
    total = sum(
        allocation_amount(
            a, rates, scales, partial_months=partial_months, actuals=actuals
        )
        for a in allocations
        if a.budget_line_id == line.id
    )
    for coverage in coverages:
        if coverage.budget_line_id != line.id:
            continue
        if coverage.cost_item_id not in items:
            raise InvalidInputError(
                f"coverage {coverage.id} refers to unknown cost item "
                f"{coverage.cost_item_id}"
            )
        total += coverage_amount(
            coverage, items[coverage.cost_item_id], invoice_lines, basis=coverage_basis
        )
    return total


def budget_line_status(
    line: BudgetLine,
    *,
    allocations: Iterable[Allocation],
    coverages: Iterable[CostCoverage],
    cost_items: Iterable[CostItem],
    invoice_lines: Iterable[InvoiceLine],
    rates: RateBook,
    scales: Iterable[PersonScale],
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
    coverage_basis: CoverageBasis = CoverageBasis.FORECAST,
    actuals: Actuals | None = None,
) -> BudgetLineStatus:
    """R10: budgeted, used and available; a negative available is an overrun."""
    budgeted_cents = budgeted(line, rates, partial_months=partial_months)
    used_cents = used(
        line,
        allocations=allocations,
        coverages=coverages,
        cost_items=cost_items,
        invoice_lines=invoice_lines,
        rates=rates,
        scales=scales,
        partial_months=partial_months,
        coverage_basis=coverage_basis,
        actuals=actuals,
    )
    return BudgetLineStatus(
        budget_line_id=line.id,
        budgeted_cents=budgeted_cents,
        used_cents=used_cents,
        available_cents=budgeted_cents - used_cents,
    )


def assignment_totals(
    assignment_id: str,
    lines: Iterable[BudgetLine],
    *,
    allocations: Iterable[Allocation],
    coverages: Iterable[CostCoverage],
    cost_items: Iterable[CostItem],
    invoice_lines: Iterable[InvoiceLine],
    rates: RateBook,
    scales: Iterable[PersonScale],
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
    coverage_basis: CoverageBasis = CoverageBasis.FORECAST,
    actuals: Actuals | None = None,
) -> AssignmentTotals:
    """R11: totals of an assignment, the sum over its budget lines."""
    allocations = tuple(allocations)
    coverages = tuple(coverages)
    cost_items = tuple(cost_items)
    invoice_lines = tuple(invoice_lines)
    scales = tuple(scales)
    statuses = tuple(
        budget_line_status(
            line,
            allocations=allocations,
            coverages=coverages,
            cost_items=cost_items,
            invoice_lines=invoice_lines,
            rates=rates,
            scales=scales,
            partial_months=partial_months,
            coverage_basis=coverage_basis,
            actuals=actuals,
        )
        for line in lines
        if line.assignment_id == assignment_id
    )
    budgeted_cents = sum(s.budgeted_cents for s in statuses)
    used_cents = sum(s.used_cents for s in statuses)
    return AssignmentTotals(
        assignment_id=assignment_id,
        budgeted_cents=budgeted_cents,
        used_cents=used_cents,
        available_cents=budgeted_cents - used_cents,
        lines=statuses,
    )


# R12, R13


def kpi_realisation(
    person_id: str,
    year: int,
    allocations: Iterable[Allocation],
    rates: RateBook,
    scales: Iterable[PersonScale],
    *,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
    actuals: Actuals | None = None,
) -> int:
    """R12: allocation amounts of a person in the months of a year."""
    scales = tuple(scales)
    return sum(
        allocation_amount(
            a, rates, scales, partial_months=partial_months, actuals=actuals, year=year
        )
        for a in allocations
        if a.person_id == person_id
    )


def kpi_target(
    target: BillabilityTarget, rates: RateBook, scales: Iterable[PersonScale]
) -> int:
    """R13: target percentage times the person's rate over the months of the year.

    Months in which the person has no billing scale do not count.
    """
    scales = tuple(scales)
    year_rate = 0
    for month in months_of_year(target.year):
        scale = billing_scale(scales, target.person_id, month.first_day, month.last_day)
        if scale is None:
            continue
        category = rates.category_for_scale(month.year, scale)
        year_rate += rates.monthly_rate_cents(month.year, category)
    return round_cents(_exact(target.target_pct) / _HUNDRED * year_rate)


# R14


def category_mismatches(
    line: BudgetLine,
    allocations: Iterable[Allocation],
    rates: RateBook,
    scales: Iterable[PersonScale],
) -> tuple[CategoryMismatch, ...]:
    """R14: allocations of people who bill in another category than the
    budget line assumes, as runs of consecutive months."""
    if line.kind is BudgetLineKind.FIXED:
        return ()
    _, line_category, _, _ = _require_personnel(line)
    scales = tuple(scales)
    mismatches: list[CategoryMismatch] = []
    for allocation in allocations:
        if allocation.budget_line_id != line.id:
            continue
        run: CategoryMismatch | None = None
        for month in months_between(allocation.start_date, allocation.end_date):
            first, last = overlap(month, allocation.start_date, allocation.end_date)  # type: ignore[misc]
            category = rate_category(
                rates, scales, allocation.person_id, month, start=first, end=last
            )
            if run is not None and category == run.person_category:
                run = replace(run, last_month=month)
                continue
            if run is not None:
                mismatches.append(run)
                run = None
            if category == line_category:
                continue
            person_rate = rates.monthly_rate_cents(month.year, category)
            line_rate = rates.monthly_rate_cents(month.year, line_category)
            if person_rate > line_rate:
                direction = MismatchDirection.OVERRUN
            elif person_rate < line_rate:
                direction = MismatchDirection.UNDERRUN
            else:
                direction = MismatchDirection.SAME_RATE
            run = CategoryMismatch(
                allocation_id=allocation.id,
                person_id=allocation.person_id,
                budget_line_id=line.id,
                line_category=line_category,
                person_category=category,
                first_month=month,
                last_month=month,
                direction=direction,
            )
        if run is not None:
            mismatches.append(run)
    return tuple(mismatches)


# Monthly close


def closed_month_amount(
    allocation: Allocation,
    month: Month,
    rates: RateBook,
    scales: Iterable[PersonScale],
    *,
    actual_fte_pct: Decimal | None = None,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
) -> MonthAmount:
    """Amount of one allocation in one month at the monthly close.

    The planned amount is the proposal; an established actual percentage
    overrides it and counts over the whole month.
    """
    if overlap(month, allocation.start_date, allocation.end_date) is None:
        raise InvalidInputError(f"allocation {allocation.id} does not run in {month}")
    actuals = (
        {(allocation.id, month): actual_fte_pct} if actual_fte_pct is not None else None
    )
    for amount in allocation_months(
        allocation, rates, scales, partial_months=partial_months, actuals=actuals
    ):
        if amount.month == month:
            return amount
    # Touched month that the strategy counts for nothing (GRIST_DATEDIF).
    scales = tuple(scales)
    first, last = overlap(month, allocation.start_date, allocation.end_date)  # type: ignore[misc]
    category = rate_category(
        rates, scales, allocation.person_id, month, start=first, end=last
    )
    return _month_amount(
        month,
        allocation.fte_pct,
        Fraction(0),
        category,
        rates.monthly_rate_cents(month.year, category),
        AmountSource.PLANNED,
    )


def billing_lines(
    month: Month,
    allocations: Iterable[Allocation],
    budget_lines: Iterable[BudgetLine],
    rates: RateBook,
    scales: Iterable[PersonScale],
    *,
    actuals: Actuals | None = None,
    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS,
) -> tuple[BillingLine, ...]:
    """Billing lines for a closed month: one per allocation running in it."""
    allocations = tuple(allocations)
    scales = tuple(scales)
    lines_by_id = {line.id: line for line in budget_lines}
    by_id = {a.id: a for a in allocations}
    for allocation_id, actual_month in actuals or {}:
        if actual_month != month:
            continue
        allocation = by_id.get(allocation_id)
        if (
            allocation is None
            or overlap(month, allocation.start_date, allocation.end_date) is None
        ):
            raise InvalidInputError(
                f"actual for {month} refers to allocation {allocation_id}, "
                "which does not run then"
            )
    result = []
    for allocation in allocations:
        if overlap(month, allocation.start_date, allocation.end_date) is None:
            continue
        line = lines_by_id.get(allocation.budget_line_id)
        if line is None:
            raise InvalidInputError(
                f"allocation {allocation.id} refers to unknown budget line "
                f"{allocation.budget_line_id}"
            )
        actual = actuals.get((allocation.id, month)) if actuals else None
        amount = closed_month_amount(
            allocation,
            month,
            rates,
            scales,
            actual_fte_pct=actual,
            partial_months=partial_months,
        )
        result.append(
            BillingLine(
                assignment_id=line.assignment_id,
                budget_line_id=line.id,
                allocation_id=allocation.id,
                person_id=allocation.person_id,
                month=month,
                fte_pct=amount.fte_pct,
                category=amount.category,
                monthly_rate_cents=amount.monthly_rate_cents,
                amount_cents=amount.cents,
                source=amount.source,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda b: (
                b.assignment_id,
                b.budget_line_id,
                b.person_id,
                b.allocation_id,
            ),
        )
    )
