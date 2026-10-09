"""``billing_lines_by_month`` gives what ``billing_lines`` gives per month.

The function exists for speed only: it prices the planned months of an
allocation once. Every case here is asked both ways and must agree, in the
lines and in the error.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from conftest import RATES_2026, make_card

from grip.calc import (
    Allocation,
    BudgetLine,
    BudgetLineKind,
    CalcError,
    Month,
    PartialMonths,
    PersonScale,
    RateBook,
    billing_lines,
    billing_lines_by_month,
)
from grip.calc.periods import months_between

RATES_2027 = {category: cents + 50_000 for category, cents in RATES_2026.items()}


def _line(line_id: str) -> BudgetLine:
    return BudgetLine(
        id=line_id,
        assignment_id="assignment-1",
        kind=BudgetLineKind.PERSONNEL,
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2025, 1, 1),
        end_date=date(2028, 12, 31),
    )


def _one_by_one(months, allocations, lines, rates, scales, actuals, partial):
    found = {}
    for month in months:
        own = {key: pct for key, pct in actuals.items() if key[1] == month}
        try:
            found[month] = billing_lines(
                month,
                allocations,
                lines,
                rates,
                scales,
                actuals=own,
                partial_months=partial,
            )
        except CalcError as error:
            found[month] = (type(error), str(error))
    return found


def _together(months, allocations, lines, rates, scales, actuals, partial):
    found = billing_lines_by_month(
        months,
        allocations,
        lines,
        rates,
        scales,
        actuals=actuals,
        partial_months=partial,
    )
    return {
        month: (type(value), str(value)) if isinstance(value, CalcError) else value
        for month, value in found.items()
    }


def _case(seed: int):
    rng = random.Random(seed)
    # A card may be missing for a year, and a person may lack a scale for a
    # while: both make months that cannot be priced.
    years = [2026, 2027] if rng.random() < 0.7 else [2026]
    rates = RateBook(
        cards=tuple(
            make_card(year, RATES_2026 if year == 2026 else RATES_2027)
            for year in years
        )
    )
    scales = [
        PersonScale("p-1", date(2025, 1, 1), 14),
        PersonScale("p-2", date(2025, 1, 1), 12, valid_to=date(2026, 8, 14)),
        PersonScale("p-2", date(2026, 8, 15), 13),
    ]
    if rng.random() < 0.5:
        scales.append(PersonScale("p-3", date(2026, 5, 1), 11))
    allocations = []
    for number in range(rng.randint(1, 5)):
        start = date(2026, 1, 1) + timedelta(days=rng.randint(0, 400))
        end = start + timedelta(days=rng.randint(0, 420))
        allocations.append(
            Allocation(
                f"alloc-{number}",
                rng.choice(["p-1", "p-2", "p-3"]),
                rng.choice(["line-1", "line-2"]),
                start,
                end,
                Decimal(rng.choice(["100", "50", "37.5", "20"])),
            )
        )
    lines = (_line("line-1"), _line("line-2"))
    first = min(a.start_date for a in allocations)
    last = max(a.end_date for a in allocations)
    months = list(months_between(first - timedelta(days=40), last))
    actuals = {}
    for allocation in allocations:
        for month in months_between(allocation.start_date, allocation.end_date):
            if rng.random() < 0.4:
                actuals[(allocation.id, month)] = Decimal(
                    rng.choice(["0", "25", "80", "100"])
                )
    partial = rng.choice(list(PartialMonths))
    return months, tuple(allocations), lines, rates, tuple(scales), actuals, partial


@pytest.mark.parametrize("seed", range(300))
def test_same_as_month_by_month(seed):
    case = _case(seed)
    assert _together(*case) == _one_by_one(*case)


def test_a_month_that_cannot_be_priced_gives_its_error():
    rates = RateBook(cards=(make_card(2026, RATES_2026),))
    scales = (PersonScale("p-1", date(2025, 1, 1), 14),)
    allocation = Allocation(
        "alloc-1", "p-1", "line-1", date(2026, 11, 1), date(2027, 2, 28), Decimal("100")
    )
    found = billing_lines_by_month(
        [Month(2026, 11), Month(2027, 1)],
        (allocation,),
        (_line("line-1"),),
        rates,
        scales,
    )
    # Asked alone, a month of an allocation with a month that has no card
    # fails too: the outcome per month is the same, whatever it is.
    alone = _one_by_one(
        [Month(2026, 11), Month(2027, 1)],
        (allocation,),
        (_line("line-1"),),
        rates,
        scales,
        {},
        PartialMonths.CALENDAR_DAYS,
    )
    assert {
        month: (type(v), str(v)) if isinstance(v, CalcError) else v
        for month, v in found.items()
    } == alone
    assert isinstance(found[Month(2027, 1)], CalcError)
