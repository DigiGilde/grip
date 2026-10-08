"""Shapes of the billing data routes.

Billing data follows from a closed month. The total is class B. A line is
one person's inzet: the name is class C and the category, rate and amount
are class D, so a reader of totals does not learn anyone's rate.
"""

from __future__ import annotations

from datetime import datetime
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
