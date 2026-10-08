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
