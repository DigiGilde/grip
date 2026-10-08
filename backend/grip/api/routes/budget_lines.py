"""The budget of an assignment: personnel lines and fixed lines."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from grip import calc
from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.auth import CurrentPerson
from grip.schema.budget_lines import (
    BudgetLineCreate,
    BudgetLineOut,
    BudgetLineUpdate,
    BudgetOut,
    DerivationOut,
    DeriveRequest,
    RateByYearOut,
    RoleChoiceOut,
)
from grip.services import assignment_views as views
from grip.services import assignments as service
from grip.services import budget_intent, periods, pricing

router = APIRouter(tags=["budget"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
D = DataClass.PERSON_RATE
ROSTER = DataClass.STAFFING_ROSTER
_CLASSES = schema_classes(BudgetOut)
_DERIVATION_CLASSES = schema_classes(DerivationOut)


def _intent_fields(
    intent: budget_intent.LineIntent | None, may_see_rate: bool
) -> dict[str, Any]:
    """The intended person of a line. The category only for who may see what
    this person bills: that is decided per person, not per assignment."""
    if intent is None:
        return {}
    return {
        "intended_person_id": intent.person_id,
        "intended_person_name": intent.person_name,
        "intended_allocation_id": intent.allocation_id,
        "intended_in_step": intent.in_step,
        "intended_tentative": intent.tentative,
        "intended_notes": list(intent.notes),
        "intended_category_differs": intent.category_differs,
        "intended_category": intent.implied_category if may_see_rate else None,
        "intended_category_notes": list(intent.category_notes) if may_see_rate else [],
    }


def _line_out(
    view: views.LineView,
    intent: budget_intent.LineIntent | None = None,
    may_see_rate: bool = False,
) -> BudgetLineOut:
    line = view.line
    budgeted = sum(view.budgeted_by_year.values()) if not view.pricing_error else None
    return BudgetLineOut(
        id=line.id,
        assignment_id=line.assignment_id,
        description=line.description,
        detail=line.detail,
        kind=line.kind,
        position=line.position,
        role=line.role,
        fte=line.fte,
        period_source=line.period_source,
        start_date=line.start_date,
        end_date=line.end_date,
        rate_category=line.rate_category,
        amount_cents=line.amount_cents,
        year=line.year,
        budgeted_cents=budgeted,
        budgeted_by_year={str(y): c for y, c in view.budgeted_by_year.items()},
        pricing_error=view.pricing_error,
        **_intent_fields(intent, may_see_rate),
    )


async def _require_may_name(
    access: RequestAccess, assignment_id: UUID, person_id: UUID
) -> None:
    """Naming an intended person is staffing: the right to edit inzet of that
    person on this assignment, and to pick people at all."""
    await access.require(Action.READ, Resource.person(), ROSTER)
    await access.require(Action.EDIT, Resource.allocation(assignment_id, person_id), C)


async def _budget(
    assignment_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    # The budget is always shown for the whole period, with a subtotal per year.
    view = await views.assignment_view(db, assignment_id, year=None)
    resource = Resource.assignment(assignment_id)
    intents = await budget_intent.line_intents(db, [v.line for v in view.lines])
    # A reservation just made changes who is staffed here, and so who may
    # see what a person bills.
    access.forget()
    try:
        differences = await pricing.rate_differences(db, assignment_id)
    except calc.CalcError:
        differences = ()
    lines = []
    for line_view in view.lines:
        intent = intents.get(line_view.line.id)
        may_see_rate = intent is not None and await access.may(
            Action.READ, Resource.allocation(assignment_id, intent.person_id), D
        )
        out = _line_out(line_view, intent, may_see_rate)
        for difference in differences:
            if difference.budget_line_id != line_view.line.id:
                continue
            if difference.generic_text not in out.rate_difference_signals:
                out.rate_difference_signals.append(difference.generic_text)
            # The cause names what a person bills: decided per person.
            if await access.may(
                Action.READ,
                Resource.allocation(assignment_id, difference.person_id),
                D,
            ):
                out.rate_difference_notes.append(difference.text)
        lines.append(out)
    follows = periods.assignment_period(view.row.assignment)
    waiting = any(
        v.line.kind == "personnel" and v.line.start_date is None for v in view.lines
    )
    model = BudgetOut(
        assignment_id=assignment_id,
        assignment_name=view.row.assignment.name,
        can_edit=await access.may(Action.EDIT, resource, B),
        assignment_start_date=follows[0],
        assignment_end_date=follows[1],
        period_missing=waiting,
        period_message=periods.NO_PERIOD_MESSAGE if waiting else None,
        lines=lines,
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
    if body.intended_person_id is not None:
        await _require_may_name(access, assignment_id, body.intended_person_id)
    override = await access.require_closed_year_override(body.allow_closed_year)
    values = body.model_dump(exclude={"allow_closed_year"})
    await budget_intent.add_line(
        db, assignment_id, actor=person, allow_closed_year=override, **values
    )
    return await _budget(assignment_id, access, db)


@router.post("/assignments/{assignment_id}/budget-lines/derive", response_model=None)
async def derive_budget_line(
    assignment_id: UUID,
    body: DeriveRequest,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    """What naming a person on a line would imply. Saves nothing.

    The category is shown to whoever may already see what this person bills,
    and to an owner or manager who may put the person on this assignment:
    saving would staff the person here and show it anyway.
    """
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await _require_may_name(access, assignment_id, body.intended_person_id)

    async def may_see(other_id: UUID) -> bool:
        return await access.may(Action.READ, Resource.assignment(other_id), A)

    derived = await budget_intent.derive(
        db,
        assignment_id,
        body.intended_person_id,
        start_date=body.start_date,
        end_date=body.end_date,
        fte=body.fte,
        period_source=body.period_source,
        exclude_line_id=body.budget_line_id,
        may_see_assignment=may_see,
    )
    model = DerivationOut(
        intended_person_id=derived.person_id,
        summary=list(derived.summary),
        notes=list(derived.notes),
        role=derived.role,
        role_id=derived.role_id,
        role_source=derived.role_source,
        role_source_text=derived.role_source_text,
        role_alternatives=[
            RoleChoiceOut(role=choice.role, role_id=choice.role_id)
            for choice in derived.role_alternatives
        ],
        start_date=derived.start_date,
        end_date=derived.end_date,
        period_source=derived.period_source,
        period_source_text=derived.period_source_text,
        period_proposed=derived.period_proposed,
        fte=derived.fte,
        free_pct=derived.free_pct,
        fte_source_text=derived.fte_source_text,
        rate_summary=derived.rate_summary,
        billing_scale=derived.billing_scale,
        rate_category=derived.rate_category,
        category_notes=list(derived.category_notes),
        monthly_rates=[
            RateByYearOut(year=year, monthly_rate_cents=cents)
            for year, cents in sorted(derived.monthly_rate_by_year.items())
        ],
        budgeted_cents=derived.budgeted_cents,
    )
    permitted = set(await access.classes(resource, _DERIVATION_CLASSES))
    about = Resource.allocation(assignment_id, body.intended_person_id)
    if not await access.may(Action.READ, about, D) and not await access.may(
        Action.READ, resource, D
    ):
        permitted.discard(D)
    if D not in permitted:
        # Rate and amount follow from the category; without the category they
        # would give it away.
        permitted.discard(B)
    return build_response(model, permitted)


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
    changes = body.model_dump(
        exclude_unset=True, exclude={"allow_closed_year", "derive_category"}
    )
    names_person = "intended_person_id" in changes
    if set(changes) - {"intended_person_id"} or body.derive_category or not changes:
        # Anything but the intended person is the budget itself.
        await access.require(Action.EDIT, resource, B)
    if names_person:
        # Naming someone is staffing; so is removing the name.
        about = changes["intended_person_id"] or line.intended_person_id
        if about is not None:
            await _require_may_name(access, line.assignment_id, about)
        else:
            await access.require(Action.EDIT, resource, C)
    override = await access.require_closed_year_override(body.allow_closed_year)
    if changes or body.derive_category:
        await budget_intent.update_line(
            db,
            line_id,
            actor=person,
            allow_closed_year=override,
            derive_category=body.derive_category,
            **changes,
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
    await budget_intent.delete_line(
        db, line_id, actor=person, allow_closed_year=override
    )
    return await _budget(assignment_id, access, db)
