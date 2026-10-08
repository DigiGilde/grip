"""Internal approval of a quote, and the instance settings behind it."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested
from grip.schema.quotes import QuoteContentOut

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)
M = in_class(DataClass.MASTER_DATA)


class ApprovalRequestOut(BaseModel):
    """One request for approval with its outcome."""

    id: Annotated[UUID, A]
    # requested, approved, sent_back or withdrawn.
    status: Annotated[str, A]
    requested_at: Annotated[datetime, A]
    requested_by_name: Annotated[str | None, A] = None
    request_note: Annotated[str | None, A] = None
    decided_at: Annotated[datetime | None, A] = None
    decided_by_name: Annotated[str | None, A] = None
    decision_note: Annotated[str | None, A] = None
    # The maker approved the own quote, which this instance allows.
    self_approved: Annotated[bool, A] = False
    # Whether the request is about the quote as it is now.
    for_this_version: Annotated[bool, A] = True


class ApprovalStateOut(BaseModel):
    """Where a quote stands with internal approval, and what the reader may do."""

    quote_id: Annotated[UUID, A]
    # Whether this quote needs approval before it can be offered, and why,
    # in words for the screen (for example "vanaf € 100.000").
    approval_required: Annotated[bool, A]
    approval_reason: Annotated[str | None, A] = None
    # none, requested, approved, sent_back or withdrawn.
    status: Annotated[str, A]
    # Whether the quote can be offered as far as approval is concerned, and
    # when not, the message to show.
    may_offer: Annotated[bool, A]
    blocked_message: Annotated[str | None, A] = None
    # Whether anyone holds the right to approve at all.
    approver_available: Annotated[bool, A]
    may_request_approval: Annotated[bool, A] = False
    may_decide_approval: Annotated[bool, A] = False
    may_withdraw: Annotated[bool, A] = False
    current: Annotated[ApprovalRequestOut | None, nested()] = None
    history: Annotated[list[ApprovalRequestOut], nested()] = Field(default_factory=list)


class ApprovalStatesOut(BaseModel):
    """The approval state of every quote of one assignment."""

    items: Annotated[list[ApprovalStateOut], nested()] = Field(default_factory=list)


class RequestApprovalIn(BaseModel):
    # What the maker wants the approver to know.
    note: str | None = Field(default=None, max_length=2000)


class DecideApprovalIn(BaseModel):
    decision: str = Field(pattern=r"^(approve|send_back)$")
    # The hash of the quote the approver saw: the decision is about that
    # version and no other.
    quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str | None = Field(default=None, max_length=2000)


class WaitingApprovalOut(BaseModel):
    """A quote that waits for the reader's approval."""

    quote_id: Annotated[UUID, A]
    quote_reference: Annotated[str | None, A] = None
    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    client_name: Annotated[str | None, A] = None
    requested_at: Annotated[datetime, A]
    requested_by_name: Annotated[str | None, A] = None
    request_note: Annotated[str | None, A] = None
    total_cents: Annotated[int, B]
    snapshot_hash: Annotated[str, B]
    # False when the reader asked for this approval and may not decide on
    # it (four eyes).
    may_decide: Annotated[bool, A] = True


class WaitingApprovalsOut(BaseModel):
    items: Annotated[list[WaitingApprovalOut], nested()] = Field(default_factory=list)


class ApproverQuoteOut(BaseModel):
    """The quote in full, for whoever decides on its approval."""

    quote_id: Annotated[UUID, A]
    quote_reference: Annotated[str | None, A] = None
    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    client_name: Annotated[str | None, A] = None
    issued_at: Annotated[datetime, A]
    issued_by_name: Annotated[str | None, A] = None
    total_cents: Annotated[int, B]
    snapshot_hash: Annotated[str, B]
    content: Annotated[QuoteContentOut | None, nested()] = None
    approval: Annotated[ApprovalStateOut, nested()]


class InstanceSettingOut(BaseModel):
    key: Annotated[str, M]
    value: Annotated[Any, M]
    default: Annotated[Any, M]
    # What the setting does, for the beheerder.
    label: Annotated[str, M]


class InstanceSettingsOut(BaseModel):
    items: Annotated[list[InstanceSettingOut], nested()] = Field(default_factory=list)


class InstanceSettingsIn(BaseModel):
    """Only the keys that are sent are changed."""

    values: dict[str, Any] = Field(default_factory=dict)
