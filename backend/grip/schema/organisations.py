"""Schemas for organisations: the list clients and contractors are picked from."""

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC


class OrganisationOut(BaseModel):
    id: Annotated[UUID, in_class(A)]
    # The name as the source gives it.
    name: Annotated[str, in_class(A)]
    # The name to show ("Ministerie van ..." for a ministry).
    label: Annotated[str, in_class(A)]
    abbreviation: Annotated[str | None, in_class(A)]
    abbreviations: Annotated[list[str], in_class(A)]
    organisation_types: Annotated[list[str], in_class(A)]
    main_type: Annotated[str | None, in_class(A)]
    # registry | manual
    source: Annotated[str, in_class(A)]
    parent_id: Annotated[UUID | None, in_class(A)]
    # Labels from the top of the hierarchy down to this organisation.
    path: Annotated[list[str], in_class(A)]
    path_label: Annotated[str, in_class(A)]
    tooi_uri: Annotated[str | None, in_class(A)]
    unit_key: Annotated[str | None, in_class(A)]
    instance_uri: Annotated[str | None, in_class(A)]
    source_url: Annotated[str | None, in_class(A)]
    end_date: Annotated[date | None, in_class(A)]


class OrganisationPage(BaseModel):
    items: Annotated[list[OrganisationOut], nested()]
    total: Annotated[int, in_class(A)]
    page: Annotated[int, in_class(A)]
    page_size: Annotated[int, in_class(A)]


class OrganisationCreate(BaseModel):
    """A manual organisation: a name and, for a unit, what it belongs to.

    ``tooi_uri`` and ``unit_key`` are still accepted for callers that register
    a counterparty by its identifiers.
    """

    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None
    instance_uri: str | None = Field(default=None, max_length=500)
    tooi_uri: str | None = Field(default=None, max_length=500)
    unit_key: str | None = Field(default=None, max_length=100)


class OrganisationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    instance_uri: str | None = Field(default=None, max_length=500)
    end_date: date | None = None


class OrganisationTypeCount(BaseModel):
    name: str
    count: int


class OrganisationSyncRunOut(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: datetime
    # completed | failed
    status: str
    source_url: str
    # Counts per outcome: seen, created, updated, unchanged, adopted, closed,
    # deleted, skipped_ended, excluded, duplicate_identifiers.
    result: dict[str, Any]
    error: str | None


class OrganisationSyncStatus(BaseModel):
    # A run is under way in this process. Fetching the register takes minutes.
    running: bool
    running_since: datetime | None
    last_run: OrganisationSyncRunOut | None
    registry_organisations: int
    manual_organisations: int
