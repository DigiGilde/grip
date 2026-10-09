"""Peers: other grip instances and corpus systems this instance talks to."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from grip.access import DataClass, in_class

M = DataClass.MASTER_DATA

PeerRoleName = Literal["counterpart", "parent", "child", "corpus"]


def _clean_grants(value: dict[str, str]) -> dict[str, str]:
    return {
        service.strip(): grant.strip()
        for service, grant in value.items()
        if service.strip() and grant.strip()
    }


class PeerIn(BaseModel):
    # The FSC peer id: the serial number in the certificate of the peer.
    peer_id: str = Field(min_length=1, max_length=64, pattern=r"^[0-9A-Za-z._:-]+$")
    name: str = Field(min_length=1, max_length=200)
    organisation_tooi_uri: str = Field(default="", max_length=500)
    # Base of the URIs the peer mints: an instance base or a corpus base.
    base_uri: str = Field(min_length=1, max_length=500, pattern=r"^https?://")
    role: PeerRoleName
    # FSC service name to the grant hash of the contract with this peer.
    grant_hashes: dict[str, str] = Field(default_factory=dict)
    financial_inspection: bool = False
    is_active: bool = True

    @field_validator("grant_hashes")
    @classmethod
    def _grants(cls, value: dict[str, str]) -> dict[str, str]:
        return _clean_grants(value)

    @field_validator("base_uri")
    @classmethod
    def _base(cls, value: str) -> str:
        return value.strip().rstrip("/")


class PeerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    organisation_tooi_uri: str | None = Field(default=None, max_length=500)
    base_uri: str | None = Field(
        default=None, min_length=1, max_length=500, pattern=r"^https?://"
    )
    role: PeerRoleName | None = None
    grant_hashes: dict[str, str] | None = None
    financial_inspection: bool | None = None
    is_active: bool | None = None

    @field_validator("grant_hashes")
    @classmethod
    def _grants(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return None if value is None else _clean_grants(value)

    @field_validator("base_uri")
    @classmethod
    def _base(cls, value: str | None) -> str | None:
        return None if value is None else value.strip().rstrip("/")


class PeerOut(BaseModel):
    id: Annotated[UUID, in_class(M)]
    # Counts what people changed; a form sends it back with its save.
    version: Annotated[int, in_class(M)] = 1
    peer_id: Annotated[str, in_class(M)]
    name: Annotated[str, in_class(M)]
    organisation_tooi_uri: Annotated[str, in_class(M)]
    base_uri: Annotated[str, in_class(M)]
    role: Annotated[str, in_class(M)]
    grant_hashes: Annotated[dict[str, str], in_class(M)]
    financial_inspection: Annotated[bool, in_class(M)]
    is_active: Annotated[bool, in_class(M)]
    # How many public keys of the peer are known here, and since when.
    key_count: Annotated[int, in_class(M)]
    jwks_fetched_at: Annotated[datetime | None, in_class(M)]
    created_at: Annotated[datetime, in_class(M)]
    updated_at: Annotated[datetime, in_class(M)]


class PeerListOut(BaseModel):
    items: Annotated[list[PeerOut], in_class(M)]
    # The services a grant hash can be recorded for.
    services: Annotated[list[str], in_class(M)]
    outway_configured: Annotated[bool, in_class(M)]


class ConnectionTestOut(BaseModel):
    ok: Annotated[bool, in_class(M)]
    # What happened, in words a beheerder can act on.
    detail: Annotated[str, in_class(M)]
    status_code: Annotated[int | None, in_class(M)]
    key_count: Annotated[int, in_class(M)]
