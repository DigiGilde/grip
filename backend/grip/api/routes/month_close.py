"""The monthly close of an assignment.

The planned inzet of a month is the proposal. Whoever manages the assignment
adjusts the percentages that turned out differently and closes the month;
the established inzet then feeds the used budget and the billing data.
Reopening a closed month is for the beheerder and needs a reason.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import Action, DataClass, Decider, Resource, Subject, decide
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.api.routes.quotes import filtered
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.schema.month_close import (
    CloseMonthIn,
    CloseRecordOut,
    MonthDetailOut,
    MonthLineOut,
    MonthPreviewLineOut,
    MonthPreviewOut,
    MonthStateOut,
    MonthTimelineOut,
    ReopenMonthIn,
)
from grip.services import month_close, month_overview, quote_views
from grip.services.assignments import get_assignment
from grip.services.errors import DomainValidationError
from grip.services.phase import allows_month_close

router = APIRouter(prefix="/assignments/{assignment_id}/months", tags=["month-close"])


async def _visible(decider: Decider, subject: Subject, assignment_id: UUID) -> Resource:
    resource = Resource.assignment(assignment_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    return resource


async def _detail(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    resource: Resource,
    assignment_id: UUID,
    month: calc.Month,
) -> dict[str, Any]:
    detail = await month_overview.month_detail(db, assignment_id, month)
    may_close = bool(await decide(decider, subject, Action.CLOSE_MONTH, resource))
    may_reopen = bool(await decide(decider, subject, Action.REOPEN_MONTH, resource))
    value = MonthDetailOut(
        assignment_id=assignment_id,
        month=str(month),
        closed=detail.closed,
        closable=detail.closable,
        closed_at=detail.closed_at,
        closed_by_name=detail.closed_by_name,
        may_close=may_close and detail.closable,
        may_reopen=may_reopen and detail.closed,
        pricing_problem=detail.pricing_problem,
        lines=[
            MonthLineOut(
                allocation_id=line.allocation_id,
                person_id=line.person_id,
                person_name=line.person_name,
                description=line.description,
                planned_fte_pct=line.planned_fte_pct,
                established_fte_pct=line.established_fte_pct,
                category=line.category,
                monthly_rate_cents=line.monthly_rate_cents,
                planned_amount_cents=line.planned_amount_cents,
                established_amount_cents=line.established_amount_cents,
            )
            for line in detail.lines
        ],
        history=[
            CloseRecordOut(
                closed_at=record.closed_at,
                closed_by_name=record.closed_by_name,
                reopened_at=record.reopened_at,
                reopened_by_name=record.reopened_by_name,
                reopen_reason=record.reopen_reason,
            )
            for record in detail.history
        ],
        planned_total_cents=detail.planned_total_cents,
        established_total_cents=detail.established_total_cents,
    )
    return await filtered(decider, subject, resource, value)


@router.get("", response_model=None)
async def month_timeline(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Every month of the assignment, open or closed."""
    resource = await _visible(decider, subject, assignment_id)
    assignment = await get_assignment(db, assignment_id)
    states = await month_overview.timeline(db, assignment_id)
    value = MonthTimelineOut(
        assignment_id=assignment.id,
        assignment_name=assignment.name,
        closing_started=allows_month_close(assignment.status),
        may_close=bool(await decide(decider, subject, Action.CLOSE_MONTH, resource)),
        months=[
            MonthStateOut(
                month=str(state.month),
                closed=state.closed,
                closable=state.closable,
                closed_at=state.closed_at,
                closed_by_name=state.closed_by_name,
                reopen_count=state.reopen_count,
            )
            for state in states
        ],
    )
    return await filtered(decider, subject, resource, value)


@router.get("/{month}", response_model=None)
async def get_month(
    assignment_id: UUID,
    month: str,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One month: the proposal from the plan and, once closed, what was established."""
    resource = await _visible(decider, subject, assignment_id)
    return await _detail(
        db, decider, subject, resource, assignment_id, month_overview.parse_month(month)
    )


@router.post("/{month}/close", response_model=None)
async def close(
    assignment_id: UUID,
    month: str,
    body: CloseMonthIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Close the month at the established percentages."""
    resource = await _visible(decider, subject, assignment_id)
    await require(decider, subject, Action.CLOSE_MONTH, resource)
    parsed = month_overview.parse_month(month)
    await month_overview.ensure_closable(parsed)
    established = {entry.allocation_id: entry.fte_pct for entry in body.established}
    if len(established) != len(body.established):
        raise DomainValidationError("Een inzet staat twee keer in de vaststelling.")
    try:
        await month_close.close_month(
            db, assignment_id, parsed, actor=person, established=established
        )
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    return await _detail(db, decider, subject, resource, assignment_id, parsed)


@router.post("/{month}/preview", response_model=None)
async def preview_close(
    assignment_id: UUID,
    month: str,
    body: CloseMonthIn,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What the month comes to at these percentages. Changes nothing."""
    resource = await _visible(decider, subject, assignment_id)
    await require(decider, subject, Action.CLOSE_MONTH, resource)
    parsed = month_overview.parse_month(month)
    established = {entry.allocation_id: entry.fte_pct for entry in body.established}
    try:
        lines = await month_close.preview(
            db, assignment_id, parsed, established=established
        )
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    value = MonthPreviewOut(
        month=str(parsed),
        lines=[
            MonthPreviewLineOut(
                allocation_id=UUID(line.allocation_id), amount_cents=line.amount_cents
            )
            for line in lines
        ],
        total_cents=sum(line.amount_cents for line in lines),
    )
    return await filtered(decider, subject, resource, value)


@router.post("/{month}/reopen", response_model=None)
async def reopen(
    assignment_id: UUID,
    month: str,
    body: ReopenMonthIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reopen a closed month. The earlier close stays in the trail."""
    resource = await _visible(decider, subject, assignment_id)
    await require(decider, subject, Action.REOPEN_MONTH, resource)
    parsed = month_overview.parse_month(month)
    await month_close.reopen_month(
        db, assignment_id, parsed, actor=person, reason=body.reason
    )
    return await _detail(db, decider, subject, resource, assignment_id, parsed)
