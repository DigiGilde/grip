"""Rate cards: request and response shapes.

Rate cards are master data: not personal and not tied to an assignment.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

_MASTER = in_class(DataClass.MASTER_DATA)

Category = Literal["A", "B", "C", "D", "E"]
CardStatus = Literal["draft", "active", "closed"]
# What a new rate is rounded to: whole euros, tens or fifties.
Rounding = Literal["euro", "ten", "fifty"]


class RateBandOut(BaseModel):
    category: Annotated[str, _MASTER]
    monthly_rate_cents: Annotated[int, _MASTER]


class ScaleBandOut(BaseModel):
    scale: Annotated[int, _MASTER]
    category: Annotated[str, _MASTER]


class RateCardOut(BaseModel):
    year: Annotated[int, _MASTER]
    status: Annotated[str, _MASTER]
    rate_bands: Annotated[list[RateBandOut], nested()]
    scale_bands: Annotated[list[ScaleBandOut], nested()]


class RateCardListOut(BaseModel):
    items: Annotated[list[RateCardOut], nested()]
    # Whether the asker may change rate cards; the screen shows or hides the
    # edit actions on it.
    may_manage: Annotated[bool, _MASTER]
    # Instance setting: the increase proposed for a new year.
    default_increase_pct: Annotated[Decimal, _MASTER]


class IndexedRateOut(BaseModel):
    category: Annotated[str, _MASTER]
    old_monthly_rate_cents: Annotated[int, _MASTER]
    new_monthly_rate_cents: Annotated[int, _MASTER]
    difference_cents: Annotated[int, _MASTER]


class IndexationPreviewOut(BaseModel):
    copy_from: Annotated[int, _MASTER]
    increase_pct: Annotated[Decimal, _MASTER]
    rounding: Annotated[str, _MASTER]
    rates: Annotated[list[IndexedRateOut], nested()]


class RateCardCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    # A new year starts as a draft copy of this one.
    copy_from: int | None = Field(default=None, ge=2000, le=2100)
    # With ``copy_from``: the percentage the rates go up by. Left out, the
    # rates are copied as they are.
    increase_pct: Decimal | None = Field(default=None, ge=0, le=25, decimal_places=2)
    rounding: Rounding = "euro"


class ClosedYearConfirmation(BaseModel):
    # Changing a closed year is a separate, explicit action: the caller
    # states that it knows the year is closed and that an audit row is kept.
    confirm_closed_year: bool = False


class RateCardStatusUpdate(ClosedYearConfirmation):
    status: CardStatus


class RateBandUpdate(ClosedYearConfirmation):
    monthly_rate_cents: int = Field(ge=0)


class ScaleBandUpdate(ClosedYearConfirmation):
    category: Category
