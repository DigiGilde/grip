"""Rate cards: request and response shapes.

Rate cards are master data: not personal and not tied to an assignment.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

_MASTER = in_class(DataClass.MASTER_DATA)

Category = Literal["A", "B", "C", "D", "E"]
CardStatus = Literal["draft", "active", "closed"]


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


class RateCardCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    # A new year starts as a draft copy of this one.
    copy_from: int | None = Field(default=None, ge=2000, le=2100)


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
