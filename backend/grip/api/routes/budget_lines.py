"""The budget of an assignment: personnel lines and fixed lines."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.auth import CurrentPerson
from grip.schema.budget_lines import (
    BudgetLineCreate,
    BudgetLineOut,
    BudgetLineUpdate,
    BudgetOut,
)
from grip.services import assignment_views as views
from grip.services import assignments as service

router = APIRouter(tags=["budget"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
_CLASSES = schema_classes(BudgetOut)


def _line_out(view: views.LineView) -> BudgetLineOut:
    line = view.line
    budgeted = sum(view.budgeted_by_year.values()) if not view.pricing_error else None
    return BudgetLineOut(
        id=line.id,
        assignment_id=line.assignment_id,
        description=line.description,
        kind=line.kind,
        position=line.position,
        role=line.role,
        fte=line.fte,
        start_date=line.start_date,
        end_date=line.end_date,
        rate_category=line.rate_category,
        amount_cents=line.amount_cents,
        year=line.year,
        budgeted_cents=budgeted,
        budgeted_by_year={str(y): c for y, c in view.budgeted_by_year.items()},
        pricing_error=view.pricing_error,
    )


async def _budget(
    assignment_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    # The budget is always shown for the whole period, with a subtotal per year.
    view = await views.assignment_view(db, assignment_id, year=None)
    resource = Resource.assignment(assignment_id)
    model = BudgetOut(
        assignment_id=assignment_id,
        assignment_name=view.row.assignment.name,
        can_edit=await access.may(Action.EDIT, resource, B),
        lines=[_line_out(line) for line in view.lines],
        subtotals_by_year={str(y): c for y, c in view.budgeted_by_year.items()},
        total_budgeted_cents=sum(view.budgeted_by_year.values())
        if view.pricing_error is None
        else None,
        quoted_amount_cents=view.row.assignment.quoted_amount_cents,
        pricing_error=view.pricing_error,
    )
    return build_response(model, await access.classes(resource, _CLASSES))


@router.get("/assignments/{assignment_id}/budget", response_model=None)
async def get_budget(
    assignment_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    """The budget lines. Each reader gets the fields of the classes it may see."""
    await access.require(
        Action.READ, Resource.assignment(assignment_id), A, hide_existence=True
    )
    return await _budget(assignment_id, access, db)


@router.post(
    "/assignments/{assignment_id}/budget-lines",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def add_budget_line(
    assignment_id: UUID,
    body: BudgetLineCreate,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.EDIT, resource, B)
    override = await access.require_closed_year_override(body.allow_closed_year)
    values = body.model_dump(exclude={"allow_closed_year"})
    await service.add_budget_line(
        db, assignment_id, actor=person, allow_closed_year=override, **values
    )
    return await _budget(assignment_id, access, db)


@router.patch("/budget-lines/{line_id}", response_model=None)
async def update_budget_line(
    line_id: UUID,
    body: BudgetLineUpdate,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    line = await service.get_budget_line(db, line_id)
    resource = Resource.assignment(line.assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.EDIT, resource, B)
    override = await access.require_closed_year_override(body.allow_closed_year)
    changes = body.model_dump(exclude_unset=True, exclude={"allow_closed_year"})
    if changes:
        await service.update_budget_line(
            db, line_id, actor=person, allow_closed_year=override, **changes
        )
    return await _budget(line.assignment_id, access, db)


@router.delete("/budget-lines/{line_id}", response_model=None)
async def delete_budget_line(
    line_id: UUID,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
    allow_closed_year: bool = False,
) -> dict[str, Any]:
    line = await service.get_budget_line(db, line_id)
    assignment_id = line.assignment_id
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.EDIT, resource, B)
    override = await access.require_closed_year_override(allow_closed_year)
    await service.delete_budget_line(
        db, line_id, actor=person, allow_closed_year=override
    )
    return await _budget(assignment_id, access, db)
