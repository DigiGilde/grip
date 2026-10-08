"""Schemas for the roles of a person. A person's roles are staffing (class C)."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

C = DataClass.STAFFING


class PersonRoleOut(BaseModel):
    role_id: Annotated[UUID, in_class(C)]
    name: Annotated[str, in_class(C)]
    # wies: from the person's skills in Wies. manual: set by the beheerder.
    source: Annotated[str, in_class(C)]
    is_active: Annotated[bool, in_class(C)]


class PersonRolesOut(BaseModel):
    person_id: Annotated[UUID, in_class(C)]
    items: Annotated[list[PersonRoleOut], nested()]


class PersonRolesSet(BaseModel):
    # The roles the person has after this; what is not listed is taken away.
    role_ids: list[UUID]


class RoleProposalOut(BaseModel):
    action: Literal["add_role", "drop_role"]
    person_id: UUID
    person_name: str
    role_id: UUID
    role_name: str
    reason: str


class RoleProposalList(BaseModel):
    configured: bool
    proposals: list[RoleProposalOut] = []
    note: str | None = None


class ConfirmedRoleChange(BaseModel):
    action: Literal["add_role", "drop_role"]
    person_id: UUID
    role_id: UUID


class RoleProposalConfirmation(BaseModel):
    changes: list[ConfirmedRoleChange]


class AppliedRoleChange(BaseModel):
    action: str
    person_id: UUID
    role_id: UUID
    # False when Wies no longer gives rise to the change.
    applied: bool


class RoleProposalResult(BaseModel):
    applied: list[AppliedRoleChange]
