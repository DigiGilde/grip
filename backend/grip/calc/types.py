"""Inputs, outputs and errors of the calculation module.

Conventions:
- Money is an integer number of cents.
- FTE is a Decimal fraction (0.8 means 0.8 FTE).
- Percentages are Decimal percent values (80 means 80 percent).
- Dates are inclusive on both ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
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
    """No rate card that prices is valid on a day.

    A gap between cards is allowed to exist; pricing a day in it is an
    error, never zero.
    """

    def __init__(self, day: date | Month | int) -> None:
        super().__init__(f"no usable rate card for {day}")
        if isinstance(day, date):
            self.day: date | None = day
            self.month: Month | None = Month.of(day)
            self.year = day.year
        elif isinstance(day, Month):
            self.day, self.month, self.year = day.first_day, day, day.year
        else:
            # A caller that still asks per year.
            self.day, self.month, self.year = None, None, day


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
    """The rates and the scale mapping valid from a date to a date.

    Any date: a card can start or end halfway through a month. ``valid_to``
    None means open-ended.
    """

    valid_from: date
    valid_to: date | None
    status: RateCardStatus
    rate_bands: tuple[RateBand, ...]
    scale_bands: tuple[ScaleBand, ...]
    name: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise InvalidInputError("a rate card ends after it starts")

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

    def valid_on(self, day: date) -> bool:
        return self.valid_from <= day and (
            self.valid_to is None or self.valid_to >= day
        )


def _as_day(when: date | Month | int) -> date:
    if isinstance(when, Month):
        return when.first_day
    if isinstance(when, date):
        return when
    # A bare year, from callers of before cards had a validity: 1 January.
    return date(when, 1, 1)


@dataclass(frozen=True)
class RateBook:
    """All rate cards. A day is priced by the card valid on it.

    Active and closed cards price. A draft does not, unless include_draft is
    set (for budgeting a period whose card is not active yet), and then only
    on a day no other card covers.

    A month given instead of a day means its first day; inside a month the
    card can change, which the rules handle by pricing each stretch.
    """

    cards: tuple[RateCard, ...]
    include_draft: bool = False

    def card(self, when: date | Month | int) -> RateCard:
        day = _as_day(when)
        draft: RateCard | None = None
        for card in self.cards:
            if not card.valid_on(day):
                continue
            if card.status is not RateCardStatus.DRAFT:
                return card
            draft = draft or card
        if draft is not None and self.include_draft:
            return draft
        raise MissingRateCardError(when)

    def monthly_rate_cents(self, when: date | Month | int, category: str) -> int:
        card = self.card(when)
        for band in card.rate_bands:
            if band.category == category:
                return band.monthly_rate_cents
        raise MissingRateError(card.label, category)

    def category_for_scale(self, when: date | Month | int, scale: int) -> str:
        card = self.card(when)
        for band in card.scale_bands:
            if band.scale == scale:
                return band.category
        raise MissingScaleBandError(card.label, scale)

    def change_days(self, start: date, end: date) -> set[date]:
        """Days after ``start`` up to ``end`` on which another card (or no
        card) starts to apply."""
        days: set[date] = set()
        for card in self.cards:
            if card.status is RateCardStatus.DRAFT and not self.include_draft:
                continue
            for day in (
                card.valid_from,
                card.valid_to + timedelta(days=1) if card.valid_to else None,
            ):
                if day is not None and start < day <= end:
                    days.add(day)
        return days


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
class Stretch:
    """Consecutive days of a month in which card, scale and so the monthly
    rate are constant. ``fraction`` is its share of the month."""

    start: date
    end: date
    fraction: Fraction
    category: str
    monthly_rate_cents: int
    exact: Fraction


@dataclass(frozen=True)
class MonthAmount:
    """One calendar month of a personnel amount.

    `exact` is the unrounded amount in cents; `cents` is the recorded amount.
    """

    month: Month
    fte_pct: Decimal
    fraction: Fraction
    # Of the first stretch. A month in which the rate card or the billing
    # scale changes has more than one stretch; see ``stretches``.
    category: str
    monthly_rate_cents: int
    exact: Fraction
    cents: int
    source: AmountSource = AmountSource.PLANNED
    stretches: tuple[Stretch, ...] = ()

    @property
    def changes_inside(self) -> bool:
        return len(self.stretches) > 1


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
    # The first day of the run: the start of the inzet, or the day the
    # person's scale or the rate card changed.
    since: date | None = None


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
