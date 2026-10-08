"""Stand van zaken: budgeted, used and available per assignment."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess, YearFilter, parse_year
from grip.api.routes.assignment_finance import figures_out
from grip.schema.board import (
    AssignmentStaffingOut,
    RoleBarOut,
    RoleGapOut,
    RoleMonthOut,
    RoleStaffingOut,
)
from grip.schema.overview import (
    AssignmentOverviewOut,
    AttentionOut,
    LineCostOut,
    LineOverviewOut,
    OverviewRowOut,
    TeamMemberOut,
    TotalsOut,
)
from grip.services import assignment_finance as finance
from grip.services import assignment_views as views
from grip.services import staffing_board
from grip.services.overview_attention import attention_points
from grip.services.phase import Phase

router = APIRouter(tags=["overview"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL
_ROW_CLASSES = schema_classes(OverviewRowOut)
_TEAM_CLASSES = schema_classes(TeamMemberOut)
_LINE_CLASSES = schema_classes(LineOverviewOut) - _TEAM_CLASSES | {DataClass.STAFFING}
_HEAD_CLASSES = frozenset({A, B})
_ROLE_BAR_CLASSES = schema_classes(RoleBarOut)


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


def _in_year(start: date | None, end: date | None, year: int | None) -> bool:
    """Whether the period of an assignment touches the chosen year."""
    if year is None:
        return True
    if start is not None and start.year > year:
        return False
    return not (end is not None and end.year < year)


@router.get("/overview", response_model=None)
async def get_overview(
    access: RequestAccess, db: DbSession, year: YearFilter = None
) -> dict[str, Any]:
    """One row per assignment the person may read.

    The amounts are class B: a reader without it gets the rows without them.
    They come from the same read model as the Financieel tab of an
    assignment, so the two always agree.
    """
    selected = parse_year(year)
    if await access.may(Action.READ, Resource.assignment(), A):
        rows = await views.assignment_rows(db)
    else:
        rows = await views.assignment_rows(
            db, only_ids=await access.own_assignment_ids()
        )
    items: list[dict[str, Any]] = []
    priced: dict[Phase, list[finance.Figures]] = {phase: [] for phase in Phase}
    any_financial = False
    to_deliver = to_invoice = 0
    for row in rows:
        resource = Resource.assignment(row.assignment.id)
        permitted = await access.classes(resource, _ROW_CLASSES)
        if A not in permitted:
            continue
        figures: finance.Figures | None = None
        error: str | None = None
        reference = None
        money = B in permitted
        # The R14 signal is also for a planner, as a fact without amounts.
        signal = await access.may(Action.READ, resource, SIGNAL)
        attention: list[AttentionOut] = []
        if money or signal:
            data = await finance.assignment_finance(
                db, row.assignment.id, year=selected
            )
            attention = [
                AttentionOut(kind=point.kind, text=point.text, tab=point.tab)
                for point in attention_points(data)
                if (money if point.about_money else signal)
            ]
        if money:
            any_financial = True
            figures, error = data.totals, data.pricing_error
            reference = data.reference_month
            if figures is not None:
                priced[row.phase].append(figures)
            if row.phase is Phase.ACTIVE:
                key = data.key_figures
                to_deliver += key.to_deliver_cents or 0
                to_invoice += key.to_invoice_cents or 0
        a = row.assignment
        items.append(
            build_response(
                OverviewRowOut(
                    assignment_id=a.id,
                    name=a.name,
                    status=a.status,
                    phase=row.phase.value,
                    client_name=row.client_name,
                    start_date=a.start_date,
                    end_date=a.end_date,
                    figures=figures_out(figures),
                    pricing_error=error,
                    reference_month=reference,
                    in_year=_in_year(a.start_date, a.end_date, selected),
                    attention=attention,
                ),
                permitted,
            )
        )
    result: dict[str, Any] = {"year": selected, "rows": items}
    if any_financial:
        for phase in Phase:
            subtotal = figures_out(finance.Figures.sum(priced[phase]))
            assert subtotal is not None
            result[f"figures_{phase.value}"] = subtotal.model_dump(mode="json")
        result["to_deliver_cents"] = to_deliver
        result["to_invoice_cents"] = to_invoice
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


@router.get("/assignments/{assignment_id}/staffing", response_model=None)
async def get_assignment_staffing(
    assignment_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    """Per role what is asked, who fills it and what is still open. No amounts.

    A reader with the staffing class gets months, bars and gaps. A team
    member gets the names on each role and nothing about time.
    """
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.READ, resource, DataClass.STAFFING_ROSTER)
    data = await staffing_board.assignment_staffing(db, assignment_id)
    classes = await access.classes(
        resource, {A, DataClass.STAFFING, DataClass.STAFFING_ROSTER}
    )
    sees_time = DataClass.STAFFING in classes
    can_fill = await access.may(Action.EDIT, resource, DataClass.STAFFING)

    roles: list[dict[str, Any]] = []
    for role in data.roles:
        bars: list[dict[str, Any]] = []
        for item in role.bars:
            bar = item.bar
            about = Resource.allocation(assignment_id, bar.person_id)
            permitted = set(await access.classes(about, _ROLE_BAR_CLASSES - {A})) | {A}
            if DataClass.STAFFING not in permitted:
                continue
            bars.append(
                build_response(
                    RoleBarOut(
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
                        can_edit=await access.may(
                            Action.EDIT, about, DataClass.STAFFING
                        ),
                        category_mismatch=bar.category_mismatch,
                        line_category=bar.line_category,
                        person_category=bar.person_category,
                        starts_on=item.starts_on,
                        before_start=item.before_start,
                        outside_role_period=item.outside_role_period,
                    ),
                    permitted,
                )
            )
        body = build_response(
            RoleStaffingOut(
                budget_line_id=role.budget_line_id,
                description=role.description,
                role=role.role,
                fte=role.fte,
                start_date=role.start_date,
                end_date=role.end_date,
                months=[
                    RoleMonthOut(
                        month=m.month,
                        asked_pct=m.asked_pct,
                        filled_pct=m.filled_pct,
                        open_pct=m.open_pct,
                        over=m.over,
                        closed=m.closed,
                    )
                    for m in role.months
                ],
                bars=[],
                gaps=[
                    RoleGapOut(start=g.start, end=g.end, open_fte=g.open_fte)
                    for g in role.gaps
                ],
                fully_staffed=role.fully_staffed,
                names=sorted({item.bar.person_name for item in role.bars}),
                can_fill=can_fill,
            ),
            classes,
        )
        body["bars"] = bars if sees_time else []
        roles.append(body)

    head = build_response(
        AssignmentStaffingOut(
            assignment_id=assignment_id,
            months=list(data.months),
            current_month=data.current_month,
            closed_months=list(data.closed_months),
            tentative=data.tentative,
            roles=[],
            role_count=len(data.roles),
            staffed_count=data.staffed_count,
            open_fte=data.open_fte,
            open_from=data.open_from,
            overbooked_count=len(data.overbooked_person_ids),
        ),
        classes,
    )
    head["roles"] = roles
    return head
