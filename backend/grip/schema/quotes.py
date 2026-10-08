"""Response and request shapes of the quote routes.

Every response field carries one data class. A quote's existence, status and
dates are class A (assignment basics); its content, hash and who signed are
class B (assignment financial).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)


class YearRate(BaseModel):
    year: Annotated[int, B]
    monthly_rate_cents: Annotated[int, B]


class YearSubtotal(BaseModel):
    year: Annotated[int, B]
    amount_cents: Annotated[int, B]


class QuoteLineOut(BaseModel):
    position: Annotated[int, B]
    description: Annotated[str, B]
    kind: Annotated[str, B]
    role: Annotated[str | None, B] = None
    fte: Annotated[str | None, B] = None
    rate_category: Annotated[str | None, B] = None
    # The scales that bill in this category, as on the rate leaflet.
    scales: Annotated[list[int], B] = Field(default_factory=list)
    start_date: Annotated[date | None, B] = None
    end_date: Annotated[date | None, B] = None
    # For a fixed line: the year it belongs to.
    year: Annotated[int | None, B] = None
    # One entry per rate year the line touches.
    monthly_rates: Annotated[list[YearRate], nested()] = Field(default_factory=list)
    amount_cents: Annotated[int, B]


class QuoteContentOut(BaseModel):
    """The content of a quote: a preview, or the frozen snapshot of an issued one."""

    name: Annotated[str, B]
    context_refs: Annotated[list[str], B] = Field(default_factory=list)
    lines: Annotated[list[QuoteLineOut], nested()] = Field(default_factory=list)
    subtotals_per_year: Annotated[list[YearSubtotal], nested()] = Field(
        default_factory=list
    )
    total_cents: Annotated[int, B]
    valid_until: Annotated[date | None, B] = None
    conditions: Annotated[str | None, B] = None
    # The organisation that sends the quote.
    sender: Annotated[str | None, B] = None
    # The client's own reference ("uw kenmerk"), when one was given.
    client_reference: Annotated[str | None, B] = None


class QuotePreviewOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    assignment_status: Annotated[str, A]
    # Whether a quote can be issued in the current status of the assignment.
    can_issue: Annotated[bool, A]
    # Whether the person asking is the one who may issue it.
    may_issue: Annotated[bool, A] = False
    # Why the content is missing, when it cannot be built.
    problem: Annotated[str | None, A] = None
    content: Annotated[QuoteContentOut | None, nested()] = None
    # The agreed amount on the assignment, when one was entered.
    quoted_amount_cents: Annotated[int | None, B] = None
    # Agreed amount minus the budget total; None without an agreed amount.
    difference_cents: Annotated[int | None, B] = None
    # Conditions the instance proposes for a new quote.
    default_conditions: Annotated[str | None, A] = None


class AcceptanceOut(BaseModel):
    form: Annotated[str, A]
    signed_at: Annotated[datetime, A]
    signer_name: Annotated[str, B]
    signer_function: Annotated[str | None, B] = None
    organisation_name: Annotated[str | None, B] = None
    has_document: Annotated[bool, B] = False


class RejectionOut(BaseModel):
    rejected_at: Annotated[datetime, A]
    reason: Annotated[str | None, B] = None


class QuoteSummaryOut(BaseModel):
    id: Annotated[UUID, A]
    uri: Annotated[str, A]
    # The reference people quote, e.g. "DG-2026-0007".
    reference: Annotated[str | None, A] = None
    assignment_id: Annotated[UUID, A]
    status: Annotated[str, A]
    issued_at: Annotated[datetime, A]
    issued_by_name: Annotated[str | None, A] = None
    total_cents: Annotated[int, B]
    snapshot_hash: Annotated[str, B]
    valid_until: Annotated[date | None, B] = None
    acceptance: Annotated[AcceptanceOut | None, nested()] = None
    rejection: Annotated[RejectionOut | None, nested()] = None


class OfferInvitationOut(BaseModel):
    """The signing link behind an offer, for whoever manages the assignment.

    The link opens only for the invited person, after logging in with the
    invited email address, and only this one quote.
    """

    id: Annotated[UUID, B]
    # Path of the page the invited person opens; the frontend puts its own
    # origin in front.
    signing_path: Annotated[str, B]
    expires_at: Annotated[datetime | None, B] = None
    opened_at: Annotated[datetime | None, B] = None
    used_at: Annotated[datetime | None, B] = None
    withdrawn_at: Annotated[datetime | None, B] = None
    # invited | opened | signed | expired | withdrawn
    state: Annotated[str, B]


class OfferOut(BaseModel):
    """One time the quote was offered to the client, and through which channel."""

    id: Annotated[UUID, B]
    # client_instance, signing_link or document.
    channel: Annotated[str, B]
    # The client's instance, the invited email address, or nothing.
    recipient: Annotated[str | None, B] = None
    offered_at: Annotated[datetime, B]
    offered_by_name: Annotated[str | None, B] = None
    # For the channel client_instance: pending, sent or refused.
    delivery: Annotated[str | None, B] = None
    # For the channel signing_link, and only for who manages the assignment.
    invitation: Annotated[OfferInvitationOut | None, nested()] = None


class ChannelOut(BaseModel):
    """A channel the quote can be offered through, or why it cannot."""

    channel: Annotated[str, B]
    available: Annotated[bool, B]
    reason: Annotated[str | None, B] = None
    suggested: Annotated[bool, B] = False


class QuoteDetailOut(QuoteSummaryOut):
    content: Annotated[QuoteContentOut | None, nested()] = None
    # How and when the quote was put before the client. Issuing alone sends
    # nothing; an offer does.
    offers: Annotated[list[OfferOut], nested()] = Field(default_factory=list)
    channels: Annotated[list[ChannelOut], nested()] = Field(default_factory=list)


class OfferQuoteIn(BaseModel):
    channel: str = Field(pattern=r"^(client_instance|signing_link|document)$")
    # For the signing link: who is invited to sign, and until when.
    email: str | None = Field(
        default=None, min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$"
    )
    expires_at: datetime | None = None


class QuoteListOut(BaseModel):
    # Whether the person asking may invite signers and record a decision.
    may_manage: Annotated[bool, A] = False
    quotes: Annotated[list[QuoteSummaryOut], nested()] = Field(default_factory=list)


class InvitationOut(BaseModel):
    """An invitation to sign. Only whoever manages the assignment sees these."""

    id: Annotated[UUID, B]
    email: Annotated[str, B]
    created_at: Annotated[datetime, B]
    expires_at: Annotated[datetime | None, B] = None
    used_at: Annotated[datetime | None, B] = None


class InvitationListOut(BaseModel):
    invitations: Annotated[list[InvitationOut], nested()] = Field(default_factory=list)


class IssueQuoteIn(BaseModel):
    valid_until: date | None = None
    conditions: str | None = Field(default=None, max_length=5000)
    # The client's own reference, such as an order or case number.
    client_reference: str | None = Field(default=None, max_length=100)


class InviteSignerIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    expires_at: datetime | None = None


class RecordRejectionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


def content_from_snapshot(snapshot: dict[str, Any]) -> QuoteContentOut:
    """A snapshot (or a preview in the same shape) as response content."""

    def cents(money: Any) -> int:
        return int(money["amount_cents"]) if isinstance(money, dict) else 0

    lines = []
    for line in snapshot.get("lines", []):
        period = line.get("period") or {}
        if "monthly_rate" in line:
            # One rate for the whole line: say so for every year it touches.
            start, end = period.get("start_date"), period.get("end_date")
            years = (
                range(int(start[:4]), int(end[:4]) + 1) if start and end else range(0)
            )
            rates = [
                YearRate(year=year, monthly_rate_cents=cents(line["monthly_rate"]))
                for year in years
            ]
        else:
            rates = [
                YearRate(
                    year=int(entry["year"]),
                    monthly_rate_cents=cents(entry["monthly_rate"]),
                )
                for entry in line.get("monthly_rates_per_year", [])
            ]
        lines.append(
            QuoteLineOut(
                position=line.get("position", 0),
                description=line.get("description", ""),
                kind=line.get("kind", ""),
                role=line.get("role"),
                fte=line.get("fte"),
                rate_category=line.get("rate_category"),
                scales=[v for v in line.get("scales") or [] if isinstance(v, int)],
                start_date=period.get("start_date"),
                end_date=period.get("end_date"),
                year=line.get("year"),
                monthly_rates=rates if line.get("kind") == "personnel" else [],
                amount_cents=cents(line.get("amount")),
            )
        )
    return QuoteContentOut(
        name=snapshot.get("name", ""),
        context_refs=list(snapshot.get("context_refs") or []),
        lines=lines,
        subtotals_per_year=[
            YearSubtotal(year=int(entry["year"]), amount_cents=cents(entry["amount"]))
            for entry in snapshot.get("subtotals_per_year", [])
        ],
        total_cents=cents(snapshot.get("total")),
        valid_until=snapshot.get("valid_until"),
        conditions=snapshot.get("conditions"),
        sender=snapshot.get("sender"),
        client_reference=snapshot.get("client_reference"),
    )
