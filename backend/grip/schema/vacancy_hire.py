"""Shapes for the recruitment reference and the hire on a vacancy.

All of it is staffing (class C): who was hired is a name, and the reference
tells where the selection took place.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

_C = in_class(DataClass.STAFFING)


class RecruitmentRefOut(BaseModel):
    system: Annotated[str, _C]
    reference: Annotated[str, _C]
    url: Annotated[str | None, _C]


class ProposedAllocationOut(BaseModel):
    budget_line_id: Annotated[UUID, _C]
    start_date: Annotated[date, _C]
    end_date: Annotated[date, _C]
    fte_pct: Annotated[str, _C]


class HireOut(BaseModel):
    person_id: Annotated[UUID | None, _C]
    person_name: Annotated[str | None, _C]
    start_date: Annotated[date, _C]
    # "prospective" until the person has started and has an address.
    stage: Annotated[str | None, _C]
    # The inzet that follows from the hire, when it is not planned yet.
    proposed_allocation: Annotated[ProposedAllocationOut | None, nested()]
    allocation_id: Annotated[UUID | None, _C]


class VacancyHireOut(BaseModel):
    vacancy_id: Annotated[UUID, _C]
    recruitment_ref: Annotated[RecruitmentRefOut | None, nested()]
    hire: Annotated[HireOut | None, nested()]


class RecruitmentRefIn(BaseModel):
    # Empty clears the reference.
    reference: str = Field(default="", max_length=255)
    url: str | None = Field(default=None, max_length=500)
    system: str | None = Field(default=None, max_length=40)


class HireIn(BaseModel):
    start_date: date
    # One of the two: a person grip knows, or the name of the new colleague.
    person_id: UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    # The merk in Wies under which the new colleague is proposed.
    suborganization: str | None = Field(default=None, max_length=255)
    create_allocation: bool = False
    note: str | None = Field(default=None, max_length=1000)


class HireWithdrawalIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
