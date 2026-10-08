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
    """No rate card that prices is valid in a month.

    A gap between cards is allowed to exist; pricing a month in it is an
    error, never zero.
    """

    def __init__(self, month: Month | int) -> None:
        super().__init__(f"no usable rate card for {month}")
        # ``month`` is None only for callers that still ask per year.
        self.month = month if isinstance(month, Month) else None
        self.year = month.year if isinstance(month, Month) else month


class MissingRateError(CalcError):
    def __init__(self, card: str, category: str) -> None:
        super().__init__(f"rate card {card} has no rate for category {category}")
        self.card = card
        self.category = category


class MissingScaleBandError(CalcError):
    def __init__(self, card: str, scale: int) -> None:
        super().__init__(f"rate card {card} maps scale {scale} to no category")
        self.card = card
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
    """The rates and the scale mapping valid for a period.

    A card starts on the first day of a month and ends on the last day of a
    month (or has no end), so every calendar month is priced by one card.
    """

    valid_from: date
    valid_to: date | None
    status: RateCardStatus
    rate_bands: tuple[RateBand, ...]
    scale_bands: tuple[ScaleBand, ...]
    name: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if self.valid_from.day != 1:
            raise InvalidInputError("a rate card starts on the first day of a month")
        if self.valid_to is not None:
            if self.valid_to < self.valid_from:
                raise InvalidInputError("a rate card ends after it starts")
            if self.valid_to != Month.of(self.valid_to).last_day:
                raise InvalidInputError("a rate card ends on the last day of a month")

    @classmethod
    def for_year(
        cls,
        year: int,
        status: RateCardStatus,
        rate_bands: tuple[RateBand, ...],
        scale_bands: tuple[ScaleBand, ...],
    ) -> RateCard:
        """A card that happens to span one calendar year."""
        return cls(
            valid_from=date(year, 1, 1),
            valid_to=date(year, 12, 31),
            status=status,
            rate_bands=rate_bands,
            scale_bands=scale_bands,
            name=str(year),
        )

    @property
    def label(self) -> str:
        return self.name or f"from {self.valid_from.isoformat()}"

    def covers(self, month: Month) -> bool:
        return self.valid_from <= month.first_day and (
            self.valid_to is None or self.valid_to >= month.last_day
        )


def _as_month(when: Month | date | int) -> Month:
    if isinstance(when, Month):
        return when
    if isinstance(when, date):
        return Month.of(when)
    # A bare year, from callers of before cards had a validity: January.
    return Month(when, 1)


@dataclass(frozen=True)
class RateBook:
    """All rate cards. A month is priced by the card valid in it.

    Active and closed cards price. A draft does not, unless include_draft is
    set (for budgeting a period whose card is not active yet), and then only
    in a month no other card covers.
    """

    cards: tuple[RateCard, ...]
    include_draft: bool = False

    def card(self, when: Month | date | int) -> RateCard:
        month = _as_month(when)
        draft: RateCard | None = None
        for card in self.cards:
            if not card.covers(month):
                continue
            if card.status is not RateCardStatus.DRAFT:
                return card
            draft = draft or card
        if draft is not None and self.include_draft:
            return draft
        raise MissingRateCardError(month if not isinstance(when, int) else when)

    def monthly_rate_cents(self, when: Month | date | int, category: str) -> int:
        card = self.card(when)
        for band in card.rate_bands:
            if band.category == category:
                return band.monthly_rate_cents
        raise MissingRateError(card.label, category)

    def category_for_scale(self, when: Month | date | int, scale: int) -> str:
        card = self.card(when)
        for band in card.scale_bands:
            if band.scale == scale:
                return band.category
        raise MissingScaleBandError(card.label, scale)


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
