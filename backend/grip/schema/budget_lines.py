"""Schemas for the budget of an assignment.

A budget line is split over three classes. What it is called is class A. The
demand it expresses (role, size, period) is class C, because a planner needs
it to put people on the line. The money, and the rate category that the
money follows from, is class B.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
D = DataClass.PERSON_RATE
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL


class BudgetLineOut(BaseModel):
    id: Annotated[UUID, in_class(A)]
    assignment_id: Annotated[UUID, in_class(A)]
    # The name of the line as it is shown: the role plus the detail.
    description: Annotated[str, in_class(A)]
    # The free text that tells the line apart; empty when the role says it
    # all. This is what the form edits.
    detail: Annotated[str, in_class(A)] = ""
    kind: Annotated[str, in_class(A)]
    position: Annotated[int, in_class(A)]
    role: Annotated[str | None, in_class(C)]
    fte: Annotated[Decimal | None, in_class(C)]
    # "assignment": the line runs as long as the assignment; "own": it has a
    # period of its own. start_date and end_date are the period in force;
    # both are null for a line that follows an assignment without a period.
    period_source: Annotated[str, in_class(C)]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]
    rate_category: Annotated[str | None, in_class(B)]
    amount_cents: Annotated[int | None, in_class(B)]
    year: Annotated[int | None, in_class(B)]
    # Computed by the calculation module; null when it could not be priced.
    budgeted_cents: Annotated[int | None, in_class(B)]
    budgeted_by_year: Annotated[dict[str, int], in_class(B)]
    pricing_error: Annotated[str | None, in_class(B)]
    # Why the line runs over or under: someone on it bills in another
    # category than it was budgeted at, from a date. With the cause named
    # ("gepromoveerd per 1 juli 2026: vanaf dan categorie C, de regel is
    # begroot op B") for who may see what that person bills, and without the
    # person ("tariefwijziging per 1 juli 2026") for who may see the signal.
    rate_difference_notes: Annotated[list[str], in_class(D)] = Field(
        default_factory=list
    )
    rate_difference_signals: Annotated[list[str], in_class(SIGNAL)] = Field(
        default_factory=list
    )
    # The colleague the role is meant for. Staffing data: absent for a reader
    # without class C, and never part of a quote.
    intended_person_id: Annotated[UUID | None, in_class(C)] = None
    intended_person_name: Annotated[str | None, in_class(C)] = None
    # The reservation the name made: the allocation, whether it still has the
    # period and size of the line, and whether it is "onder voorbehoud".
    intended_allocation_id: Annotated[UUID | None, in_class(C)] = None
    intended_in_step: Annotated[bool | None, in_class(C)] = None
    intended_tentative: Annotated[bool | None, in_class(C)] = None
    intended_notes: Annotated[list[str], in_class(C)] = Field(default_factory=list)
    # The R14 signal: the person bills in another category than the line
    # assumes in some month. A fact, without the category.
    intended_category_differs: Annotated[bool | None, in_class(SIGNAL)] = None
    # What the person bills, and why it may differ from the line.
    intended_category: Annotated[str | None, in_class(D)] = None
    intended_category_notes: Annotated[list[str], in_class(D)] = Field(
        default_factory=list
    )


class BudgetOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    assignment_name: Annotated[str, in_class(A)]
    can_edit: Annotated[bool, in_class(A)]
    # The period lines follow; null while the assignment has none.
    assignment_start_date: Annotated[date | None, in_class(A)]
    assignment_end_date: Annotated[date | None, in_class(A)]
    # True when lines wait for the assignment to get a period. The message
    # is the one thing to do; such lines are not priced, never as zero.
    period_missing: Annotated[bool, in_class(A)]
    period_message: Annotated[str | None, in_class(A)]
    lines: Annotated[list[BudgetLineOut], nested()]
    subtotals_by_year: Annotated[dict[str, int], in_class(B)]
    total_budgeted_cents: Annotated[int | None, in_class(B)]
    quoted_amount_cents: Annotated[int | None, in_class(B)]
    pricing_error: Annotated[str | None, in_class(B)]


class BudgetLineCreate(BaseModel):
    # Optional once a role is chosen: a line needs a role or a description.
    description: str = Field(default="", max_length=500)
    kind: str
    position: int | None = Field(default=None, ge=1)
    role: str | None = Field(default=None, max_length=255)
    fte: Decimal | None = None
    rate_category: str | None = None
    # Without dates a personnel line follows the period of the assignment.
    period_source: Literal["assignment", "own"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    year: int | None = Field(default=None, ge=2000, le=2100)
    # The colleague the role is meant for. Without a rate_category the
    # category is derived from this person.
    intended_person_id: UUID | None = None
    # Only a beheerder may change a closed year; it leaves an audit row.
    allow_closed_year: bool = False


class BudgetLineUpdate(BaseModel):
    """Only the fields that are sent are changed. The kind cannot change."""

    description: str | None = Field(default=None, max_length=500)
    position: int | None = Field(default=None, ge=1)
    role: str | None = Field(default=None, max_length=255)
    fte: Decimal | None = None
    rate_category: str | None = None
    # "assignment" makes the line follow the assignment again.
    period_source: Literal["assignment", "own"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    year: int | None = Field(default=None, ge=2000, le=2100)
    # Send a person to name or replace the intended person, null to remove.
    intended_person_id: UUID | None = None
    # Take the category from the intended person instead of sending one.
    derive_category: bool = False
    allow_closed_year: bool = False


class DeriveRequest(BaseModel):
    """What the form knows so far when it asks what a person implies."""

    intended_person_id: UUID
    # "assignment": the line follows the assignment, so the proposal is the
    # assignment's period and dates sent here are ignored.
    period_source: Literal["assignment", "own"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    fte: Decimal | None = Field(default=None, gt=0)
    # The line being edited, so its own reservation does not count as busy.
    budget_line_id: UUID | None = None


class RateByYearOut(BaseModel):
    year: Annotated[int, in_class(B)]
    monthly_rate_cents: Annotated[int, in_class(B)]


class RoleChoiceOut(BaseModel):
    role: Annotated[str, in_class(C)]
    role_id: Annotated[UUID | None, in_class(C)]


class DerivationOut(BaseModel):
    """Proposals for a budget line meant for a person. Nothing is saved.

    Every value is a proposal with its source. Role, size and period are
    staffing; scale, category, rate and amount say what the person bills and
    are absent for a reader who may not see that.
    """

    intended_person_id: Annotated[UUID, in_class(C)]
    # Sentences for under the field, in plain Dutch.
    summary: Annotated[list[str], in_class(C)]
    # What needs attention.
    notes: Annotated[list[str], in_class(C)]
    role: Annotated[str | None, in_class(C)]
    role_id: Annotated[UUID | None, in_class(C)]
    # "wies" or "manual" (the one role recorded for the person), "history"
    # (the role the person was last staffed in), or null.
    role_source: Annotated[str | None, in_class(C)]
    role_source_text: Annotated[str | None, in_class(C)]
    role_alternatives: Annotated[list[RoleChoiceOut], nested()]
    start_date: Annotated[date | None, in_class(C)]
    end_date: Annotated[date | None, in_class(C)]
    # "given", "assignment" or "person"; null when nothing could be proposed.
    period_source: Annotated[str | None, in_class(C)]
    period_source_text: Annotated[str | None, in_class(C)]
    # True when the period is a proposal and was not sent by the form.
    period_proposed: Annotated[bool, in_class(C)]
    # The room the person has over the period, at most 1; null without a
    # period or without room.
    fte: Annotated[Decimal | None, in_class(C)]
    free_pct: Annotated[Decimal | None, in_class(C)]
    fte_source_text: Annotated[str | None, in_class(C)]
    rate_summary: Annotated[str | None, in_class(D)]
    billing_scale: Annotated[int | None, in_class(D)]
    rate_category: Annotated[str | None, in_class(D)]
    category_notes: Annotated[list[str], in_class(D)]
    monthly_rates: Annotated[list[RateByYearOut], nested()]
    budgeted_cents: Annotated[int | None, in_class(B)]
