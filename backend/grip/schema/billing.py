"""Shapes of the billing data routes.

Billing data follows from a closed month. The total is class B. A line is
one person's inzet: the name is class C and the category, rate and amount
are class D, so a reader of totals does not learn anyone's rate.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = in_class(DataClass.ASSIGNMENT_BASIC)
B = in_class(DataClass.ASSIGNMENT_FINANCIAL)
ROSTER = in_class(DataClass.STAFFING_ROSTER)
C = in_class(DataClass.STAFFING)
D = in_class(DataClass.PERSON_RATE)


class BillingLineOut(BaseModel):
    allocation_id: Annotated[UUID, ROSTER]
    person_name: Annotated[str, ROSTER]
    description: Annotated[str, ROSTER]
    fte_pct: Annotated[Decimal, C]
    category: Annotated[str, D]
    monthly_rate_cents: Annotated[int, D]
    amount_cents: Annotated[int, D]


class BillingDataOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    month: Annotated[str, A]
    closed_at: Annotated[datetime, A]
    total_cents: Annotated[int, B]
    lines: Annotated[list[BillingLineOut], nested()] = Field(default_factory=list)


class BillingExportLineOut(BaseModel):
    description: Annotated[str, ROSTER]
    person_name: Annotated[str, ROSTER]
    fte_pct: Annotated[Decimal, C]
    category: Annotated[str, D]
    monthly_rate_cents: Annotated[int, D]
    amount_cents: Annotated[int, D]


class BillingExportOut(BaseModel):
    id: Annotated[UUID, A]
    assignment_id: Annotated[UUID, A]
    month: Annotated[str, A]
    created_at: Annotated[datetime, A]
    exported_by_name: Annotated[str | None, A] = None
    total_cents: Annotated[int, B]
    lines: Annotated[list[BillingExportLineOut], nested()] = Field(default_factory=list)


class BillingExportListOut(BaseModel):
    exports: Annotated[list[BillingExportOut], nested()] = Field(default_factory=list)


class MonthBillingOut(BaseModel):
    """Where a closed month stands: delivered, invoiced, or neither."""

    month: Annotated[str, B]
    # False when the month was reopened after an invoice was recorded on it.
    closed: Annotated[bool, B]
    # not_delivered | delivered | invoiced
    state: Annotated[str, B]
    deliverable_cents: Annotated[int | None, B] = None
    to_deliver_cents: Annotated[int | None, B] = None
    export_id: Annotated[UUID | None, B] = None
    delivered_at: Annotated[datetime | None, B] = None
    delivered_by_name: Annotated[str | None, B] = None
    delivered_cents: Annotated[int | None, B] = None
    invoice_id: Annotated[UUID | None, B] = None
    invoice_number: Annotated[str | None, B] = None
    invoice_date: Annotated[date | None, B] = None
    invoiced_cents: Annotated[int | None, B] = None
    invoice_on_earlier_delivery: Annotated[bool, B] = False


class OutgoingInvoiceOut(BaseModel):
    """The recorded fact that an invoice was sent."""

    id: Annotated[UUID, B]
    invoice_number: Annotated[str, B]
    invoice_date: Annotated[date, B]
    # The amount on the invoice.
    amount_cents: Annotated[int, B]
    # What was delivered for the months it covers.
    delivered_cents: Annotated[int, B]
    # Invoice amount minus delivered; zero when they agree.
    difference_cents: Annotated[int, B]
    months: Annotated[list[str], B] = Field(default_factory=list)
    export_ids: Annotated[list[UUID], B] = Field(default_factory=list)
    # manual | financial_system
    source: Annotated[str, B]
    note: Annotated[str | None, B] = None
    recorded_at: Annotated[datetime, B]
    recorded_by_name: Annotated[str | None, B] = None
    withdrawn_at: Annotated[datetime | None, B] = None
    withdrawn_by_name: Annotated[str | None, B] = None
    withdrawn_reason: Annotated[str | None, B] = None


class BillingStatusOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    # None means the whole period.
    year: Annotated[int | None, A] = None
    # Whether billing data may be produced in the current status.
    billable: Annotated[bool, A]
    # Whether the person asking may record, correct or withdraw an invoice.
    may_record_invoice: Annotated[bool, A] = False
    deliverable_cents: Annotated[int | None, B] = None
    delivered_cents: Annotated[int, B] = 0
    to_deliver_cents: Annotated[int | None, B] = None
    invoiced_cents: Annotated[int, B] = 0
    to_invoice_cents: Annotated[int, B] = 0
    months: Annotated[list[MonthBillingOut], nested()] = Field(default_factory=list)
    invoices: Annotated[list[OutgoingInvoiceOut], nested()] = Field(
        default_factory=list
    )


class InvoiceProposalOut(BaseModel):
    """What was delivered for a selection of months, to compare an invoice with."""

    months: Annotated[list[str], B] = Field(default_factory=list)
    delivered_cents: Annotated[int, B]


class RecordInvoiceIn(BaseModel):
    export_ids: list[UUID] = Field(min_length=1, max_length=120)
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    amount_cents: int = Field(ge=-(10**13), le=10**13)
    note: str | None = Field(default=None, max_length=2000)


class CorrectInvoiceIn(BaseModel):
    invoice_number: str | None = Field(default=None, min_length=1, max_length=100)
    invoice_date: date | None = None
    amount_cents: int | None = Field(default=None, ge=-(10**13), le=10**13)
    note: str | None = Field(default=None, max_length=2000)
    export_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=120)


class WithdrawInvoiceIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


# -- billing per period -------------------------------------------------------


class BillingTermsOut(BaseModel):
    """How the assignment is billed, as a term of the agreement."""

    # month | quarter
    rhythm: Annotated[str, A]
    # True when the assignment follows the instance and has no terms of its own.
    rhythm_is_default: Annotated[bool, A] = False
    # What the client gave for the invoice: where it goes and its reference.
    details: Annotated[dict[str, str], B] = Field(default_factory=dict)
    # Keys of details the financial administration cannot do without.
    missing_details: Annotated[list[str], B] = Field(default_factory=list)
    names_on_specification: Annotated[bool, B] = False


class BillingTermsIn(BaseModel):
    rhythm: str | None = None
    details: dict[str, str | None] | None = None
    names_on_specification: bool | None = None


class PeriodMonthOut(BaseModel):
    month: Annotated[str, A]
    label: Annotated[str, A]
    # closed | to_close | running | upcoming
    state: Annotated[str, A]
    closed_at: Annotated[datetime | None, A] = None
    closed_by_name: Annotated[str | None, A] = None
    # Established when closed, else what the plan gives.
    amount_cents: Annotated[int | None, B] = None
    delivered_cents: Annotated[int | None, B] = None
    correction_cents: Annotated[int, B] = 0


class BillingDeliveryOut(BaseModel):
    """What went to the financial administration, to whom and how."""

    id: Annotated[UUID, B]
    reference: Annotated[str, B]
    period_key: Annotated[str, B]
    total_cents: Annotated[int, B]
    # mail | self
    via: Annotated[str, B]
    recipient: Annotated[str | None, B] = None
    delivered_at: Annotated[datetime, B]
    delivered_by_name: Annotated[str | None, B] = None
    has_document: Annotated[bool, B] = False
    # queued | sent | failed, when grip mailed it.
    mail_state: Annotated[str | None, B] = None
    invoice_id: Annotated[UUID | None, B] = None
    invoice_number: Annotated[str | None, B] = None


class BillingPeriodOut(BaseModel):
    key: Annotated[str, A]
    # "derde kwartaal 2026" or "juli 2026".
    label: Annotated[str, A]
    # "juli t/m september 2026".
    span: Annotated[str, A]
    # running | to_close | ready | delivered | invoiced
    state: Annotated[str, A]
    months: Annotated[list[PeriodMonthOut], nested()] = Field(default_factory=list)
    # Sum of the closed months.
    closed_cents: Annotated[int | None, B] = None
    # What a delivery made now would hold.
    to_deliver_cents: Annotated[int | None, B] = None
    delivered_cents: Annotated[int, B] = 0
    invoiced_cents: Annotated[int, B] = 0
    deliveries: Annotated[list[BillingDeliveryOut], nested()] = Field(
        default_factory=list
    )
    invoice_numbers: Annotated[list[str], B] = Field(default_factory=list)
    # Whether an invoice can be recorded for what was delivered.
    awaits_invoice: Annotated[bool, B] = False
    last_step_at: Annotated[datetime | None, A] = None


class NextStepOut(BaseModel):
    """The one thing to do now on this assignment."""

    # close_month | deliver | record_invoice | none
    kind: Annotated[str, A]
    month: Annotated[str | None, A] = None
    month_label: Annotated[str | None, A] = None
    period_key: Annotated[str | None, A] = None
    period_label: Annotated[str | None, A] = None
    amount_cents: Annotated[int | None, B] = None
    # For "none": the first day something can be done, and what.
    from_date: Annotated[date | None, A] = None


class BillingOverviewOut(BaseModel):
    assignment_id: Annotated[UUID, A]
    assignment_name: Annotated[str, A]
    client_name: Annotated[str | None, A] = None
    # Whether closing months has started (from a verbal agreement on).
    closing_started: Annotated[bool, A] = False
    # Whether billing data may be produced (from formal acceptance on).
    billable: Annotated[bool, A] = False
    may_close: Annotated[bool, A] = False
    may_deliver: Annotated[bool, A] = False
    may_record_invoice: Annotated[bool, A] = False
    may_edit_terms: Annotated[bool, A] = False
    terms: Annotated[BillingTermsOut, nested()]
    next_step: Annotated[NextStepOut, nested()]
    periods: Annotated[list[BillingPeriodOut], nested()] = Field(default_factory=list)
    # Periods that have not begun, as a count and where they end.
    upcoming_count: Annotated[int, A] = 0
    upcoming_until: Annotated[str | None, A] = None
    closed_cents: Annotated[int | None, B] = None
    delivered_cents: Annotated[int, B] = 0
    invoiced_cents: Annotated[int, B] = 0
    # Whether grip can mail the financial administration.
    can_mail: Annotated[bool, A] = False
    recipient: Annotated[str | None, B] = None


class DeliverIn(BaseModel):
    period_key: str
    # mail | self
    via: str
    note: str | None = None


class PeriodInvoiceIn(BaseModel):
    invoice_number: str
    invoice_date: date
    amount_cents: int
    note: str | None = None


class BatchDeliverIn(BaseModel):
    # Pairs of assignment and period.
    items: list[dict[str, str]]
    via: str
