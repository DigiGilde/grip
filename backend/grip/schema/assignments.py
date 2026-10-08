"""Schemas for assignments.

Who holds a role on an assignment (owner, manager) is class A: it says whom
to contact about the assignment, not who is staffed on it.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
ROSTER = DataClass.STAFFING_ROSTER


class RoleHolderOut(BaseModel):
    person_id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    role: Annotated[str, in_class(A)]


class AssignmentPermissionsOut(BaseModel):
    """What the person asking may do, so the screen offers only that."""

    edit_basic: Annotated[bool, in_class(A)]
    edit_financial: Annotated[bool, in_class(A)]
    edit_staffing: Annotated[bool, in_class(A)]
    read_financial: Annotated[bool, in_class(A)]
    read_staffing: Annotated[bool, in_class(A)]
    # Who is on the team, by name and role: what a team member may see.
    read_roster: Annotated[bool, in_class(A)]


class AssignmentSummaryOut(BaseModel):
    id: Annotated[UUID, in_class(A)]
    uri: Annotated[str, in_class(A)]
    name: Annotated[str, in_class(A)]
    kind: Annotated[str, in_class(A)]
    status: Annotated[str, in_class(A)]
    # potential, active or closed; derived from the status, never stored.
    phase: Annotated[str, in_class(A)]
    # The day the assignment got its current status.
    status_since: Annotated[date | None, in_class(A)]
    # When the assignment was shared with the grip instance of the client;
    # null when it was not.
    shared_with_client_at: Annotated[date | None, in_class(A)]
    client_organisation_id: Annotated[UUID | None, in_class(A)]
    client_name: Annotated[str | None, in_class(A)]
    start_date: Annotated[date | None, in_class(A)]
    end_date: Annotated[date | None, in_class(A)]
    owner_name: Annotated[str | None, in_class(A)]
    quoted_amount_cents: Annotated[int | None, in_class(B)]
    # What a potential assignment may be worth: the total of the latest
    # quote, or the budget while there is no quote. Null for other phases.
    pipeline_amount_cents: Annotated[int | None, in_class(B)]
    # "quote" or "budget"; null when there is no amount.
    pipeline_amount_source: Annotated[str | None, in_class(B)]


class AssignmentListOut(BaseModel):
    items: Annotated[list[AssignmentSummaryOut], nested()]
    can_create: Annotated[bool, in_class(A)]


class AssignmentDetailOut(AssignmentSummaryOut):
    contractor_organisation_id: Annotated[UUID | None, in_class(A)]
    contractor_name: Annotated[str | None, in_class(A)]
    parent_assignment_uri: Annotated[str | None, in_class(A)]
    context_refs: Annotated[list[str], in_class(A)]
    client_contact: Annotated[str | None, in_class(A)]
    quote_date: Annotated[date | None, in_class(A)]
    notes: Annotated[str | None, in_class(A)]
    # What was agreed verbally and when; null without a verbal agreement.
    verbal_agreement_note: Annotated[str | None, in_class(A)]
    verbal_agreement_at: Annotated[date | None, in_class(A)]
    roles: Annotated[list[RoleHolderOut], nested()]
    allowed_transitions: Annotated[list[str], in_class(A)]
    permissions: Annotated[AssignmentPermissionsOut, nested()]


class AssignmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = "external"
    client_organisation_id: UUID | None = None
    client_contact: str | None = Field(default=None, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None
    context_refs: list[str] = Field(default_factory=list)
    owner_id: UUID | None = None


class AssignmentUpdate(BaseModel):
    """Only the fields that are sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = None
    client_organisation_id: UUID | None = None
    client_contact: str | None = Field(default=None, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None
    context_refs: list[str] | None = None
    quoted_amount_cents: int | None = Field(default=None, ge=0)


class TransitionIn(BaseModel):
    target: str
    reason: str | None = Field(default=None, max_length=1000)


class RoleIn(BaseModel):
    role: str


class PersonOptionOut(BaseModel):
    id: Annotated[UUID, in_class(ROSTER)]
    name: Annotated[str, in_class(ROSTER)]


class PersonOptionsOut(BaseModel):
    items: Annotated[list[PersonOptionOut], nested()]
