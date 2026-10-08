"""Schemas for the Functiegebouw Rijk. Public information: master data."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

LISTS = in_class(DataClass.MASTER_DATA)


class FunctionGroupOut(BaseModel):
    id: Annotated[UUID, LISTS]
    family_id: Annotated[UUID, LISTS]
    name: Annotated[str, LISTS]
    scales: Annotated[list[int], LISTS]
    # "schaal 11 t/m 13"
    scales_text: Annotated[str, LISTS]
    source: Annotated[str, LISTS]
    source_url: Annotated[str | None, LISTS] = None
    valid_to: Annotated[date | None, LISTS] = None
    # Changed by a beheerder; a reload of the reference file leaves it alone.
    edited: Annotated[bool, LISTS]


class FunctionFamilyOut(BaseModel):
    id: Annotated[UUID, LISTS]
    name: Annotated[str, LISTS]
    source: Annotated[str, LISTS]
    source_url: Annotated[str | None, LISTS] = None
    valid_to: Annotated[date | None, LISTS] = None
    groups: Annotated[list[FunctionGroupOut], nested()]


class FunctionFrameworkSourceOut(BaseModel):
    """Where the list comes from and when it was read."""

    name: Annotated[str, LISTS]
    source_url: Annotated[str, LISTS]
    read_on: Annotated[date, LISTS]
    reference_families: Annotated[int, LISTS]
    reference_groups: Annotated[int, LISTS]


class FunctionFrameworkOut(BaseModel):
    source: Annotated[FunctionFrameworkSourceOut, nested()]
    families: Annotated[list[FunctionFamilyOut], nested()]
    # The viewer may correct, add and reload.
    can_manage: Annotated[bool, LISTS]


class ReloadOut(BaseModel):
    families_created: Annotated[int, LISTS]
    families_updated: Annotated[int, LISTS]
    groups_created: Annotated[int, LISTS]
    groups_updated: Annotated[int, LISTS]
    groups_kept: Annotated[int, LISTS]


class FunctionFamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FunctionFamilyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    valid_to: date | None = None


class FunctionGroupCreate(BaseModel):
    family_id: UUID
    name: str = Field(min_length=1, max_length=255)
    scales: list[int] = Field(min_length=1, max_length=19)


class FunctionGroupUpdate(BaseModel):
    family_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scales: list[int] | None = Field(default=None, min_length=1, max_length=19)
    valid_to: date | None = None
