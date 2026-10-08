"""Stand van zaken: budgeted, used and available per assignment."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess, YearFilter, parse_year
from grip.schema.overview import (
    AssignmentOverviewOut,
    LineCostOut,
    LineOverviewOut,
    OverviewRowOut,
    TeamMemberOut,
    TotalsOut,
)
from grip.services import assignment_views as views

router = APIRouter(tags=["overview"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
_ROW_CLASSES = schema_classes(OverviewRowOut)
_TEAM_CLASSES = schema_classes(TeamMemberOut)
_LINE_CLASSES = schema_classes(LineOverviewOut) - _TEAM_CLASSES | {DataClass.STAFFING}
_HEAD_CLASSES = frozenset({A, B})


def _totals(totals: Any) -> TotalsOut | None:
    if totals is None:
        return None
    return TotalsOut(
        budgeted_cents=totals.budgeted_cents,
        realised_cents=totals.realised_cents,
        forecast_cents=totals.forecast_cents,
        coverage_cents=totals.coverage_cents,
        used_cents=totals.used_cents,
        available_cents=totals.available_cents,
        overrun=totals.overrun,
    )


@router.get("/overview", response_model=None)
async def get_overview(
    access: RequestAccess, db: DbSession, year: YearFilter = None
) -> dict[str, Any]:
    """One row per assignment the person may read.

    The amounts are class B: a reader without it gets the rows without them.
    """
    selected = parse_year(year)
    if await access.may(Action.READ, Resource.assignment(), A):
        rows = await views.assignment_rows(db)
    else:
        rows = await views.assignment_rows(
            db, only_ids=await access.own_assignment_ids()
        )
    items: list[dict[str, Any]] = []
    priced: list[views.Totals] = []
    any_financial = False
    for row in rows:
        resource = Resource.assignment(row.assignment.id)
        permitted = await access.classes(resource, _ROW_CLASSES)
        if A not in permitted:
            continue
        totals: views.Totals | None = None
        error: str | None = None
        if B in permitted:
            any_financial = True
            view = await views.assignment_view(db, row.assignment.id, year=selected)
            totals, error = view.totals, view.pricing_error
            if totals is not None:
                priced.append(totals)
        a = row.assignment
        items.append(
            build_response(
                OverviewRowOut(
                    assignment_id=a.id,
                    name=a.name,
                    status=a.status,
                    client_name=row.client_name,
                    start_date=a.start_date,
                    end_date=a.end_date,
                    totals=_totals(totals),
                    pricing_error=error,
                ),
                permitted,
            )
        )
    result: dict[str, Any] = {"year": selected, "rows": items}
    if any_financial:
        grand = _totals(views.Totals.of(priced))
        assert grand is not None
        result["totals"] = grand.model_dump(mode="json")
    return result


@router.get("/assignments/{assignment_id}/overview", response_model=None)
async def get_assignment_overview(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    year: YearFilter = None,
) -> dict[str, Any]:
    """The budget lines of one assignment, and per line the team and the costs."""
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    selected = parse_year(year)
    view = await views.assignment_view(db, assignment_id, year=selected)
    line_permitted = await access.classes(resource, _LINE_CLASSES)

    lines: list[dict[str, Any]] = []
    for line_view in view.lines:
        line = line_view.line
        body = build_response(
            LineOverviewOut(
                budget_line_id=line.id,
                description=line.description,
                kind=line.kind,
                role=line.role,
                fte=line.fte,
                start_date=line.start_date,
                end_date=line.end_date,
                rate_category=line.rate_category,
                totals=_totals(line_view.overview),
                pricing_error=line_view.pricing_error,
                team=[],
                costs=[
                    LineCostOut(
                        cost_item_id=c.cost_item_id,
                        description=c.description,
                        pct=c.pct,
                        amount_cents=c.amount_cents,
                    )
                    for c in line_view.coverages
                ],
            ),
            line_permitted,
        )
        # Who is on the team is decided per person: someone sees the own
        # amount but not a colleague's.
        team: list[dict[str, Any]] = []
        for member in line_view.allocations:
            allocation = member.allocation
            permitted = await access.classes(
                Resource.allocation(assignment_id, allocation.person_id),
                _TEAM_CLASSES,
            )
            if DataClass.STAFFING_ROSTER not in permitted:
                continue
            team.append(
                build_response(
                    TeamMemberOut(
                        allocation_id=allocation.id,
                        person_id=allocation.person_id,
                        person_name=member.person_name,
                        start_date=allocation.start_date,
                        end_date=allocation.end_date,
                        fte_pct=allocation.fte_pct,
                        amount_cents=member.amount_cents,
                        pricing_error=member.pricing_error,
                        category_mismatch=member.mismatch is not None,
                    ),
                    permitted,
                )
            )
        body["team"] = team
        if B not in line_permitted:
            # Not even how many cost items a line carries.
            body["costs"] = []
        lines.append(body)

    head = build_response(
        AssignmentOverviewOut(
            assignment_id=assignment_id,
            name=view.row.assignment.name,
            status=view.row.assignment.status,
            year=selected,
            totals=_totals(view.totals),
            pricing_error=view.pricing_error,
            lines=[],
        ),
        await access.classes(resource, _HEAD_CLASSES),
    )
    head["lines"] = lines
    return head
