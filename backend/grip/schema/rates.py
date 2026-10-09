"""Rate cards: request and response shapes.

Rate cards are master data: not personal and not tied to an assignment.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

_MASTER = in_class(DataClass.MASTER_DATA)
# The amounts: only for who may read the price list.
_AMOUNT = in_class(DataClass.RATE_TABLE)

Category = Literal["A", "B", "C", "D", "E"]
CardStatus = Literal["draft", "active", "closed"]
# What a new rate is rounded to: whole euros, tens or fifties.
Rounding = Literal["euro", "ten", "fifty"]


class RateBandOut(BaseModel):
    id: Annotated[UUID | None, _MASTER] = None
    version: Annotated[int, _MASTER] = 1
    category: Annotated[str, _MASTER]
    monthly_rate_cents: Annotated[int, _AMOUNT]


class ScaleBandOut(BaseModel):
    scale: Annotated[int, _MASTER]
    category: Annotated[str, _MASTER]


class RateCardOut(BaseModel):
    id: Annotated[UUID, _MASTER]
    # Counts the changes of the record; a form sends it back with its save.
    version: Annotated[int, _MASTER] = 1
    # "Tarieven 2026", "Tarieven vanaf 15 juli 2026".
    name: Annotated[str, _MASTER]
    valid_from: Annotated[date, _MASTER]
    # Null: open-ended.
    valid_to: Annotated[date | None, _MASTER]
    status: Annotated[str, _MASTER]
    # The calendar year the card starts in. A year can hold more than one
    # card; kept for screens from before a card had a validity.
    year: Annotated[int, _MASTER]
    spans_calendar_year: Annotated[bool, _MASTER]
    rate_bands: Annotated[list[RateBandOut], nested()]
    scale_bands: Annotated[list[ScaleBandOut], nested()]


class RateCardListOut(BaseModel):
    # Newest first.
    items: Annotated[list[RateCardOut], nested()]
    # Whether the asker may change rate cards; the screen shows or hides the
    # edit actions on it.
    may_manage: Annotated[bool, _MASTER]
    # Whether the asker gets the amounts; without it the bands carry the
    # category only.
    may_read_amounts: Annotated[bool, _MASTER]
    # Instance setting: the increase proposed for a new card.
    default_increase_pct: Annotated[Decimal, _MASTER]


class IndexedRateOut(BaseModel):
    category: Annotated[str, _MASTER]
    old_monthly_rate_cents: Annotated[int, _MASTER]
    new_monthly_rate_cents: Annotated[int, _MASTER]
    difference_cents: Annotated[int, _MASTER]


class IndexationPreviewOut(BaseModel):
    # The year the source card starts in; see ``copy_from_id``.
    copy_from: Annotated[int, _MASTER]
    copy_from_id: Annotated[UUID, _MASTER]
    copy_from_name: Annotated[str, _MASTER]
    increase_pct: Annotated[Decimal, _MASTER]
    rounding: Annotated[str, _MASTER]
    rates: Annotated[list[IndexedRateOut], nested()]


class RateCardCreate(BaseModel):
    """A new card, as a draft.

    Send ``valid_from`` to start a card on any date ("nieuwe tarievenkaart
    vanaf"). Sending only ``year`` still makes the card of a calendar year.
    """

    valid_from: date | None = None
    valid_to: date | None = None
    name: str | None = Field(default=None, max_length=100)
    # Copy the rates and the scale mapping of the card valid just before
    # ``valid_from``.
    copy_previous: bool = False
    # Or of this card.
    copy_from_id: UUID | None = None
    year: int | None = Field(default=None, ge=2000, le=2100)
    # The year form of ``copy_from_id``.
    copy_from: int | None = Field(default=None, ge=2000, le=2100)
    # With a copy: the percentage the rates go up by. Left out, the rates
    # are copied as they are.
    increase_pct: Decimal | None = Field(default=None, ge=0, le=25, decimal_places=2)
    rounding: Rounding = "euro"


class RateCardUpdate(BaseModel):
    """Rename a card or change its end date. Only what is sent changes."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    valid_to: date | None = None
    confirm_closed_year: bool = False


class ClosedYearConfirmation(BaseModel):
    # Changing a closed card is a separate, explicit action: the caller
    # states that it knows the card is closed and that an audit row is kept.
    # (The name dates from when a card was a calendar year.)
    confirm_closed_year: bool = False


class RateCardStatusUpdate(ClosedYearConfirmation):
    status: CardStatus


class ShortenedCardOut(BaseModel):
    id: Annotated[UUID, _MASTER]
    name: Annotated[str, _MASTER]
    old_valid_to: Annotated[date | None, _MASTER]
    new_valid_to: Annotated[date, _MASTER]


class MonthChangeOut(BaseModel):
    # JJJJ-MM.
    month: Annotated[str, _MASTER]
    # open, closed (afgesloten, nog niet aangeleverd), delivered, invoiced.
    state: Annotated[str, _MASTER]
    before_cents: Annotated[int | None, _MASTER]
    after_cents: Annotated[int | None, _MASTER]
    difference_cents: Annotated[int, _MASTER]
    invoice_number: Annotated[str | None, _MASTER]


class AssignmentImpactOut(BaseModel):
    assignment_id: Annotated[UUID, _MASTER]
    assignment_name: Annotated[str, _MASTER]
    open_difference_cents: Annotated[int, _MASTER]
    # Closed, not delivered: prices right from now on.
    closed_difference_cents: Annotated[int, _MASTER]
    # Already delivered: becomes a correction to deliver (naverrekening).
    correction_cents: Annotated[int, _MASTER]
    months: Annotated[list[MonthChangeOut], nested()]


class PriceImpactOut(BaseModel):
    """What a change does to what is already priced. Nothing was saved."""

    budget_lines_changed: Annotated[int, _MASTER]
    budget_difference_cents: Annotated[int, _MASTER]
    allocations_changed: Annotated[int, _MASTER]
    open_difference_cents: Annotated[int, _MASTER]
    closed_difference_cents: Annotated[int, _MASTER]
    correction_cents: Annotated[int, _MASTER]
    # Months that can no longer be priced after the change.
    unpriced_months: Annotated[int, _MASTER]
    reaches_into_the_past: Annotated[bool, _MASTER]
    # Among the repriced: assignments with a signed quote, and how far
    # their budget moves from what was signed.
    signed_assignments_changed: Annotated[int, _MASTER] = 0
    signed_difference_cents: Annotated[int, _MASTER] = 0
    assignments: Annotated[list[AssignmentImpactOut], nested()]


class RateGapOut(BaseModel):
    """A period no settled card prices."""

    start_date: Annotated[date, _MASTER]
    end_date: Annotated[date, _MASTER]
    # Names of the drafts that lie in the gap: what to settle next.
    drafts: Annotated[list[str], _MASTER]


class ActivationPreviewOut(BaseModel):
    card: Annotated[RateCardOut, nested()]
    # The periods without a settled card once this one is settled.
    gaps: Annotated[list[RateGapOut], nested()] = []
    # The card that activating this one ends on the day before it starts.
    shortened: Annotated[ShortenedCardOut | None, nested()]
    impact: Annotated[PriceImpactOut, nested()]


class ValidRateOut(BaseModel):
    """A stretch of a period and the card that prices it."""

    start_date: Annotated[date, _MASTER]
    end_date: Annotated[date, _MASTER]
    # Null in a gap: no card prices these days.
    card_id: Annotated[UUID | None, _MASTER]
    card_name: Annotated[str | None, _MASTER]
    card_valid_to: Annotated[date | None, _MASTER]
    rate_bands: Annotated[list[RateBandOut], nested()]
    scale_bands: Annotated[list[ScaleBandOut], nested()]


class ValidRatesOut(BaseModel):
    start_date: Annotated[date, _MASTER]
    end_date: Annotated[date, _MASTER]
    stretches: Annotated[list[ValidRateOut], nested()]
    # More than one card prices the period.
    crosses_cards: Annotated[bool, _MASTER]
    # And they do not all have the same rates.
    rates_differ: Annotated[bool, _AMOUNT]
    has_gap: Annotated[bool, _MASTER]
    # One sentence for under a field: "Volgens Tarieven 2026, geldig t/m ...".
    summary: Annotated[str, _MASTER]


class RateBandUpdate(ClosedYearConfirmation):
    monthly_rate_cents: int = Field(ge=0)


class ScaleBandUpdate(ClosedYearConfirmation):
    category: Category
