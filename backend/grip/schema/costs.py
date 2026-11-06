"""Cost items, invoice lines and coverage (class B)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

_FIN = in_class(DataClass.ASSIGNMENT_FINANCIAL)


class AttachmentOut(BaseModel):
    """A document attached to an invoice line: the received invoice itself."""

    id: Annotated[UUID, _FIN]
    filename: Annotated[str, _FIN]
    content_type: Annotated[str, _FIN]
    size_bytes: Annotated[int, _FIN]
    uploaded_at: Annotated[datetime, _FIN]
    uploaded_by_name: Annotated[str | None, _FIN]


class InvoiceLineOut(BaseModel):
    id: Annotated[UUID, _FIN]
    version: Annotated[int, _FIN] = 1
    reference: Annotated[str | None, _FIN]
    description: Annotated[str | None, _FIN]
    kind: Annotated[str, _FIN]
    amount_cents: Annotated[int, _FIN]
    period: Annotated[date | None, _FIN]
    attachments: Annotated[list[AttachmentOut], nested()]


class ExecutorLineOut(BaseModel):
    """An invoice line of a cost item another organisation keeps, as read
    there just now. It is only read here."""

    reference: Annotated[str | None, _FIN]
    description: Annotated[str | None, _FIN]
    kind: Annotated[str, _FIN]
    amount_cents: Annotated[int, _FIN]
    period: Annotated[date | None, _FIN]


class CoverageOut(BaseModel):
    id: Annotated[UUID, _FIN]
    # Counts the changes of the record; a form sends it back with its save.
    version: Annotated[int, _FIN] = 1
    budget_line_id: Annotated[UUID, _FIN]
    budget_line_description: Annotated[str, _FIN]
    assignment_id: Annotated[UUID, _FIN]
    assignment_name: Annotated[str, _FIN]
    pct: Annotated[Decimal, _FIN]
    # Null while the cost item cannot be counted (a reference not read).
    amount_cents: Annotated[int | None, _FIN]
    may_edit: Annotated[bool, _FIN]


class CostItemOut(BaseModel):
    id: Annotated[UUID, _FIN]
    # Counts the changes of the record; a form sends it back with its save.
    version: Annotated[int, _FIN] = 1
    description: Annotated[str, _FIN]
    # Null for a reference whose executor could not be read.
    budgeted_cents: Annotated[int | None, _FIN]
    # R6: realised plus estimated invoice lines. These amounts are null
    # while the cost item cannot be counted (ADR 0052).
    forecast_cents: Annotated[int | None, _FIN]
    actual_cents: Annotated[int | None, _FIN]
    estimate_cents: Annotated[int | None, _FIN]
    # Budgeted minus the expected total; negative means over budget.
    variance_cents: Annotated[int | None, _FIN]
    # R8. Null when the stored percentages add up to more than 100.
    covered_cents: Annotated[int | None, _FIN]
    uncovered_cents: Annotated[int | None, _FIN]
    pct_total: Annotated[Decimal, _FIN]
    # The share no budget line covers. Null above 100 percent.
    uncovered_pct: Annotated[Decimal | None, _FIN]
    # Share covered by budget lines of assignments the asker may not see.
    hidden_coverage_pct: Annotated[Decimal, _FIN]
    # A reference (ADR 0052): the organisation that keeps the cost item,
    # and what the item stands for now: waiting, refused, undelivered,
    # found or unreachable. For a found one, what became of a later request
    # to change it, while the executor has not applied it.
    executor_organisation_id: Annotated[UUID | None, _FIN] = None
    executor_name: Annotated[str | None, _FIN] = None
    reference_state: Annotated[str | None, _FIN] = None
    change_state: Annotated[str | None, _FIN] = None
    # At the executor: the organisation that asked for the cost item.
    requested_by_name: Annotated[str | None, _FIN] = None
    invoice_lines: Annotated[list[InvoiceLineOut], nested()]
    # The invoice lines of a reference, as read at the executor.
    executor_lines: Annotated[list[ExecutorLineOut], nested()] = []
    coverages: Annotated[list[CoverageOut], nested()]
    may_edit: Annotated[bool, _FIN]


class ExecutorOptionOut(BaseModel):
    """An organisation that can be asked to make a cost item."""

    organisation_id: Annotated[UUID, _FIN]
    name: Annotated[str, _FIN]


class BudgetLineOptionOut(BaseModel):
    budget_line_id: Annotated[UUID, _FIN]
    description: Annotated[str, _FIN]
    kind: Annotated[str, _FIN]
    assignment_id: Annotated[UUID, _FIN]
    assignment_name: Annotated[str, _FIN]


class CostItemCreate(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    budgeted_cents: int = Field(default=0, ge=0)
    # Another organisation makes the expense and keeps the cost item.
    executor_organisation_id: UUID | None = None
    # A day in the period of the expense, asked of the executor.
    period: date | None = None


class CostItemUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    budgeted_cents: int | None = Field(default=None, ge=0)
    # Left out keeps the executor. An own item without invoices can get one;
    # a reference keeps the one it has.
    executor_organisation_id: UUID | None = None


class InvoiceLineCreate(BaseModel):
    kind: Literal["actual", "estimate"]
    amount_cents: int
    reference: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    # Any day in the period the amount belongs to.
    period: date | None = None


class CoverageUpdate(BaseModel):
    pct: Decimal = Field(gt=0, le=100)


class InvoiceLineUpdate(BaseModel):
    # Only the fields sent change. Reference, description and period may be
    # sent as null to clear them.
    kind: Literal["actual", "estimate"] | None = None
    amount_cents: int | None = None
    reference: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    period: date | None = None
