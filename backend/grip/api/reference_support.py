"""Small helpers shared by the routes for rates, team, KPI and costs."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from grip.access import (
    Action,
    Context,
    DataClass,
    Decider,
    Resource,
    Subject,
    build_response,
    decide,
    permitted_classes,
    schema_classes,
)
from grip.core import clock


async def filtered(
    decider: Decider,
    subject: Subject,
    resource: Resource,
    value: BaseModel,
    context: Context | None = None,
) -> dict[str, Any]:
    """The response for ``value`` with only the classes the subject may read."""
    permitted = await permitted_classes(
        decider, subject, resource, schema_classes(type(value)), context
    )
    return build_response(value, permitted)


async def may(
    decider: Decider,
    subject: Subject,
    action: Action,
    resource: Resource,
    data_class: DataClass | None = None,
    context: Context | None = None,
) -> bool:
    return bool(await decide(decider, subject, action, resource, data_class, context))


def period_or_today(
    period_start: date | None, period_end: date | None
) -> tuple[date, date]:
    """The period on screen; one day (today) when none is given."""
    today = clock.today()
    start = period_start or period_end or today
    end = period_end or period_start or today
    if end < start:
        raise HTTPException(
            status_code=422,
            detail="De einddatum van de periode ligt voor de begindatum.",
        )
    return (start, end)
