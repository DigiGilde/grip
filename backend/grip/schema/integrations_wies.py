"""Shapes of the link with Wies.

Every field of the export carries a data class, so a test can prove that
nothing outside classes A (assignment basics) and C (staffing) leaves.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel

from grip.access.fields import in_class, nested
from grip.access.types import DataClass

_A = in_class(DataClass.ASSIGNMENT_BASIC)
_C = in_class(DataClass.STAFFING)


class WiesPlacement(BaseModel):
    """A person on a role, for a period. No percentage, no amount."""

    id: Annotated[str, _C]
    person_email: Annotated[str, _C]
    start_date: Annotated[date, _C]
    end_date: Annotated[date, _C]


class WiesRole(BaseModel):
    """A role on an assignment: a personnel budget line, or its open remainder."""

    id: Annotated[str, _C]
    url: Annotated[str, _A]
    description: Annotated[str, _C]
    start_date: Annotated[date | None, _C]
    end_date: Annotated[date | None, _C]
    # Size of the role as a decimal string. Wies turns it into hours per week.
    fte: Annotated[str, _C]
    open: Annotated[bool, _C]
    placements: Annotated[list[WiesPlacement], nested()]


class WiesAssignment(BaseModel):
    id: Annotated[str, _A]
    url: Annotated[str, _A]
    name: Annotated[str, _A]
    status: Annotated[str, _A]
    start_date: Annotated[date | None, _A]
    end_date: Annotated[date | None, _A]
    client_tooi_uri: Annotated[str | None, _A]
    owner_email: Annotated[str | None, _A]
    roles: Annotated[list[WiesRole], nested()]


class WiesExport(BaseModel):
    generated_at: Annotated[datetime, _A]
    instance_name: Annotated[str, _A]
    instance_base_uri: Annotated[str, _A]
    assignments: Annotated[list[WiesAssignment], nested()]


# --- Reconciliation of persons (beheerder only; not part of the export) --------


class PersonProposal(BaseModel):
    """One proposed change to grip's persons, for the beheerder to confirm."""

    action: Literal["add", "deactivate", "reactivate", "rename"]
    email: str
    name: str
    # Present for a person grip already has.
    person_id: UUID | None = None
    # What grip has now, for a rename.
    current_name: str | None = None
    reason: str
    # From Wies, to help the beheerder recognise the person.
    suborganization: str | None = None
    skills: list[str] = []


class ReconciliationProposal(BaseModel):
    configured: bool
    fetched_at: datetime | None = None
    wies_colleagues: int = 0
    proposals: list[PersonProposal] = []
    # Why nothing is proposed, when that needs saying.
    note: str | None = None


class ConfirmedChange(BaseModel):
    action: Literal["add", "deactivate", "reactivate", "rename"]
    email: str


class ReconciliationConfirmation(BaseModel):
    changes: list[ConfirmedChange]


class AppliedChange(BaseModel):
    action: str
    email: str
    person_id: UUID | None = None
    applied: bool
    # Why a confirmed change was not applied (no longer proposed by Wies).
    reason: str | None = None


class ReconciliationResult(BaseModel):
    applied: list[AppliedChange]
