"""Deciding on a quote that another instance sent."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class

A = DataClass.ASSIGNMENT_BASIC


class ReceivedQuoteAccept(BaseModel):
    # The function the signer holds, as it should appear with the signature.
    signer_function: str | None = Field(default=None, max_length=255)


class ReceivedQuoteReject(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class ReceivedQuoteDecisionOut(BaseModel):
    quote_id: Annotated[UUID, in_class(A)]
    assignment_id: Annotated[UUID, in_class(A)]
    decision: Annotated[str, in_class(A)]
    decided_at: Annotated[datetime, in_class(A)]
    # Whether a message to the contractor was queued.
    sent_to_contractor: Annotated[bool, in_class(A)]
