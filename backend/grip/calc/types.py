"""Inputs, outputs and errors of the calculation module.

Conventions:
- Money is an integer number of cents.
- FTE is a Decimal fraction (0.8 means 0.8 FTE).
- Percentages are Decimal percent values (80 means 80 percent).
- Dates are inclusive on both ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from grip.calc.periods import Month


class CalcError(Exception):
    """Base class for every error raised by the calculation module."""


class InvalidInputError(CalcError, ValueError):
    pass


class MissingPeriodError(InvalidInputError):
    """A personnel budget line has no period, so it cannot be priced.

    This is a line that follows an assignment without a period. It is never
    priced as zero.
    """

    def __init__(self, line_id: str) -> None:
        super().__init__(f"personnel budget line {line_id} has no period yet")
        self.line_id = line_id


class MissingRateCardError(CalcError):
    def __init__(self, year: int) -> None:
        super().__init__(f"no usable rate card for {year}")
        self.year = year


class MissingRateError(CalcError):
    def __init__(self, year: int, category: str) -> None:
        super().__init__(f"rate card {year} has no rate for category {category}")
        self.year = year
        self.category = category


class MissingScaleBandError(CalcError):
    def __init__(self, year: int, scale: int) -> None:
        super().__init__(f"rate card {year} maps scale {scale} to no category")
        self.year = year
        self.scale = scale


class MissingPersonScaleError(CalcError):
    def __init__(self, person_id: str, day: date) -> None:
        super().__init__(f"person {person_id} has no billing scale on {day}")
        self.person_id = person_id
        self.day = day


class CoverageExceededError(CalcError):
    def __init__(self, cost_item_id: str, pct_total: Decimal) -> None:
        super().__init__(
            f"cost item {cost_item_id} is covered for {pct_total} percent, above 100"
        )
        self.cost_item_id = cost_item_id
        self.pct_total = pct_total


class CoverageBasis(StrEnum):
    FORECAST = "forecast"
    BUDGETED = "budgeted"


class RateCardStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class BudgetLineKind(StrEnum):
    PERSONNEL = "personnel"
    FIXED = "fixed"


class InvoiceLineKind(StrEnum):
    ACTUAL = "actual"
    ESTIMATE = "estimate"


class AmountSource(StrEnum):
    PLANNED = "planned"
    ACTUAL = "actual"


class MismatchDirection(StrEnum):
    OVERRUN = "overrun"
    UNDERRUN = "underrun"
    SAME_RATE = "same_rate"


@dataclass(frozen=True)
class RateBand:
    category: str
    monthly_rate_cents: int


@dataclass(frozen=True)
class ScaleBand:
    scale: int
    category: str


@dataclass(frozen=True)
class RateCard:
    year: int
    status: RateCardStatus
    rate_bands: tuple[RateBand, ...]
    scale_bands: tuple[ScaleBand, ...]


@dataclass(frozen=True)
class RateBook:
    """All rate cards. Active and closed cards price; a draft does not,
    unless include_draft is set (for budgeting a year that is not open yet)."""

    cards: tuple[RateCard, ...]
    include_draft: bool = False

    def card(self, year: int) -> RateCard:
        for card in self.cards:
            if card.year != year:
                continue
            if card.status is RateCardStatus.DRAFT and not self.include_draft:
                continue
            return card
        raise MissingRateCardError(year)

    def monthly_rate_cents(self, year: int, category: str) -> int:
        for band in self.card(year).rate_bands:
            if band.category == category:
                return band.monthly_rate_cents
        raise MissingRateError(year, category)

    def category_for_scale(self, year: int, scale: int) -> str:
        for band in self.card(year).scale_bands:
            if band.scale == scale:
                return band.category
        raise MissingScaleBandError(year, scale)


@dataclass(frozen=True)
class PersonScale:
    person_id: str
    valid_from: date
    billing_scale: int
    valid_to: date | None = None


@dataclass(frozen=True)
class BillabilityTarget:
    person_id: str
    year: int
    target_pct: Decimal


@dataclass(frozen=True)
class BudgetLine:
    id: str
    assignment_id: str
    kind: BudgetLineKind
    # personnel
    fte: Decimal | None = None
    rate_category: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    # fixed
    amount_cents: int | None = None
    year: int | None = None


@dataclass(frozen=True)
class Allocation:
    id: str
    person_id: str
    budget_line_id: str
    start_date: date
    end_date: date
    fte_pct: Decimal


@dataclass(frozen=True)
class CostItem:
    id: str
    budgeted_cents: int


@dataclass(frozen=True)
class InvoiceLine:
    id: str
    cost_item_id: str
    kind: InvoiceLineKind
    amount_cents: int
    period: date | None = None


@dataclass(frozen=True)
class CostCoverage:
    id: str
    cost_item_id: str
    budget_line_id: str
    pct: Decimal


@dataclass(frozen=True)
class MonthAmount:
    """One calendar month of a personnel amount.

    `exact` is the unrounded amount in cents; `cents` is the recorded amount.
    """

    month: Month
    fte_pct: Decimal
    fraction: Fraction
    category: str
    monthly_rate_cents: int
    exact: Fraction
    cents: int
    source: AmountSource = AmountSource.PLANNED


@dataclass(frozen=True)
class CostItemCoverage:
    cost_item_id: str
    basis_cents: int
    pct_total: Decimal
    covered_cents: int
    uncovered_cents: int


@dataclass(frozen=True)
class BudgetLineStatus:
    budget_line_id: str
    budgeted_cents: int
    used_cents: int
    available_cents: int

    @property
    def overrun(self) -> bool:
        return self.available_cents < 0


@dataclass(frozen=True)
class AssignmentTotals:
    assignment_id: str
    budgeted_cents: int
    used_cents: int
    available_cents: int
    lines: tuple[BudgetLineStatus, ...]

    @property
    def overrun(self) -> bool:
        return self.available_cents < 0


@dataclass(frozen=True)
class CategoryMismatch:
    allocation_id: str
    person_id: str
    budget_line_id: str
    line_category: str
    person_category: str
    first_month: Month
    last_month: Month
    direction: MismatchDirection


@dataclass(frozen=True)
class BillingLine:
    assignment_id: str
    budget_line_id: str
    allocation_id: str
    person_id: str
    month: Month
    fte_pct: Decimal
    category: str
    monthly_rate_cents: int
    amount_cents: int
    source: AmountSource
