"""Schemas for the role catalogue."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CatalogueRoleOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    # wies | manual
    source: str
    is_active: bool
    # Added on the spot or taken over from free text: for the beheerder to
    # keep, rename or merge.
    needs_review: bool
    # Budget lines that refer to this role.
    usage_count: int
    # Other names the role goes by in the standard texts.
    also_known_as: list[str] = []


class CatalogueRoleList(BaseModel):
    items: list[CatalogueRoleOut]
    # Whether the reader may add a role that is not in the list.
    can_add: bool
    # Whether the reader may rename, switch off, merge and sync.
    can_manage: bool


class CatalogueRoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)


class CatalogueRoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    needs_review: bool | None = None


class CatalogueRoleMerge(BaseModel):
    # The role that stays; the role in the path disappears into it.
    into_id: UUID


class CatalogueRoleMergeResult(BaseModel):
    role: CatalogueRoleOut
    budget_lines_rewritten: int


class RoleSyncRunOut(BaseModel):
    id: UUID
    finished_at: datetime
    # completed | failed
    status: str
    # Counts per outcome: seen, created, adopted, renamed, reactivated,
    # unchanged, deactivated, deleted, conflicts.
    result: dict[str, Any]
    error: str | None


class RoleSyncStatus(BaseModel):
    # Whether the link with Wies is set up; without it the catalogue is kept
    # by hand.
    wies_configured: bool
    last_run: RoleSyncRunOut | None
    roles: int
    needs_review: int
