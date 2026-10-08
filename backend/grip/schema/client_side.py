"""Shapes of the client side: requests, received quotes and inspection.

Existence, parties, status, dates, context and progress are class A
(assignment basics). Amounts are class B (assignment financial). Nothing
here carries a person's name from the other organisation, except who signed
a quote, which the quote schemas already put in class B.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from grip.access import DataClass, in_class, nested
from grip.schema.quotes import QuoteDetailOut

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)

MAX_CONTEXT_URIS = 50


class ContractorOptionOut(BaseModel):
    # Row id of the peer; what a request names as contractor.
    peer_id: Annotated[UUID, A]
    name: Annotated[str, A]
    base_uri: Annotated[str, A]
    # Whether a request can be delivered: there is a contract for the service.
    reachable: Annotated[bool, A]


class ClientOptionsOut(BaseModel):
    may_request: Annotated[bool, A]
    contractors: Annotated[list[ContractorOptionOut], nested()] = Field(
        default_factory=list
    )
    # Why a request would not reach a contractor, when that is so.
    problem: Annotated[str | None, A] = None


class AssignmentRequestIn(BaseModel):
    contractor_peer_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    start_date: date | None = None
    end_date: date | None = None
    # Node URIs in one or more corpora. May be empty.
    context_uris: list[str] = Field(default_factory=list, max_length=MAX_CONTEXT_URIS)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Geef de aanvraag een naam.")
        return value.strip()

    @field_validator("context_uris")
    @classmethod
    def _uris(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for uri in value:
            uri = uri.strip()
            if not uri.startswith(("https://", "http://")) or len(uri) > 500:
                raise ValueError("Een context-URI begint met https:// of http://.")
            if uri not in cleaned:
                cleaned.append(uri)
        return cleaned


class DeliveryOut(BaseModel):
    """Whether a message reached the other side."""

    operation: Annotated[str, A]
    # pending | sent | rejected | dead
    status: Annotated[str, A]
    queued_at: Annotated[datetime, A]
    sent_at: Annotated[datetime | None, A] = None
    attempts: Annotated[int, A] = 0


class QuoteRefOut(BaseModel):
    id: Annotated[UUID, A]
    status: Annotated[str, A]
    issued_at: Annotated[datetime, A]
    total_cents: Annotated[int, B]


class ClientAssignmentOut(BaseModel):
    id: Annotated[UUID, A]
    uri: Annotated[str, A]
    name: Annotated[str, A]
    status: Annotated[str, A]
    contractor_name: Annotated[str | None, A] = None
    start_date: Annotated[date | None, A] = None
    end_date: Annotated[date | None, A] = None
    created_at: Annotated[datetime, A]
    context_count: Annotated[int, A] = 0
    latest_quote: Annotated[QuoteRefOut | None, nested()] = None
    # Delivery of the request to the contractor; absent when nothing was queued.
    request_delivery: Annotated[DeliveryOut | None, nested()] = None


class ClientAssignmentListOut(BaseModel):
    may_request: Annotated[bool, A] = False
    items: Annotated[list[ClientAssignmentOut], nested()] = Field(default_factory=list)


class ClientAssignmentDetailOut(ClientAssignmentOut):
    description: Annotated[str | None, A] = None
    context_refs: Annotated[list[str], A] = Field(default_factory=list)
    quotes: Annotated[list[QuoteRefOut], nested()] = Field(default_factory=list)
    # Whether the contractor runs an instance this one has a contract with,
    # so progress and spending can be asked for.
    contractor_reachable: Annotated[bool, A] = False
    # Whether the person asking may ask the contractor for the spending.
    may_request_usage: Annotated[bool, A] = False


class ReceivedRequestOut(BaseModel):
    id: Annotated[UUID, A]
    uri: Annotated[str, A]
    name: Annotated[str, A]
    status: Annotated[str, A]
    client_name: Annotated[str | None, A] = None
    start_date: Annotated[date | None, A] = None
    end_date: Annotated[date | None, A] = None
    description: Annotated[str | None, A] = None
    context_count: Annotated[int, A] = 0
    quote_count: Annotated[int, A] = 0
    received_at: Annotated[datetime, A]


class ReceivedRequestListOut(BaseModel):
    items: Annotated[list[ReceivedRequestOut], nested()] = Field(default_factory=list)


class ReceivedQuoteRowOut(BaseModel):
    id: Annotated[UUID, A]
    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    contractor_name: Annotated[str | None, A] = None
    status: Annotated[str, A]
    issued_at: Annotated[datetime, A]
    total_cents: Annotated[int, B]
    # Whether the person asking is the one who may accept or reject it.
    may_decide: Annotated[bool, A] = False


class ReceivedQuoteListOut(BaseModel):
    items: Annotated[list[ReceivedQuoteRowOut], nested()] = Field(default_factory=list)


class ReceivedQuoteDetailOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    contractor_name: Annotated[str | None, A] = None
    may_decide: Annotated[bool, A] = False
    # The quote as the contractor issued it: the frozen snapshot and its hash.
    quote: Annotated[QuoteDetailOut, nested()]
    # The decisions that were queued for the contractor, oldest first.
    deliveries: Annotated[list[DeliveryOut], nested()] = Field(default_factory=list)


class MilestoneOut(BaseModel):
    description: Annotated[str, A]
    due_date: Annotated[date | None, A] = None
    state: Annotated[str | None, A] = None


class ProgressOut(BaseModel):
    # False when the contractor could not be asked; see ``problem``.
    available: Annotated[bool, A]
    problem: Annotated[str | None, A] = None
    fetched_at: Annotated[datetime, A]
    status: Annotated[str | None, A] = None
    as_of: Annotated[date | None, A] = None
    summary: Annotated[str | None, A] = None
    milestones: Annotated[list[MilestoneOut], nested()] = Field(default_factory=list)
    delivered: Annotated[list[str], A] = Field(default_factory=list)
    not_delivered: Annotated[list[str], A] = Field(default_factory=list)


class BudgetUsageRequestIn(BaseModel):
    # A year, or nothing for the whole period.
    year: int | None = Field(default=None, ge=2000, le=2100)


class UsageLineOut(BaseModel):
    description: Annotated[str, B]
    budgeted_cents: Annotated[int | None, B] = None
    used_cents: Annotated[int | None, B] = None
    available_cents: Annotated[int | None, B] = None


class BudgetUsageOut(BaseModel):
    # False when the contractor did not give the figures; see ``problem``.
    available: Annotated[bool, A]
    # True when the refusal is the contract: financial inspection is not
    # part of what was agreed with the contractor.
    not_in_contract: Annotated[bool, A] = False
    problem: Annotated[str | None, A] = None
    fetched_at: Annotated[datetime, A]
    as_of: Annotated[date | None, B] = None
    year: Annotated[int | None, B] = None
    budgeted_cents: Annotated[int | None, B] = None
    used_cents: Annotated[int | None, B] = None
    available_cents: Annotated[int | None, B] = None
    lines: Annotated[list[UsageLineOut], nested()] = Field(default_factory=list)


class NotDeliveredOut(BaseModel):
    description: Annotated[str, A]
    reason: Annotated[str | None, A] = None


class FinalReportOut(BaseModel):
    received: Annotated[bool, A]
    received_at: Annotated[datetime | None, A] = None
    issued_at: Annotated[datetime | None, A] = None
    period_start: Annotated[date | None, A] = None
    period_end: Annotated[date | None, A] = None
    summary: Annotated[str | None, A] = None
    agreed: Annotated[list[str], A] = Field(default_factory=list)
    delivered: Annotated[list[str], A] = Field(default_factory=list)
    not_delivered: Annotated[list[NotDeliveredOut], nested()] = Field(
        default_factory=list
    )
    total_cost_cents: Annotated[int | None, B] = None
