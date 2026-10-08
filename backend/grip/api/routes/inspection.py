"""Following an assignment as client: progress, spending and the final report.

Progress is asked from the contractor when the page is opened. Spending is
never a default: it is asked only when a person does so explicitly, and the
contractor answers only when the contract with this instance covers
financial inspection. A refusal for that reason is said as such.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import Access, DbSession, RequestAccess
from grip.core.audit import CREATE, record_audit
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.federation import terms
from grip.federation.contract_loader import (
    SERVICE_OPDRACHTVERKEER,
    operation,
    validation_errors,
)
from grip.federation.outway import (
    MissingGrantError,
    OutwayClient,
    OutwayNotConfiguredError,
)
from grip.federation.routes import get_outway_client
from grip.models.assignment import Assignment
from grip.schema.client_side import (
    BudgetUsageOut,
    BudgetUsageRequestIn,
    FinalReportOut,
    MilestoneOut,
    NotDeliveredOut,
    ProgressOut,
    UsageLineOut,
)
from grip.services import client_side
from grip.services.errors import NotFoundError

router = APIRouter(prefix="/client/assignments", tags=["client"])

_A = DataClass.ASSIGNMENT_BASIC
_B = DataClass.ASSIGNMENT_FINANCIAL

NO_INSTANCE = (
    "De opdrachtnemer heeft geen instantie waarmee deze instantie een "
    "contract heeft. Vraag de stand van zaken rechtstreeks op."
)
NOT_CONNECTED = "Deze instantie is niet verbonden met andere organisaties."
UNREACHABLE = "De opdrachtnemer is nu niet bereikbaar. Probeer het later opnieuw."
UNKNOWN_THERE = (
    "De opdrachtnemer kent deze opdracht niet. De aanvraag is daar mogelijk "
    "nog niet aangekomen."
)
BAD_ANSWER = "De opdrachtnemer gaf een antwoord dat niet aan het contract voldoet."
NOT_IN_CONTRACT = (
    "De opdrachtnemer geeft de uitputting niet: financiële inzage is geen "
    "onderdeel van wat met deze opdrachtnemer is afgesproken. De beheerder "
    "van de opdrachtnemer kan dat voor deze opdrachtgever aanzetten."
)


class PullResult:
    """The answer of the contractor in code names, or why there is none."""

    def __init__(
        self,
        body: dict[str, Any] | None = None,
        problem: str | None = None,
        *,
        forbidden: bool = False,
    ) -> None:
        self.body = body
        self.problem = problem
        self.forbidden = forbidden


async def _client_assignment(
    db: DbSession,
    access: Access,
    assignment_id: UUID,
    data_class: DataClass,
    settings: Settings,
) -> Assignment:
    """The assignment, if this instance is its client and the person may read it."""
    await access.require(
        Action.READ, Resource.assignment(assignment_id), _A, hide_existence=True
    )
    row = await client_side.client_assignment(db, assignment_id, settings)
    if row is None:
        raise NotFoundError("Opdracht", assignment_id)
    if data_class is not _A:
        await access.require(Action.READ, Resource.assignment(assignment_id), _B)
    return row.assignment


async def _pull(
    db: DbSession,
    outway: OutwayClient,
    assignment: Assignment,
    operation_id: str,
    schema: str,
    params: dict[str, Any] | None = None,
) -> PullResult:
    peer = await client_side.contractor_peer(db, assignment)
    if peer is None:
        return PullResult(problem=NO_INSTANCE)
    op = operation(operation_id)
    path = op.url_path(
        **{
            terms.contract_parameter("assignmentId"): client_side.remote_assignment_id(
                assignment
            )
        }
    )
    try:
        response = await outway.request(
            peer, SERVICE_OPDRACHTVERKEER, "GET", path, params=params
        )
    except OutwayNotConfiguredError:
        return PullResult(problem=NOT_CONNECTED)
    except MissingGrantError:
        return PullResult(problem=NO_INSTANCE)
    except Exception:
        return PullResult(problem=UNREACHABLE)
    if response.status_code == 403:
        return PullResult(forbidden=True)
    if response.status_code == 404:
        return PullResult(problem=UNKNOWN_THERE)
    if response.status_code != 200:
        return PullResult(problem=UNREACHABLE)
    try:
        body = response.json()
    except ValueError:
        return PullResult(problem=BAD_ANSWER)
    if validation_errors(terms.schema(schema), body):
        return PullResult(problem=BAD_ANSWER)
    translated: dict[str, Any] = terms.from_contract(body)
    return PullResult(body=translated)


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _cents(money: Any) -> int | None:
    if isinstance(money, dict) and isinstance(money.get("amount_cents"), int):
        return int(money["amount_cents"])
    return None


@router.get("/{assignment_id}/progress", response_model=None)
async def get_progress(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    outway: OutwayClient = Depends(get_outway_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The progress of the assignment, as the contractor reports it now."""
    assignment = await _client_assignment(db, access, assignment_id, _A, settings)
    result = await _pull(db, outway, assignment, "getProgress", "progress")
    now = datetime.now(UTC)
    if result.body is None:
        value = ProgressOut(
            available=False,
            fetched_at=now,
            problem=result.problem
            or "De opdrachtnemer geeft de voortgang niet aan deze instantie.",
        )
    else:
        body = result.body
        value = ProgressOut(
            available=True,
            fetched_at=now,
            status=body.get("status"),
            as_of=_date(body.get("as_of")),
            summary=body.get("summary"),
            milestones=[
                MilestoneOut(
                    description=item.get("description") or "",
                    due_date=_date(item.get("due_date")),
                    state=item.get("state"),
                )
                for item in body.get("milestones") or []
            ],
            delivered=[str(item) for item in body.get("delivered") or []],
            not_delivered=[str(item) for item in body.get("not_delivered") or []],
        )
    permitted = await access.classes(
        Resource.assignment(assignment.id), schema_classes(type(value))
    )
    return build_response(value, permitted)


