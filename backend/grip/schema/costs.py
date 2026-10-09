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


class CoverageOut(BaseModel):
    id: Annotated[UUID, _FIN]
    # Counts the changes of the record; a form sends it back with its save.
    version: Annotated[int, _FIN] = 1
    budget_line_id: Annotated[UUID, _FIN]
    budget_line_description: Annotated[str, _FIN]
    assignment_id: Annotated[UUID, _FIN]
    assignment_name: Annotated[str, _FIN]
    pct: Annotated[Decimal, _FIN]
    amount_cents: Annotated[int, _FIN]
    may_edit: Annotated[bool, _FIN]


class CostItemOut(BaseModel):
    id: Annotated[UUID, _FIN]
    # Counts the changes of the record; a form sends it back with its save.
    version: Annotated[int, _FIN] = 1
    description: Annotated[str, _FIN]
    budgeted_cents: Annotated[int, _FIN]
    # R6: realised plus estimated invoice lines.
    forecast_cents: Annotated[int, _FIN]
    actual_cents: Annotated[int, _FIN]
    estimate_cents: Annotated[int, _FIN]
    # Budgeted minus the expected total; negative means over budget.
    variance_cents: Annotated[int, _FIN]
    # R8. Null when the stored percentages add up to more than 100.
    covered_cents: Annotated[int | None, _FIN]
    uncovered_cents: Annotated[int | None, _FIN]
    pct_total: Annotated[Decimal, _FIN]
    # The share no budget line covers. Null above 100 percent.
    uncovered_pct: Annotated[Decimal | None, _FIN]
    # Share covered by budget lines of assignments the asker may not see.
    hidden_coverage_pct: Annotated[Decimal, _FIN]
    invoice_lines: Annotated[list[InvoiceLineOut], nested()]
    coverages: Annotated[list[CoverageOut], nested()]
    may_edit: Annotated[bool, _FIN]


class BudgetLineOptionOut(BaseModel):
    budget_line_id: Annotated[UUID, _FIN]
    description: Annotated[str, _FIN]
    kind: Annotated[str, _FIN]
    assignment_id: Annotated[UUID, _FIN]
    assignment_name: Annotated[str, _FIN]


class CostItemCreate(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    budgeted_cents: int = Field(default=0, ge=0)


class CostItemUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    budgeted_cents: int | None = Field(default=None, ge=0)


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
