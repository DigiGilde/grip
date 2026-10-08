"""Persons, scale history, hire and functions: request and response shapes.

Who someone is and whom they report to is roster data. The functions someone
holds and whether they are hired is staffing data (class C). The billing
scale and what follows from it is class D, the cost side of hire is class E.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

_ROSTER = in_class(DataClass.STAFFING_ROSTER)
_STAFFING = in_class(DataClass.STAFFING)
_RATE = in_class(DataClass.PERSON_RATE)
_COST = in_class(DataClass.PERSON_COST)


class ScaleOut(BaseModel):
    id: Annotated[UUID, _RATE]
    valid_from: Annotated[date, _RATE]
    valid_to: Annotated[date | None, _RATE]
    billing_scale: Annotated[int, _RATE]


class HireOut(BaseModel):
    id: Annotated[UUID, _COST]
    supplier: Annotated[str, _COST]
    cost_monthly_rate_cents: Annotated[int, _COST]
    valid_from: Annotated[date, _COST]
    valid_to: Annotated[date | None, _COST]
    contract_reference: Annotated[str | None, _COST]
    notes: Annotated[str | None, _COST]


class PersonOut(BaseModel):
    id: Annotated[UUID, _ROSTER]
    name: Annotated[str, _ROSTER]
    email: Annotated[str, _ROSTER]
    is_active: Annotated[bool, _ROSTER]
    manager_id: Annotated[UUID | None, _ROSTER]
    manager_name: Annotated[str | None, _ROSTER]

    functions: Annotated[list[str], _STAFFING]
    is_hired: Annotated[bool, _STAFFING]

    # What the person bills at on the reference day (rule R1). Null where a
    # scale, a rate card or a band is missing.
    billing_scale: Annotated[int | None, _RATE]
    rate_category: Annotated[str | None, _RATE]
    monthly_rate_cents: Annotated[int | None, _RATE]
    scales: Annotated[list[ScaleOut], nested()]

    # Cost side of hire on the reference day; the margin is the billing rate
    # minus the cost rate, per FTE per month.
    cost_monthly_rate_cents: Annotated[int | None, _COST]
    margin_monthly_cents: Annotated[int | None, _COST]
    hires: Annotated[list[HireOut], nested()]


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    manager_id: UUID | None = None


class PersonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    # Send null to remove the line manager; leave the field out to keep it.
    manager_id: UUID | None = None
    is_active: bool | None = None


class ScaleCreate(BaseModel):
    valid_from: date
    valid_to: date | None = None
    billing_scale: int = Field(ge=1, le=30)
    confirm_closed_year: bool = False


class HireCreate(BaseModel):
    supplier: str = Field(min_length=1, max_length=255)
    cost_monthly_rate_cents: int = Field(ge=0)
    valid_from: date
    valid_to: date | None = None
    contract_reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None