@router.post("/{assignment_id}/budget-usage", response_model=None)
async def request_budget_usage(
    assignment_id: UUID,
    body: BudgetUsageRequestIn,
    access: RequestAccess,
    db: DbSession,
    person: CurrentPerson,
    outway: OutwayClient = Depends(get_outway_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Ask the contractor for the spending. An explicit act, and logged as one."""
    assignment = await _client_assignment(db, access, assignment_id, _B, settings)
    params = {terms.contract_parameter("year"): body.year} if body.year else None
    result = await _pull(
        db, outway, assignment, "getBudgetUsage", "budget-usage", params
    )
    now = datetime.now(UTC)
    record_audit(
        db,
        actor=person,
        action=CREATE,
        entity="budget_usage_requested",
        entity_id=assignment.id,
        new_value={
            "year": body.year,
            "answered": result.body is not None,
            "refused_by_contract": result.forbidden,
        },
    )
    if result.body is None:
        value = BudgetUsageOut(
            available=False,
            not_in_contract=result.forbidden,
            problem=NOT_IN_CONTRACT if result.forbidden else result.problem,
            fetched_at=now,
        )
    else:
        answer = result.body
        value = BudgetUsageOut(
            available=True,
            fetched_at=now,
            as_of=_date(answer.get("as_of")),
            year=answer.get("year"),
            budgeted_cents=_cents(answer.get("budgeted")),
            used_cents=_cents(answer.get("used")),
            available_cents=_cents(answer.get("available")),
            lines=[
                UsageLineOut(
                    description=line.get("description") or "",
                    budgeted_cents=_cents(line.get("budgeted")),
                    used_cents=_cents(line.get("used")),
                    available_cents=_cents(line.get("available")),
                )
                for line in answer.get("lines") or []
            ],
        )
    permitted = await access.classes(
        Resource.assignment(assignment.id), schema_classes(type(value))
    )
    return build_response(value, permitted)


@router.get("/{assignment_id}/final-report", response_model=None)
async def get_final_report(
    assignment_id: UUID,
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The final report the contractor delivered, when it came in."""
    assignment = await _client_assignment(db, access, assignment_id, _A, settings)
    report = await client_side.final_report(db, assignment.id)
    if report is None:
        value = FinalReportOut(received=False)
    else:
        period = report.get("period") or {}
        value = FinalReportOut(
            received=True,
            received_at=_datetime(report.get("received_at")),
            issued_at=_datetime(report.get("issued_at")),
            period_start=_date(period.get("start_date")),
            period_end=_date(period.get("end_date")),
            summary=report.get("summary"),
            agreed=[str(item) for item in report.get("agreed") or []],
            delivered=[str(item) for item in report.get("delivered") or []],
            not_delivered=[
                NotDeliveredOut(
                    description=item.get("description") or "",
                    reason=item.get("reason"),
                )
                if isinstance(item, dict)
                else NotDeliveredOut(description=str(item))
                for item in report.get("not_delivered") or []
            ],
            total_cost_cents=_cents(report.get("total_cost")),
        )
    permitted = await access.classes(
        Resource.assignment(assignment.id), schema_classes(type(value))
    )
    return build_response(value, permitted)
