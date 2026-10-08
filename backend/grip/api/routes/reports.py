"""Reports: per assignment, steering inside the organisation, and the year account.

Three rules hold for everything here:

- A total is taken over exactly the rows the reader may see, and says so in
  ``scope``: ``all`` when the reader sees everything through a function,
  ``own`` when the rows follow from the reader's relations. ``scope`` is
  decided from the function, not from the data, so it does not tell whether
  rows exist that the reader does not see.
- A block of the steering overview the reader may see nothing of is absent,
  not empty.
- The version of an assignment report meant for the client carries classes A
  and B only: no names of staff, whoever asks for it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess
from grip.api.routes.assignment_finance import figures_out
from grip.calc import Month
from grip.core.config import Settings, get_settings
from grip.schema.kpi import KpiOut
from grip.schema.overview import TotalsOut
from grip.schema.reports import (
    AgreedLineOut,
    AgreedOut,
    AssignmentReportOut,
    BillabilityOut,
    CostCoverageItemOut,
    CostCoverageOut,
    FinalReportOut,
    NotDeployableOut,
    OccupancyCellOut,
    OccupancyMonthOut,
    OccupancyOut,
    OccupancyPartOut,
    OccupancySummaryOut,
    OpenRoleOut,
    OpenRolesOut,
    PersonOccupancyOut,
    PipelineOut,
    PipelineQuoteOut,
    PipelineStatusOut,
    ReportCostOut,
    ReportLineOut,
    ReportMonthOut,
    ReportPeriodOut,
    ReportStaffingOut,
    StatusChangeOut,
    TurnoverMonthOut,
    TurnoverOut,
    YearAccountOut,
    YearAccountRowOut,
    YearAccountTotalsOut,
    YearAmountOut,
)
from grip.services import assignment_views as views
from grip.services.reports import assignment_report as assignment_reports
from grip.services.reports import steering, year_account
from grip.services.reports.document import render_report_html

router = APIRouter(prefix="/reports", tags=["reports"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
COUNTS = DataClass.STAFFING_COUNTS
F = DataClass.PERSON_KPI

_CLIENT_CLASSES = frozenset({A, B})
_STAFFING_CLASSES = schema_classes(ReportStaffingOut)
_REPORT_CLASSES = schema_classes(AssignmentReportOut) - _STAFFING_CLASSES
_KPI_CLASSES = schema_classes(KpiOut)

# The printable report is a page of its own: it gets a policy that allows its
# inline stylesheet and nothing else, and it is never cached.
DOCUMENT_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "Cache-Control": "private, no-store",
}

Audience = Annotated[
    Literal["client", "internal"],
    Query(description="client: classes A and B only. internal: adds staffing."),
]
Year = Annotated[
    int | None,
    Query(ge=2000, le=2100, description="A budget year. Default: this year."),
]


def _year(value: int | None) -> int:
    return value or date.today().year


def _totals(totals: views.Totals | None) -> TotalsOut | None:
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


async def _sees_all_financial(access: RequestAccess) -> bool:
    """Whether the reader reads class B of every assignment, through a function."""
    return await access.may(Action.READ, Resource.assignment(), B)


async def _financial_scope(
    access: RequestAccess,
) -> tuple[str, set[UUID] | None] | None:
    """Which assignments' amounts the reader may add up.

    ``("all", None)`` for a reader who sees them all, ``("own", ids)`` for one
    who sees them through a relation, ``None`` for one who sees none.
    """
    if await _sees_all_financial(access):
        return "all", None
    own = {
        assignment_id
        for assignment_id in await access.own_assignment_ids()
        if await access.may(Action.READ, Resource.assignment(assignment_id), B)
    }
    return ("own", own) if own else None


# -- report per assignment ----------------------------------------------------


async def _assignment_report(
    assignment_id: UUID,
    audience: str,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    report = await assignment_reports.assignment_report(db, assignment_id)
    permitted = await access.classes(resource, _REPORT_CLASSES)
    internal = audience == "internal"
    if not internal:
        permitted = permitted & _CLIENT_CLASSES

    view = report.view
    assignment = view.row.assignment
    agreed = report.agreed
    body = build_response(
        AssignmentReportOut(
            assignment_id=assignment.id,
            uri=assignment.uri,
            name=assignment.name,
            kind=assignment.kind,
            status=assignment.status,
            client_name=view.row.client_name,
            contractor_name=view.row.contractor_name,
            start_date=assignment.start_date,
            end_date=assignment.end_date,
            context_refs=list(assignment.context_refs or []),
            audience=audience,
            generated_on=date.today(),
            months_total=len(report.months),
            months_closed=report.closed_month_count,
            agreed=AgreedOut(
                quote_id=agreed.quote_id,
                quote_uri=agreed.quote_uri,
                issued_at=agreed.issued_at,
                accepted_at=agreed.accepted_at,
                form=agreed.form,
                total_cents=agreed.total_cents,
                lines=[
                    AgreedLineOut(
                        description=line.description,
                        kind=line.kind,
                        role=line.role,
                        fte=line.fte,
                        start_date=line.start_date,
                        end_date=line.end_date,
                        amount_cents=line.amount_cents,
                    )
                    for line in agreed.lines
                ],
                subtotals=[
                    YearAmountOut(year=year, amount_cents=cents)
                    for year, cents in agreed.subtotals
                ],
            )
            if agreed is not None
            else None,
            quoted_amount_cents=assignment.quoted_amount_cents,
            status_history=[
                StatusChangeOut(
                    occurred_at=change.occurred_at,
                    old_status=change.old_status,
                    new_status=change.new_status,
                    reason=change.reason,
                )
                for change in report.status_history
            ],
            final_report=FinalReportOut(
                issued_at=report.final_report.issued_at,
                summary=report.final_report.summary,
                delivered=list(report.final_report.delivered),
                not_delivered=list(report.final_report.not_delivered),
            )
            if report.final_report is not None
            else None,
            months=[
                ReportMonthOut(
                    month=str(state.month),
                    closed=state.closed,
                    closed_at=state.closed_at,
                )
                for state in report.months
            ],
            totals=_totals(view.totals),
            pricing_error=view.pricing_error,
            periods=[
                ReportPeriodOut(
                    year=period.year,
                    totals=_totals(period.totals),
                    pricing_error=period.pricing_error,
                )
                for period in report.periods
            ],
            lines=[
                ReportLineOut(
                    budget_line_id=line_view.line.id,
                    description=line_view.line.description,
                    kind=line_view.line.kind,
                    totals=_totals(line_view.overview),
                    pricing_error=line_view.pricing_error,
                )
                for line_view in view.lines
            ],
            costs=[
                ReportCostOut(
                    cost_item_id=cost.cost_item_id,
                    description=cost.description,
                    budget_line_description=cost.budget_line_description,
                    pct=cost.pct,
                    amount_cents=cost.amount_cents,
                )
                for cost in report.costs
            ],
            staffing=[],
        ),
        permitted,
    )

    # Who worked on it is decided per person, and only for the internal
    # version: the client's version never names staff.
    body.pop("staffing", None)
    if internal:
        staffing: list[dict[str, Any]] = []
        for member in report.staffing:
            member_classes = await access.classes(
                Resource.allocation(assignment_id, member.person_id), _STAFFING_CLASSES
            )
            if ROSTER not in member_classes:
                continue
            staffing.append(
                build_response(
                    ReportStaffingOut(
                        person_id=member.person_id,
                        person_name=member.person_name,
                        budget_line_description=member.budget_line_description,
                        role=member.role,
                        start_date=member.start_date,
                        end_date=member.end_date,
                        fte_pct=member.fte_pct,
                    ),
                    member_classes,
                )
            )
        if staffing:
            body["staffing"] = staffing
    return body


@router.get("/assignments/{assignment_id}", response_model=None)
async def get_assignment_report(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    audience: Audience = "client",
) -> dict[str, Any]:
    """What was agreed, what was delivered and what it cost, for one assignment."""
    return await _assignment_report(assignment_id, audience, access, db)


@router.get("/assignments/{assignment_id}/document", response_class=HTMLResponse)
async def get_assignment_report_document(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    audience: Audience = "client",
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """The same report as a printable page, built from the filtered response."""
    body = await _assignment_report(assignment_id, audience, access, db)
    return HTMLResponse(
        render_report_html(body, instance_name=settings.INSTANCE_NAME),
        headers=DOCUMENT_HEADERS,
    )


# -- steering -----------------------------------------------------------------


async def _turnover_block(
    access: RequestAccess, db: DbSession, year: int
) -> dict[str, Any] | None:
    scope = await _financial_scope(access)
    if scope is None:
        return None
    name, ids = scope
    data = await steering.turnover(db, year, assignment_ids=ids)
    figures = figures_out(await steering.agreed_figures(db, year, assignment_ids=ids))
    assert figures is not None
    return build_response(
        TurnoverOut(
            scope=name,
            months=[
                TurnoverMonthOut(
                    month=str(m.month),
                    realised_cents=m.realised_cents,
                    forecast_cents=m.forecast_cents,
                    verbal_cents=m.verbal_cents,
                    pipeline_cents=m.pipeline_cents,
                )
                for m in data.months
            ],
            realised_cents=data.realised_cents,
            forecast_cents=data.forecast_cents,
            verbal_cents=data.verbal_cents,
            pipeline_cents=data.pipeline_cents,
            expected_cents=data.realised_cents + data.forecast_cents,
            figures=figures,
            unpriced_assignments=list(data.unpriced),
        ),
        {B},
    )


def _occupancy_month(month: steering.OccupancyMonth) -> OccupancyMonthOut:
    return OccupancyMonthOut(
        month=str(month.month),
        allocated_fte=month.allocated_fte,
        tentative_fte=month.tentative_fte,
        available_fte=month.available_fte,
        free_fte=month.free_fte,
        pct=month.pct,
        under=month.under,
        full=month.full,
        over=month.over,
    )


async def _occupancy_person(
    access: RequestAccess,
    row: steering.PersonOccupancy,
    classes: frozenset[DataClass],
    *,
    now: steering.OccupancyCell | None,
    idle_ahead: bool,
    last_inzet_end: date | None,
) -> dict[str, Any]:
    """One row of the occupancy, with the parts of each cell.

    The name of an assignment is class A of that assignment, so it is
    decided per assignment; the percentage belongs to the person.
    """
    person = build_response(
        PersonOccupancyOut(
            person_id=row.person_id,
            person_name=row.person_name,
            average_pct=row.average_pct,
            over_months=[str(month) for month in row.over_months],
            now_pct=now.pct if now is not None and now.available else None,
            idle_ahead=idle_ahead,
            last_inzet_end=last_inzet_end,
            cells=[],
        ),
        classes,
    )
    cells: list[dict[str, Any]] = []
    for cell in row.cells:
        body = build_response(
            OccupancyCellOut(
                month=str(cell.month),
                available=cell.available,
                pct=cell.pct,
                tentative_pct=cell.tentative_pct,
                established=cell.established,
                parts=[],
            ),
            {C},
        )
        parts: list[dict[str, Any]] = []
        for part in cell.parts:
            named = await access.may(
                Action.READ, Resource.assignment(part.assignment_id), A
            )
            parts.append(
                build_response(
                    OccupancyPartOut(
                        assignment_id=part.assignment_id,
                        assignment_name=part.assignment_name,
                        pct=part.pct,
                        tentative=part.tentative,
                        verbally_agreed=part.verbally_agreed,
                        established=part.established,
                    ),
                    {C, A} if named else {C},
                )
            )
        body["parts"] = parts
        cells.append(body)
    person["cells"] = cells
    return person


async def _occupancy_block(
    access: RequestAccess, db: DbSession, year: int
) -> dict[str, Any] | None:
    sees_all = await access.may(Action.READ, Resource.person(), C)
    person_classes = frozenset({ROSTER, C})

    async def visible_of(
        rows: list[steering.PersonOccupancy],
    ) -> list[steering.PersonOccupancy]:
        return [
            row
            for row in rows
            if C in await access.classes(Resource.person(row.person_id), person_classes)
        ]

    year_months = steering.months_of(year)
    all_rows = await steering.occupancy(db, year_months)
    visible = await visible_of(all_rows)
    if not visible:
        return None
    # Every figure below is over the visible persons only, so it says
    # nothing about anyone else.
    window = steering.next_months(Month.of(date.today()), 4)
    in_block = {row.person_id for row in visible}
    window_rows = [
        row for row in await steering.occupancy(db, window) if row.person_id in in_block
    ]
    summary = steering.occupancy_summary(visible, window_rows, window)
    idle = steering.idle_person_ids(window_rows, window)
    now_cells = {row.person_id: row.cells[0] for row in window_rows}
    last_end = await steering.last_inzet_end(db, in_block)

    block = build_response(
        OccupancyOut(
            scope="all" if sees_all else "own",
            summary=OccupancySummaryOut(
                person_count=summary.person_count,
                average_pct=summary.average_pct,
                over_count=summary.over_count,
                over_months=[str(month) for month in summary.over_months],
                current_month=str(summary.current_month),
                window=[_occupancy_month(month) for month in summary.window],
                idle_count=summary.idle_count,
            ),
            months=[
                _occupancy_month(month)
                for month in steering.occupancy_months(year_months, visible)
            ],
            persons=[],
            not_deployable=[],
        ),
        {COUNTS},
    )
    block["persons"] = [
        await _occupancy_person(
            access,
            row,
            person_classes,
            now=now_cells.get(row.person_id),
            idle_ahead=row.person_id in idle,
            last_inzet_end=last_end.get(row.person_id),
        )
        for row in visible
    ]
    left_out = []
    for person_id, person_name in await steering.not_deployable(
        db, [row.person_id for row in all_rows]
    ):
        if C in await access.classes(Resource.person(person_id), person_classes):
            left_out.append(
                build_response(
                    NotDeployableOut(person_id=person_id, person_name=person_name),
                    {ROSTER},
                )
            )
    block["not_deployable"] = left_out
    return block


async def _pipeline_block(
    access: RequestAccess, db: DbSession, year: int
) -> dict[str, Any] | None:
    scope = await _financial_scope(access)
    if scope is None:
        return None
    name, ids = scope
    quotes = await steering.quotes_of_year(db, year, assignment_ids=ids)
    statuses = []
    for quote_status in steering.QUOTE_STATUSES:
        matching = [q for q in quotes if q.status == quote_status]
        statuses.append(
            PipelineStatusOut(
                status=quote_status,
                count=len(matching),
                total_cents=sum(q.total_cents for q in matching),
            )
        )
    return build_response(
        PipelineOut(
            scope=name,
            statuses=statuses,
            waiting=[
                PipelineQuoteOut(
                    quote_id=q.quote_id,
                    assignment_id=q.assignment_id,
                    assignment_name=q.assignment_name,
                    client_name=q.client_name,
                    status=q.status,
                    total_cents=q.total_cents,
                    issued_at=q.issued_at,
                    valid_until=q.valid_until,
                )
                for q in quotes
                if q.status == "issued"
            ],
        ),
        {B},
    )


async def _costs_block(
    access: RequestAccess, db: DbSession, year: int
) -> dict[str, Any] | None:
    # A cost item that does not exist is readable only through a function,
    # so this tells whether the reader sees every item without looking at any.
    sees_all = await access.may(Action.READ, Resource.cost_item(uuid4()), B)
    items = [
        item
        for item in await steering.cost_items(db, year)
        if sees_all
        or await access.may(Action.READ, Resource.cost_item(item.item.id), B)
    ]
    if not sees_all and not items:
        return None
    return build_response(
        CostCoverageOut(
            scope="all" if sees_all else "own",
            forecast_cents=sum(i.forecast_cents for i in items),
            covered_cents=sum(i.covered_cents or 0 for i in items),
            uncovered_cents=sum(i.uncovered_cents or 0 for i in items),
            items=[
                CostCoverageItemOut(
                    cost_item_id=i.item.id,
                    description=i.item.description,
                    forecast_cents=i.forecast_cents,
                    covered_cents=i.covered_cents,
                    uncovered_cents=i.uncovered_cents,
                    pct_total=i.pct_total,
                )
                for i in items
            ],
        ),
        {B},
    )


async def _billability_block(
    access: RequestAccess, db: DbSession, year: int
) -> dict[str, Any] | None:
    sees_all = await access.may(Action.READ, Resource.person(), F)
    persons: list[dict[str, Any]] = []
    target = realised = forecast = 0
    with_target = below_target = 0
    for person_id, person_name in await steering.kpi_person_ids(db, year):
        classes = await access.classes(Resource.person(person_id), _KPI_CLASSES)
        if F not in classes:
            continue
        row = await steering.kpi_row(db, person_id, person_name, year)
        overview = row.overview
        if overview is not None:
            target += overview.target_cents or 0
            realised += overview.realised_cents
            forecast += overview.forecast_cents
            if overview.target_cents is not None:
                with_target += 1
                if overview.realisation_cents < overview.target_cents:
                    below_target += 1
        persons.append(
            build_response(
                KpiOut(
                    person_id=person_id,
                    person_name=person_name,
                    year=year,
                    target_pct=overview.target_pct if overview else None,
                    target_cents=overview.target_cents if overview else None,
                    realised_cents=overview.realised_cents if overview else None,
                    forecast_cents=overview.forecast_cents if overview else None,
                    realisation_cents=overview.realisation_cents if overview else None,
                    unavailable_reason=None
                    if overview
                    else (
                        "De KPI kan niet worden berekend: voor dit jaar ontbreekt "
                        "een actieve tarievenkaart of een inzetschaal."
                    ),
                ),
                classes,
            )
        )
    if not persons:
        return None
    block = build_response(
        BillabilityOut(
            scope="all" if sees_all else "own",
            persons=[],
            target_cents=target,
            realised_cents=realised,
            forecast_cents=forecast,
            realisation_cents=realised + forecast,
            with_target_count=with_target,
            below_target_count=below_target,
        ),
        {F},
    )
    block["persons"] = persons
    return block


async def _open_roles_block(
    access: RequestAccess, db: DbSession
) -> dict[str, Any] | None:
    sees_all = await access.may(Action.READ, Resource.assignment(), C)
    roles = []
    for role in await steering.open_roles(db):
        if sees_all or (
            role.assignment_id is not None
            and await access.may(
                Action.READ, Resource.assignment(role.assignment_id), C
            )
        ):
            roles.append(role)
    if not sees_all and not roles:
        return None
    return build_response(
        OpenRolesOut(
            scope="all" if sees_all else "own",
            unfilled_fte=sum((r.unfilled_fte for r in roles), Decimal(0)),
            roles=[
                OpenRoleOut(
                    assignment_id=r.assignment_id,
                    assignment_name=r.assignment_name,
                    budget_line_id=r.budget_line_id,
                    description=r.description,
                    unfilled_fte=r.unfilled_fte,
                    start_date=r.start_date,
                    end_date=r.end_date,
                    vacancy_status=r.vacancy_status,
                )
                for r in roles
            ],
        ),
        {C},
    )


@router.get("/steering", response_model=None)
async def get_steering(
    access: RequestAccess, db: DbSession, year: Year = None
) -> dict[str, Any]:
    """The steering overview of a year. A block the reader may not see is absent."""
    selected = _year(year)
    result: dict[str, Any] = {"year": selected}
    blocks = {
        "turnover": await _turnover_block(access, db, selected),
        "occupancy": await _occupancy_block(access, db, selected),
        "pipeline": await _pipeline_block(access, db, selected),
        "costs": await _costs_block(access, db, selected),
        "billability": await _billability_block(access, db, selected),
        "open_roles": await _open_roles_block(access, db),
    }
    result.update({name: block for name, block in blocks.items() if block is not None})
    return result


# -- year account -------------------------------------------------------------


async def _year_account_rows(
    access: RequestAccess, db: DbSession, year: int
) -> tuple[str, list[tuple[year_account.YearAccountRow, frozenset[DataClass]]]]:
    """The rows the reader may see, each with the classes permitted on it."""
    sees_all = await access.may(Action.READ, Resource.assignment(), A)
    ids = None if sees_all else await access.own_assignment_ids()
    rows = await year_account.year_account(db, year, assignment_ids=ids)
    classes = schema_classes(YearAccountRowOut)
    visible = []
    for row in rows:
        permitted = await access.classes(
            Resource.assignment(row.row.assignment.id), classes
        )
        if A in permitted:
            visible.append((row, permitted))
    return ("all" if sees_all else "own"), visible


@router.get("/year-account", response_model=None)
async def get_year_account(
    access: RequestAccess, db: DbSession, year: Year = None
) -> dict[str, Any]:
    """Assignments received and carried out in a budget year, with their amounts."""
    selected = _year(year)
    scope, visible = await _year_account_rows(access, db, selected)
    items: list[dict[str, Any]] = []
    with_amounts: list[year_account.YearAccountRow] = []
    for row, permitted in visible:
        assignment = row.row.assignment
        totals = row.totals
        if B in permitted:
            with_amounts.append(row)
        items.append(
            build_response(
                YearAccountRowOut(
                    assignment_id=assignment.id,
                    uri=assignment.uri,
                    name=assignment.name,
                    kind=assignment.kind,
                    client_name=row.row.client_name,
                    status=assignment.status,
                    start_date=assignment.start_date,
                    end_date=assignment.end_date,
                    agreed_cents=row.agreed_cents,
                    budgeted_cents=totals.budgeted_cents if totals else None,
                    realised_cents=totals.realised_cents if totals else None,
                    forecast_cents=totals.forecast_cents if totals else None,
                    costs_cents=totals.coverage_cents if totals else None,
                    delivered_cents=row.delivered_cents,
                    to_deliver_cents=row.to_deliver_cents,
                    invoiced_cents=row.invoiced_cents,
                    to_invoice_cents=row.to_invoice_cents,
                    difference_cents=row.difference_cents,
                    pricing_error=row.pricing_error,
                ),
                permitted,
            )
        )
    result = build_response(
        YearAccountOut(year=selected, scope=scope, rows=[], totals=None), {A}
    )
    result["rows"] = items
    if with_amounts:
        priced = [r.totals for r in with_amounts if r.totals is not None]
        result["totals"] = YearAccountTotalsOut(
            agreed_cents=sum(r.agreed_cents or 0 for r in with_amounts),
            budgeted_cents=sum(t.budgeted_cents for t in priced),
            realised_cents=sum(t.realised_cents for t in priced),
            forecast_cents=sum(t.forecast_cents for t in priced),
            costs_cents=sum(t.coverage_cents for t in priced),
            delivered_cents=sum(r.delivered_cents for r in with_amounts),
            to_deliver_cents=sum(r.to_deliver_cents or 0 for r in with_amounts),
            invoiced_cents=sum(r.invoiced_cents for r in with_amounts),
            to_invoice_cents=sum(r.to_invoice_cents for r in with_amounts),
        ).model_dump(mode="json")
    return result


@router.get("/year-account/csv")
async def get_year_account_csv(
    access: RequestAccess, db: DbSession, year: Year = None
) -> Response:
    """The year account as CSV, with only the rows whose amounts the reader sees.

    The columns are ``year_account.CSV_COLUMNS``. No names of persons.
    """
    selected = _year(year)
    _scope, visible = await _year_account_rows(access, db, selected)
    rows = [row for row, permitted in visible if B in permitted]
    if not rows and not await _sees_all_financial(access):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Je hebt geen toegang tot de bedragen van de jaarverantwoording.",
        )
    return Response(
        content=year_account.to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="jaarverantwoording-{selected}.csv"'
            ),
            "Cache-Control": "private, no-store",
        },
    )
