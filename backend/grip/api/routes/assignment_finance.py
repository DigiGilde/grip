"""The financial state of one assignment: the Financieel tab and its export."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Response

from grip import calc
from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess, YearFilter, parse_year
from grip.schema.finance import (
    AssignmentFinanceOut,
    CostAmountOut,
    FiguresOut,
    FinanceLineOut,
    KeyFiguresOut,
    LinePreviewIn,
    LinePreviewOut,
    MonthRowOut,
    PersonAmountOut,
    SignalOut,
)
from grip.services import assignment_finance as finance
from grip.services import assignments, pricing
from grip.services.overview_attention import correction_due

router = APIRouter(tags=["finance"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
D = DataClass.PERSON_RATE
_PERSON_CLASSES = schema_classes(PersonAmountOut)


def figures_out(figures: finance.Figures | None) -> FiguresOut | None:
    if figures is None:
        return None
    return FiguresOut(
        budgeted_cents=figures.budgeted_cents,
        realised_cents=figures.realised_cents,
        planned_cents=figures.planned_cents,
        costs_realised_cents=figures.costs_realised_cents,
        costs_forecast_cents=figures.costs_forecast_cents,
        costs_cents=figures.costs_cents,
        expected_total_cents=figures.expected_total_cents,
        variance_cents=figures.variance_cents,
        variance_pct=figures.variance_pct,
        overrun=figures.overrun,
        realised_total_cents=figures.realised_total_cents,
        realised_pct=figures.realised_pct,
    )


async def _require_financial(assignment_id: UUID, access: RequestAccess) -> Resource:
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    await access.require(Action.READ, resource, B)
    return resource


@router.get("/assignments/{assignment_id}/financial", response_model=None)
async def get_assignment_finance(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    year: YearFilter = None,
) -> dict[str, Any]:
    """Budget, realised, planned, costs, expected total and variance.

    For whoever may read class B of the assignment. The amounts per person
    behind a line are class D and decided per person.
    """
    await _require_financial(assignment_id, access)
    data = await finance.assignment_finance(db, assignment_id, year=parse_year(year))
    key = data.key_figures

    try:
        differences = await pricing.rate_differences(db, assignment_id)
    except calc.CalcError:
        differences = ()

    lines: list[dict[str, Any]] = []
    for item in data.lines:
        # The cause next to the variance it explains: named for who may see
        # what the person bills, otherwise only that a rate changed and when.
        causes: list[str] = []
        for difference in differences:
            if difference.budget_line_id != item.line.id:
                continue
            named = await access.may(
                Action.READ,
                Resource.allocation(assignment_id, difference.person_id),
                D,
            )
            text = difference.text if named else difference.generic_text
            if text not in causes:
                causes.append(text)
        persons: list[dict[str, Any]] = []
        hidden = 0
        for person in item.persons:
            permitted = await access.classes(
                Resource.allocation(assignment_id, person.person_id), _PERSON_CLASSES
            )
            if D not in permitted:
                hidden += 1
                continue
            persons.append(
                build_response(
                    PersonAmountOut(
                        allocation_id=person.allocation_id,
                        person_id=person.person_id,
                        person_name=person.person_name,
                        start_date=person.start_date,
                        end_date=person.end_date,
                        realised_cents=person.realised_cents,
                        planned_cents=person.planned_cents,
                        total_cents=person.total_cents,
                        category_mismatch=person.category_mismatch,
                    ),
                    permitted,
                )
            )
        body = FinanceLineOut(
            budget_line_id=item.line.id,
            description=item.line.description,
            kind=item.line.kind,
            rate_category=item.line.rate_category,
            figures=figures_out(item.figures),
            pricing_error=item.pricing_error,
            rate_difference_notes=causes,
            persons=[],
            persons_hidden=hidden,
            costs=[
                CostAmountOut(
                    cost_item_id=c.cost_item_id,
                    description=c.description,
                    pct=c.pct,
                    realised_cents=c.realised_cents,
                    forecast_cents=c.forecast_cents,
                    total_cents=c.total_cents,
                )
                for c in item.costs
            ],
        ).model_dump(mode="json")
        body["persons"] = persons
        lines.append(body)

    head = AssignmentFinanceOut(
        assignment_id=assignment_id,
        name=data.row.assignment.name,
        year=data.year,
        reference_month=data.reference_month,
        key_figures=KeyFiguresOut(
            agreed_cents=key.agreed_cents,
            budgeted_cents=key.budgeted_cents,
            expected_total_cents=key.expected_total_cents,
            agreed_minus_budgeted_cents=key.agreed_minus_budgeted_cents,
            budgeted_minus_expected_cents=key.budgeted_minus_expected_cents,
            realised_cents=key.realised_cents,
            realised_pct=key.realised_pct,
            delivered_cents=key.delivered_cents,
            to_deliver_cents=key.to_deliver_cents,
            invoiced_cents=key.invoiced_cents,
            to_invoice_cents=key.to_invoice_cents,
        ),
        totals=figures_out(data.totals),
        pricing_error=data.pricing_error,
        lines=[],
        months=[
            MonthRowOut(
                month=m.month,
                closed=m.closed,
                budgeted_cents=m.budgeted_cents,
                planned_cents=m.planned_cents,
                realised_cents=m.realised_cents,
                cumulative_budgeted_cents=m.cumulative_budgeted_cents,
                cumulative_realised_cents=m.cumulative_realised_cents,
                cumulative_planned_open_cents=m.cumulative_planned_open_cents,
                cumulative_expected_cents=m.cumulative_expected_cents,
                cumulative_variance_cents=m.cumulative_variance_cents,
            )
            for m in data.months
        ],
        budgeted_outside_months_cents=data.budgeted_outside_months_cents,
        signals=[
            SignalOut(
                kind=s.kind,
                budget_line_id=s.budget_line_id,
                description=s.description,
                amount_cents=s.amount_cents,
                pct=s.pct,
                count=s.count,
                months=list(s.months),
            )
            for s in data.signals
        ],
        free_room_threshold_pct=data.free_room_threshold_pct,
    )
    correction = await correction_due(db, assignment_id, differences)
    if correction is not None:
        head.signals.append(
            SignalOut(
                kind="correction_due",
                budget_line_id=None,
                description=correction.cause,
                amount_cents=correction.amount_cents,
                pct=None,
                count=len(correction.months),
                months=list(correction.months),
            )
        )
    # The reader has class B (required above), so everything but the persons
    # is theirs; build_response still drops what a schema marks otherwise.
    result = build_response(head, {A, B})
    result["lines"] = lines
    return result


@router.get("/assignments/{assignment_id}/financial/csv")
async def get_assignment_finance_csv(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    year: YearFilter = None,
    section: Literal["lines", "months"] = "lines",
) -> Response:
    """The table of the Financieel tab as CSV. No names of persons.

    Columns: ``assignment_finance.LINE_CSV_COLUMNS`` or ``MONTH_CSV_COLUMNS``.
    """
    await _require_financial(assignment_id, access)
    selected = parse_year(year)
    data = await finance.assignment_finance(db, assignment_id, year=selected)
    content = (
        finance.lines_csv(data) if section == "lines" else finance.months_csv(data)
    )
    period = "hele-looptijd" if selected is None else str(selected)
    name = "regels" if section == "lines" else "maanden"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="financieel-{name}-{period}.csv"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/assignments/{assignment_id}/budget-lines/preview", response_model=None)
async def preview_budget_line(
    assignment_id: UUID,
    body: LinePreviewIn,
    access: RequestAccess,
    db: DbSession,
) -> dict[str, Any]:
    """What a budget line with these values would be budgeted at. Saves nothing.

    The form shows this as the outcome while it is being filled in, so the
    browser never computes an amount itself.
    """
    await _require_financial(assignment_id, access)
    start, end, period_name = body.start_date, body.end_date, "de periode"
    if body.period_source == "assignment":
        # A following line is priced over the period of the assignment.
        assignment = await assignments.get_assignment(db, assignment_id)
        start, end = assignment.start_date, assignment.end_date
        period_name = "de looptijd van de opdracht"
    preview = await finance.preview_budget_line(
        db,
        kind=body.kind,
        fte=body.fte,
        rate_category=body.rate_category,
        start_date=start,
        end_date=end,
        amount_cents=body.amount_cents,
        year=body.year,
        period_name=period_name,
    )
    return build_response(
        LinePreviewOut(
            budgeted_cents=preview.budgeted_cents,
            budgeted_by_year={str(y): c for y, c in preview.budgeted_by_year.items()},
            reason=preview.reason,
        ),
        {B},
    )
