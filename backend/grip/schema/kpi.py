"""Billability KPI per person and year (class F)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from grip.access import DataClass, in_class

_ROSTER = in_class(DataClass.STAFFING_ROSTER)
_KPI = in_class(DataClass.PERSON_KPI)


class KpiOut(BaseModel):
    person_id: Annotated[UUID, _ROSTER]
    person_name: Annotated[str, _ROSTER]
    year: Annotated[int, _KPI]
    # Null when no target is set for the year.
    target_pct: Annotated[Decimal | None, _KPI]
    # Counts the changes of the target; null when none is set.
    target_version: Annotated[int | None, _KPI] = None
    target_cents: Annotated[int | None, _KPI]
    # Closed months with the established inzet.
    realised_cents: Annotated[int | None, _KPI]
    # Open months with the planned inzet.
    forecast_cents: Annotated[int | None, _KPI]
    realisation_cents: Annotated[int | None, _KPI]
    # Set when the amounts cannot be derived, for example without a rate
    # card for the year.
    unavailable_reason: Annotated[str | None, _KPI]


class KpiTargetUpdate(BaseModel):
    target_pct: Decimal = Field(ge=0, le=100)
    confirm_closed_year: bool = False
