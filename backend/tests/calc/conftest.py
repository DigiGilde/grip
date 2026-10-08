"""Shared fixtures for the calculation tests. All amounts are fictitious."""

from datetime import date
from decimal import Decimal

import pytest

from grip.calc import (
    Allocation,
    BudgetLine,
    BudgetLineKind,
    PersonScale,
    RateBand,
    RateBook,
    RateCard,
    RateCardStatus,
    ScaleBand,
)

EUR = 100

RATES_2026 = {"A": 9_000, "B": 12_000, "C": 15_000, "D": 18_000, "E": 21_000}
RATES_2027 = {"A": 9_450, "B": 12_600, "C": 15_750, "D": 18_900, "E": 22_050}
SCALES = {
    8: "A",
    9: "A",
    10: "B",
    11: "B",
    12: "C",
    13: "C",
    14: "D",
    15: "D",
    16: "E",
    17: "E",
}


def make_card(year, rates, status=RateCardStatus.ACTIVE, scales=SCALES):
    return RateCard.for_year(
        year,
        status,
        tuple(RateBand(c, r * EUR) for c, r in rates.items()),
        tuple(ScaleBand(s, c) for s, c in scales.items()),
    )


@pytest.fixture
def rates():
    return RateBook(cards=(make_card(2026, RATES_2026), make_card(2027, RATES_2027)))


@pytest.fixture
def scales():
    # p-d bills in D, p-c in C, p-move moves from C to D on 2026-07-01.
    return (
        PersonScale("p-d", date(2025, 1, 1), 14),
        PersonScale("p-c", date(2025, 1, 1), 12),
        PersonScale("p-move", date(2025, 1, 1), 13, valid_to=date(2026, 6, 30)),
        PersonScale("p-move", date(2026, 7, 1), 14),
    )


@pytest.fixture
def allocation():
    def build(
        person_id="p-d",
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        fte_pct="100",
        budget_line_id="line-1",
        id="alloc-1",
    ):
        return Allocation(id, person_id, budget_line_id, start, end, Decimal(fte_pct))

    return build


@pytest.fixture
def personnel_line():
    def build(
        fte="1",
        category="D",
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
        id="line-1",
        assignment_id="assignment-1",
    ):
        return BudgetLine(
            id=id,
            assignment_id=assignment_id,
            kind=BudgetLineKind.PERSONNEL,
            fte=Decimal(fte),
            rate_category=category,
            start_date=start,
            end_date=end,
        )

    return build


@pytest.fixture
def fixed_line():
    def build(
        amount=10_000 * EUR, year=2026, id="line-fixed", assignment_id="assignment-1"
    ):
        return BudgetLine(
            id=id,
            assignment_id=assignment_id,
            kind=BudgetLineKind.FIXED,
            amount_cents=amount,
            year=year,
        )

    return build
