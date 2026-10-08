"""Shapes of the signing-link routes: what an invited signer sees and sends.

A signer sees exactly one quote, in full. Its content is class B and the
rest class A; the decider grants a guest both, for that quote only.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested
from grip.schema.quotes import QuoteContentOut

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)


class SigningQuoteOut(BaseModel):
    id: Annotated[UUID, A]
    uri: Annotated[str, A]
    reference: Annotated[str | None, A] = None
    status: Annotated[str, A]
    issued_at: Annotated[datetime, A]
    contractor_name: Annotated[str, A]
    client_name: Annotated[str | None, A] = None
    snapshot_hash: Annotated[str, B]
    # The kept PDF the signer is shown: its hash, and how it came to be.
    document_sha256: Annotated[str | None, B] = None
    document_fixed_at: Annotated[datetime | None, B] = None
    document_origin: Annotated[str | None, B] = None
    document_note: Annotated[str | None, B] = None
    content: Annotated[QuoteContentOut | None, nested()] = None
    # The moment of the decision, once there is one.
    decided_at: Annotated[datetime | None, A] = None


class SigningInvitationOut(BaseModel):
    quote_id: Annotated[UUID, A]
    reference: Annotated[str | None, A] = None
    assignment_name: Annotated[str, A]
    status: Annotated[str, A]
    issued_at: Annotated[datetime, A]
    valid_until: Annotated[date | None, B] = None
    expires_at: Annotated[datetime | None, A] = None


class SigningInvitationListOut(BaseModel):
    invitations: Annotated[list[SigningInvitationOut], nested()] = Field(
        default_factory=list
    )


class SignAcceptIn(BaseModel):
    # Hash of the quote as it was shown to the signer.
    quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    signer_function: str | None = Field(default=None, max_length=255)
    # Only needed when the assignment names no client organisation.
    organisation_name: str | None = Field(default=None, max_length=255)
    # The signer states explicitly that they may sign for the organisation.
    confirm_mandate: bool


class SignRejectIn(BaseModel):
    quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str | None = Field(default=None, max_length=2000)
