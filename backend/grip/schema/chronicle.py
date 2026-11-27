"""Response shapes of the chronicle of an assignment.

Every field carries the class it has on the live screens, at every moment: what
an assignment is called and where it stands is class A, what a line needs in
staffing is class C, money and the content of a quote is class B. A moment says
that something happened to whoever may read the assignment; what it said takes
B. One exception: the dates, the acceptance and the approvals of a quote take B
in a stand, also where a live route has them as A.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested
from grip.schema.quotes import QuoteContentOut
from grip.schema.tasks import CourseOut

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)
C = in_class(DataClass.STAFFING)


class MomentOut(BaseModel):
    seq: Annotated[int, A]
    # When it was recorded, not the day it counts from.
    occurred_at: Annotated[datetime, A]
    fact: Annotated[str, A]
    title: Annotated[str, A]
    decision: Annotated[bool, A]
    actor_name: Annotated[str | None, A] = None
    # person, guest, peer or system: who established it where no name says so.
    actor_kind: Annotated[str | None, A] = None
    effective_on: Annotated[date | None, B] = None
    # The fact in the form it was established; the title is for who may not.
    statement: Annotated[str, B]
    lines: Annotated[list[str], B] = Field(default_factory=list)
    erased: Annotated[bool, A] = False


class MomentsOut(BaseModel):
    items: Annotated[list[MomentOut], nested()] = Field(default_factory=list)


class StandAssignmentOut(BaseModel):
    name: Annotated[str, A]
    status: Annotated[str, A]
    status_label: Annotated[str, A]
    kind: Annotated[str, A]
    owner_name: Annotated[str | None, A] = None
    client_name: Annotated[str | None, A] = None
    start_date: Annotated[date | None, A] = None
    end_date: Annotated[date | None, A] = None
    notes: Annotated[str | None, A] = None
    quote_date: Annotated[date | None, B] = None
    verbal_agreement_note: Annotated[str | None, A] = None
    quoted_amount_cents: Annotated[int | None, B] = None


class LaterKnownOut(BaseModel):
    """Recorded later, while it counts from a day at or before this moment, or
    corrects a date that did."""

    seq: Annotated[int, A]
    title: Annotated[str, A]
    statement: Annotated[str, B]
    effective_on: Annotated[date, B]


class RestatementOut(BaseModel):
    """A later moment took a typed text out of this one (ADR 0057)."""

    seq: Annotated[int, A]
    occurred_at: Annotated[datetime, A]
    # What was taken out, by its label; never the text.
    removed: Annotated[list[str], A] = Field(default_factory=list)


class RemovableTextOut(BaseModel):
    """A typed text of this moment that may be taken out of it."""

    key: Annotated[str, A]
    label: Annotated[str, A]
    # A name or a note is A, a reason under a moment B: the stricter one.
    text: Annotated[str, B]
    # Quotes that hold the text too: they stay as they were made.
    kept: Annotated[list[str], A] = Field(default_factory=list)


class StandLineOut(BaseModel):
    id: Annotated[UUID, A]
    description: Annotated[str, A]
    kind: Annotated[str, A]
    position: Annotated[int, A]
    role: Annotated[str | None, C] = None
    fte: Annotated[Decimal | None, C] = None
    start_date: Annotated[date | None, C] = None
    end_date: Annotated[date | None, C] = None
    rate_category: Annotated[str | None, B] = None
    amount_cents: Annotated[int | None, B] = None
    year: Annotated[int | None, B] = None
    budgeted_cents: Annotated[int | None, B] = None
    # What this moment did to the line.
    change: Annotated[Literal["added", "changed"] | None, A] = None


class StandBudgetOut(BaseModel):
    lines: Annotated[list[StandLineOut], nested()] = Field(default_factory=list)
    # The names of the lines this moment removed.
    removed: Annotated[list[str], A] = Field(default_factory=list)
    subtotals_by_year: Annotated[dict[str, int], B] = Field(default_factory=dict)
    total_budgeted_cents: Annotated[int | None, B] = None
    # The total at the previous moment, when it differs.
    previous_total_cents: Annotated[int | None, B] = None
    pricing_error: Annotated[str | None, B] = None


class StandApprovalOut(BaseModel):
    status: Annotated[str, B]
    requested_by_name: Annotated[str | None, B] = None
    requested_at: Annotated[datetime, B]
    decided_by_name: Annotated[str | None, B] = None
    decided_at: Annotated[datetime | None, B] = None
    withdrawn_by_name: Annotated[str | None, B] = None
    withdrawn_at: Annotated[datetime | None, B] = None
    request_note: Annotated[str | None, B] = None
    decision_note: Annotated[str | None, B] = None
    self_approved: Annotated[bool, B] = False


class StandInvitationOut(BaseModel):
    """Where a signing link stood at this moment. As the live route gives it,
    without what opens the link."""

    # invited | opened | signed | expired | withdrawn
    state: Annotated[str, B]
    expires_at: Annotated[datetime | None, B] = None
    opened_at: Annotated[datetime | None, B] = None
    used_at: Annotated[datetime | None, B] = None
    withdrawn_at: Annotated[datetime | None, B] = None


class StandOfferOut(BaseModel):
    channel: Annotated[str, B]
    # An invited address only for whoever manages the assignment.
    recipient: Annotated[str | None, B] = None
    offered_at: Annotated[datetime, B]
    offered_by_name: Annotated[str | None, B] = None
    # Only for whoever manages the assignment.
    invitation: Annotated[StandInvitationOut | None, nested()] = None


class StandAcceptanceOut(BaseModel):
    signer_name: Annotated[str, B]
    form: Annotated[str, B]
    signed_at: Annotated[datetime, B]
    organisation_name: Annotated[str | None, B] = None
    recorded_by_name: Annotated[str | None, B] = None


class StandRejectionOut(BaseModel):
    reason: Annotated[str | None, B] = None
    rejected_at: Annotated[datetime, B]
    recorded_by_name: Annotated[str | None, B] = None


class StandQuoteOut(BaseModel):
    id: Annotated[UUID, A]
    reference: Annotated[str | None, A] = None
    status: Annotated[str, A]
    status_label: Annotated[str, A]
    # This moment changed the quote or what hangs from it.
    changed: Annotated[bool, A] = False
    total_cents: Annotated[int, B]
    valid_until: Annotated[date | None, B] = None
    issued_at: Annotated[datetime, B]
    snapshot_hash: Annotated[str, B]
    document_sha256: Annotated[str | None, B] = None
    has_document: Annotated[bool, B] = False
    approvals: Annotated[list[StandApprovalOut], nested()] = Field(default_factory=list)
    offers: Annotated[list[StandOfferOut], nested()] = Field(default_factory=list)
    acceptance: Annotated[StandAcceptanceOut | None, nested()] = None
    rejection: Annotated[StandRejectionOut | None, nested()] = None
    content: Annotated[QuoteContentOut | None, nested()] = None


class StandOut(BaseModel):
    moment: Annotated[MomentOut, nested()]
    previous_seq: Annotated[int | None, A] = None
    next_seq: Annotated[int | None, A] = None
    assignment: Annotated[StandAssignmentOut, nested()]
    # Told to nobody in particular; no one's turn once the case has started.
    course: Annotated[CourseOut | None, nested()] = None
    # What changed around the case since the previous moment, without a value.
    outside: Annotated[list[str], A] = Field(default_factory=list)
    # The same with the amount, the day and what changed in the rates. For who
    # reads this, it replaces the list above.
    outside_values: Annotated[list[str], B] = Field(default_factory=list)
    later_known: Annotated[list[LaterKnownOut], nested()] = Field(default_factory=list)
    restated: Annotated[list[RestatementOut], nested()] = Field(default_factory=list)
    budget: Annotated[StandBudgetOut | None, nested()] = None
    quotes: Annotated[list[StandQuoteOut], nested()] = Field(default_factory=list)
    # Values of a fact up to here were erased: this stand is not whole.
    incomplete: Annotated[bool, A] = False
    # Only for who may take a text out of a moment.
    removable_texts: Annotated[list[RemovableTextOut] | None, nested()] = None


class RestateIn(BaseModel):
    """The typed texts to take out of a moment, by key."""

    columns: list[str]


class RestatedStandOut(BaseModel):
    """The moment after a text was taken out of it."""

    stand: Annotated[StandOut, nested()]
    # Quotes that hold a text that was taken out: they stay as they were made.
    kept: Annotated[list[str], A] = Field(default_factory=list)
