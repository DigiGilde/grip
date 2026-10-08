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
    # The key the two systems share. Wies matches on it first.
    person_uri: Annotated[str | None, _C] = None
    # Null for a prospective colleague, whose address does not exist yet.
    person_email: Annotated[str | None, _C]
    start_date: Annotated[date, _C]
    end_date: Annotated[date, _C]


class WiesRole(BaseModel):
    """A role on an assignment: a personnel budget line, or its open remainder."""

    id: Annotated[str, _C]
    url: Annotated[str, _A]
    # The role of the line, or its own text when it has no role.
    description: Annotated[str, _C]
    # The role from the catalogue, and the public id of the skill in Wies it
    # came from. Wies finds its skill on the id first and on the name second.
    role_name: Annotated[str | None, _C] = None
    role_wies_id: Annotated[str | None, _C] = None
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
    # The public register's own id of the client, for the many organisations
    # and parts of organisations that have no TOOI URI.
    client_registry_id: Annotated[str | None, _A]
    owner_email: Annotated[str | None, _A]
    roles: Annotated[list[WiesRole], nested()]


class WiesExport(BaseModel):
    generated_at: Annotated[datetime, _A]
    instance_name: Annotated[str, _A]
    instance_base_uri: Annotated[str, _A]
    assignments: Annotated[list[WiesAssignment], nested()]


class WiesProposedColleague(BaseModel):
    """A new colleague grip proposes to Wies, or the withdrawal of one."""

    person_uri: Annotated[str, _C]
    # Empty for a withdrawal: the key says which one.
    name: Annotated[str, _C]
    suborganization: Annotated[str | None, _C]
    start_date: Annotated[date | None, _C]
    state: Annotated[Literal["open", "withdrawn"], _C]


class WiesProposedColleagues(BaseModel):
    generated_at: Annotated[datetime, _A]
    instance_base_uri: Annotated[str, _A]
    proposals: Annotated[list[WiesProposedColleague], nested()]


# --- Reconciliation of persons (beheerder only; not part of the export) --------


class PersonProposal(BaseModel):
    """One proposed change to grip's persons, for the beheerder to confirm."""

    # "link": the address from Wies attaches to a person grip already has
    # without one (a prospective colleague).
    action: Literal["add", "deactivate", "reactivate", "rename", "link"]
    email: str
    name: str
    # For "link": how the two were recognised as one person. "uri" is
    # certain, "name" is a suggestion the beheerder has to judge.
    match: Literal["uri", "name"] | None = None
    # Present for a person grip already has.
    person_id: UUID | None = None
    # What grip has now, for a rename.
    current_name: str | None = None
    reason: str
    # From Wies, to help the beheerder recognise the person.
    suborganization: str | None = None
    skills: list[str] = []


class OutgoingProposalState(BaseModel):
    person_id: UUID
    name: str
    suborganization: str | None = None
    start_date: date | None = None
    state: Literal["open", "confirmed", "declined", "withdrawn"]


class ReconciliationProposal(BaseModel):
    configured: bool
    fetched_at: datetime | None = None
    wies_colleagues: int = 0
    proposals: list[PersonProposal] = []
    # Why nothing is proposed, when that needs saying.
    note: str | None = None
    # New colleagues grip proposed to Wies, with what Wies answered.
    outgoing: list[OutgoingProposalState] = []


class ConfirmedChange(BaseModel):
    action: Literal["add", "deactivate", "reactivate", "rename", "link"]
    email: str
    # For "link": the person the address attaches to.
    person_id: UUID | None = None


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
