"""Schemas for counterparty organisations."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class

A = DataClass.ASSIGNMENT_BASIC


class OrganisationOut(BaseModel):
    id: Annotated[UUID, in_class(A)]
    name: Annotated[str, in_class(A)]
    tooi_uri: Annotated[str | None, in_class(A)]
    unit_key: Annotated[str | None, in_class(A)]
    instance_uri: Annotated[str | None, in_class(A)]


class OrganisationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tooi_uri: str | None = Field(default=None, max_length=500)
    unit_key: str | None = Field(default=None, max_length=100)
    instance_uri: str | None = Field(default=None, max_length=500)
