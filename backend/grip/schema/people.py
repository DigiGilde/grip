"""Persons, scale history, hire and functions: request and response shapes.

Who someone is and whom they report to is roster data. The functions someone
holds and whether they are hired is staffing data (class C). The billing
scale and what follows from it is class D, the cost side of hire is class E.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
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
    """A period in which the person is hired from a supplier.

    That someone is hired, from whom and until when is how they are engaged
    (class C). What it costs is class E.
    """

    id: Annotated[UUID, _STAFFING]
    supplier: Annotated[str, _STAFFING]
    valid_from: Annotated[date, _STAFFING]
    valid_to: Annotated[date | None, _STAFFING]
    contract_reference: Annotated[str | None, _STAFFING]
    cost_monthly_rate_cents: Annotated[int, _COST]
    notes: Annotated[str | None, _COST]


class FunctionGrantOut(BaseModel):
    """A right in grip the person holds: since when and who granted it."""

    function: Annotated[str, _STAFFING]
    since: Annotated[date, _STAFFING]
    # Null when the system granted it at the set-up of the instance.
    granted_by_name: Annotated[str | None, _STAFFING]


class PersonOut(BaseModel):
    id: Annotated[UUID, _ROSTER]
    name: Annotated[str, _ROSTER]
    # Null for a prospective colleague: the address comes later, from Wies.
    email: Annotated[str | None, _ROSTER]
    is_active: Annotated[bool, _ROSTER]
    uri: Annotated[str | None, _ROSTER]
    # prospective | colleague | left. A prospective colleague is hired and
    # planned, and has not started; screens show "start op <datum>".
    stage: Annotated[str, _ROSTER]
    starts_on: Annotated[date | None, _ROSTER]
    can_log_in: Annotated[bool, _ROSTER]
    manager_id: Annotated[UUID | None, _ROSTER]
    manager_name: Annotated[str | None, _ROSTER]

    functions: Annotated[list[str], _STAFFING]
    function_grants: Annotated[list[FunctionGrantOut], nested()]
    # The only active beheerder: that right cannot be revoked, and the
    # person cannot be made inactive, until someone else holds it too.
    is_sole_beheerder: Annotated[bool, _STAFFING]
    is_hired: Annotated[bool, _STAFFING]
    # Staffing on the reference day: on how many assignments, for how much.
    current_assignment_count: Annotated[int, _STAFFING]
    current_fte_pct: Annotated[Decimal, _STAFFING]

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
    # Leave out for a prospective colleague; start_date is then required.
    email: str | None = Field(default=None, min_length=3, max_length=320)
    manager_id: UUID | None = None
    start_date: date | None = None
    # The merk in Wies under which the new colleague is proposed.
    suborganization: str | None = Field(default=None, max_length=255)
    # Reference and link of the hire in the recruitment system.
    source_ref: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=500)


class StartDateUpdate(BaseModel):
    start_date: date


class HireWithdrawal(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


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
