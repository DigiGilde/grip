"""Inzet: a person on a budget line, for a period, at a percentage."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from grip.access import (
    PLANNER,
    Action,
    DataClass,
    Resource,
    build_response,
    schema_classes,
)
from grip.api.assignment_support import DbSession, RequestAccess, YearFilter, parse_year
from grip.calc import Month
from grip.core.auth import CurrentPerson
from grip.schema.allocations import (
    AllocationCreate,
    AllocationOut,
    AllocationUpdate,
    LineChoiceOut,
    PersonChoiceOut,
)
from grip.schema.board import (
    BoardBarOut,
    BoardCellOut,
    BoardOpenRoleOut,
    BoardPersonOut,
)
from grip.services import assignment_views as views
from grip.services import assignments as service
from grip.services import staffing_board

router = APIRouter(prefix="/allocations", tags=["allocations"])

A = DataClass.ASSIGNMENT_BASIC
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
_CLASSES = schema_classes(AllocationOut)
_BAR_CLASSES = schema_classes(BoardBarOut)


async def _row(
    view: views.AllocationView, access: RequestAccess
) -> dict[str, Any] | None:
    """The allocation as this reader may see it, or None when not at all."""
    allocation = view.allocation
    about = Resource.allocation(view.assignment_id, allocation.person_id)
    permitted = set(await access.classes(about, _CLASSES - {A}))
    if ROSTER not in permitted:
        return None
    # Name of the assignment and the line: class A of the assignment itself.
    if await access.may(Action.READ, Resource.assignment(view.assignment_id), A):
        permitted.add(A)
    mismatch = view.mismatch
    model = AllocationOut(
        id=allocation.id,
        person_id=allocation.person_id,
        person_name=view.person_name,
        assignment_id=view.assignment_id,
        assignment_name=view.assignment_name,
        budget_line_id=view.line.id,
        budget_line_description=view.line.description,
        role=view.line.role,
        tentative=view.tentative,
        period_source=allocation.period_source,
        start_date=allocation.start_date,
        end_date=allocation.end_date,
        fte_pct=allocation.fte_pct,
        can_edit=await access.may(Action.EDIT, about, C),
        amount_cents=view.amount_cents,
        pricing_error=view.pricing_error,
        line_category=mismatch.line_category if mismatch else None,
        person_category=mismatch.person_category if mismatch else None,
        mismatch_direction=mismatch.direction.value if mismatch else None,
        category_mismatch=mismatch is not None,
    )
    return build_response(model, permitted)


async def _may_add(access: RequestAccess, db: DbSession) -> bool:
    """Whether there is any assignment the person may staff."""
    if PLANNER in access.subject.functions:
        return True
    person_id = access.subject.person_id
    return person_id is not None and bool(
        await views.managed_assignment_ids(db, person_id)
    )


@router.get("", response_model=None)
async def list_allocations(
    access: RequestAccess,
    db: DbSession,
    person_id: UUID | None = None,
    assignment_id: UUID | None = None,
    budget_line_id: UUID | None = None,
    year: YearFilter = None,
) -> dict[str, Any]:
    """Inzet the person may see: all of it for a planner, otherwise the own
    assignments, the own inzet and that of direct reports."""
    selected = parse_year(year)
    person_ids = [person_id] if person_id is not None else None
    assignment_ids = [assignment_id] if assignment_id is not None else None

    reads_all = await access.may(Action.READ, Resource.assignment(), C)
    found: list[views.AllocationView] = []
    if reads_all:
        found = await views.allocation_views(
            db,
            person_ids=person_ids,
            assignment_ids=assignment_ids,
            budget_line_id=budget_line_id,
            year=selected,
        )
    elif access.subject.person_id is not None:
        me = access.subject.person_id
        own_assignments = await access.own_assignment_ids()
        if assignment_id is not None:
            own_assignments &= {assignment_id}
        people = {me} | await views.direct_report_ids(db, me)
        if person_id is not None:
            people &= {person_id}
        by_assignment = await views.allocation_views(
            db,
            person_ids=person_ids,
            assignment_ids=own_assignments,
            budget_line_id=budget_line_id,
            year=selected,
        )
        by_person = await views.allocation_views(
            db,
            person_ids=people,
            assignment_ids=assignment_ids,
            budget_line_id=budget_line_id,
            year=selected,
        )
        seen: set[UUID] = set()
        for view in [*by_assignment, *by_person]:
            if view.allocation.id not in seen:
                seen.add(view.allocation.id)
                found.append(view)
        found.sort(key=lambda v: (v.allocation.start_date, str(v.allocation.id)))

    items = []
    for view in found:
        row = await _row(view, access)
        if row is not None:
            items.append(row)
    return {"items": items, "can_add": await _may_add(access, db)}


@router.get("/board", response_model=None)
async def get_board(
    access: RequestAccess,
    db: DbSession,
    start: str | None = None,
    months: int = 12,
) -> dict[str, Any]:
    """The planner's board: people over months, bars per allocation, open roles.

    ``start`` is the first month as ``YYYY-MM``; by default three months back.
    Each bar and each row is decided separately, so a team member gets the
    own row and someone who manages an assignment the bars on it. No amounts.
    """
    data = await staffing_board.board(db, _board_start(start), months=months)

    persons: list[dict[str, Any]] = []
    for person in data.persons:
        about_person = Resource.person(person.person_id)
        person_classes = set(await access.classes(about_person, {C, ROSTER}))
        bars: list[dict[str, Any]] = []
        for bar in person.bars:
            about = Resource.allocation(bar.assignment_id, bar.person_id)
            permitted = set(await access.classes(about, _BAR_CLASSES - {A}))
            # A row is about inzet: a bar without period and percentage has
            # nothing to draw, so the roster alone does not show it here.
            if C not in permitted:
                continue
            if await access.may(Action.READ, Resource.assignment(bar.assignment_id), A):
                permitted.add(A)
            bars.append(
                build_response(
                    BoardBarOut(
                        allocation_id=bar.allocation_id,
                        person_id=bar.person_id,
                        person_name=bar.person_name,
                        assignment_id=bar.assignment_id,
                        assignment_name=bar.assignment_name,
                        budget_line_id=bar.budget_line_id,
                        line_description=bar.line_description,
                        role=bar.role,
                        tentative=bar.tentative,
                        verbally_agreed=bar.verbally_agreed,
                        start_date=bar.start_date,
                        end_date=bar.end_date,
                        fte_pct=bar.fte_pct,
                        closed_months=list(bar.closed_months),
                        can_edit=await access.may(Action.EDIT, about, C),
                        category_mismatch=bar.category_mismatch,
                        line_category=bar.line_category,
                        person_category=bar.person_category,
                    ),
                    permitted,
                )
            )
        sees_totals = C in person_classes
        if not bars and not sees_totals:
            continue
        row = build_response(
            BoardPersonOut(
                person_id=person.person_id,
                person_name=person.person_name,
                manager_id=person.manager_id,
                manager_name=person.manager_name,
                cells=[
                    BoardCellOut(
                        month=cell.month,
                        available=cell.available,
                        pct=cell.pct,
                        tentative_pct=cell.tentative_pct,
                        over=cell.over,
                        established=cell.established,
                    )
                    for cell in person.cells
                ],
                now_pct=person.now_pct,
                room_from=person.room_from,
                idle_from=person.idle_from,
                over_months=list(person.over_months),
                bars=[],
            ),
            # Whoever sees a bar sees whose it is.
            person_classes | {ROSTER},
        )
        if not sees_totals:
            row["cells"] = []
        row["bars"] = bars
        persons.append(row)

    roles: list[dict[str, Any]] = []
    for role in data.open_roles:
        resource = Resource.assignment(role.assignment_id)
        permitted = await access.classes(resource, {A, C})
        if C not in permitted:
            continue
        roles.append(
            build_response(
                BoardOpenRoleOut(
                    budget_line_id=role.budget_line_id,
                    assignment_id=role.assignment_id,
                    assignment_name=role.assignment_name,
                    description=role.description,
                    role=role.role,
                    fte=role.fte,
                    unfilled_fte=role.unfilled_fte,
                    start_date=role.start_date,
                    end_date=role.end_date,
                    can_fill=await access.may(Action.EDIT, resource, C),
                ),
                permitted,
            )
        )
    return {
        "months": [month.isoformat() for month in data.months],
        "current_month": data.current_month.isoformat(),
        "persons": persons,
        "open_roles": roles,
        "can_add": await _may_add(access, db),
    }


def _board_start(value: str | None) -> Month:
    if not value:
        today = date.today()
        month = Month(today.year, today.month)
        # Three months of what has been, nine of what is coming.
        year, number = month.year, month.month - 3
        if number < 1:
            year, number = year - 1, number + 12
        return Month(year, number)
    try:
        year_text, month_text = value.split("-")
        return Month(int(year_text), int(month_text))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422, detail="De eerste maand heeft de vorm JJJJ-MM."
        ) from None


@router.get("/options", response_model=None)
async def allocation_options(access: RequestAccess, db: DbSession) -> dict[str, Any]:
    """People and personnel lines to choose from when adding inzet."""
    await access.require(Action.READ, Resource.person(), ROSTER)
    if PLANNER in access.subject.functions:
        lines = await views.line_options(db)
    else:
        person_id = access.subject.person_id
        managed = (
            await views.managed_assignment_ids(db, person_id) if person_id else set()
        )
        lines = await views.line_options(db, only_assignment_ids=managed)
    line_items = []
    for option in lines:
        resource = Resource.assignment(option.assignment_id)
        if not await access.may(Action.EDIT, resource, C):
            continue
        line = option.line
        line_items.append(
            build_response(
                LineChoiceOut(
                    budget_line_id=line.id,
                    assignment_id=option.assignment_id,
                    assignment_name=option.assignment_name,
                    description=line.description,
                    role=line.role,
                    fte=line.fte,
                    start_date=line.start_date,
                    end_date=line.end_date,
                ),
                await access.classes(resource, {A, C}),
            )
        )
    return {
        "people": [
            build_response(PersonChoiceOut(id=p.person_id, name=p.name), {ROSTER})
            for p in await views.person_options(db)
        ],
        "lines": line_items,
    }


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def add_allocation(
    body: AllocationCreate,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    line = await service.get_budget_line(db, body.budget_line_id)
    about = Resource.allocation(line.assignment_id, body.person_id)
    await access.require(Action.EDIT, about, C)
    override = await access.require_closed_year_override(body.allow_closed_year)
    allocation = await service.add_allocation(
        db,
        body.budget_line_id,
        body.person_id,
        period_source=body.period_source,
        start_date=body.start_date,
        end_date=body.end_date,
        fte_pct=body.fte_pct,
        actor=person,
        allow_closed_year=override,
    )
    access.forget()
    row = await _row(await views.allocation_view(db, allocation.id), access)
    return row or {}


async def _require_edit(
    allocation_id: UUID, access: RequestAccess, db: DbSession
) -> views.AllocationView:
    view = await views.allocation_view(db, allocation_id)
    about = Resource.allocation(view.assignment_id, view.allocation.person_id)
    # Not readable means not known to exist.
    await access.require(Action.READ, about, ROSTER, hide_existence=True)
    await access.require(Action.EDIT, about, C)
    return view


@router.patch("/{allocation_id}", response_model=None)
async def update_allocation(
    allocation_id: UUID,
    body: AllocationUpdate,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    await _require_edit(allocation_id, access, db)
    override = await access.require_closed_year_override(body.allow_closed_year)
    changes = body.model_dump(exclude_unset=True, exclude={"allow_closed_year"})
    changes = {k: v for k, v in changes.items() if v is not None}
    if changes:
        await service.update_allocation(
            db, allocation_id, actor=person, allow_closed_year=override, **changes
        )
    row = await _row(await views.allocation_view(db, allocation_id), access)
    return row or {}


@router.delete("/{allocation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allocation(
    allocation_id: UUID,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
    allow_closed_year: bool = False,
) -> None:
    await _require_edit(allocation_id, access, db)
    override = await access.require_closed_year_override(allow_closed_year)
    await service.delete_allocation(
        db, allocation_id, actor=person, allow_closed_year=override
    )
