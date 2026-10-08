"""What this instance answers when another one asks.

Every provider answers for one peer and one pull operation. It first asks
the access model what this peer may read; what it may not read is not in the
answer, and an assignment it has no relation with is "not found". Answers
are built in code names; the route translates and validates them. A status
goes out as the other organisation should see it: a status that only this
side knows (a verbal agreement) reads as the one before it, so nothing the
contract does not know ever leaves.

Data classes: a client gets class A and, only when the contract with it
covers financial inspection, class B. It never gets names. A parent instance
gets A and B of everything, and staffing as head counts unless this instance
allows names. A corpus system gets, for assignments that refer to its
nodes, class A and the spending in totals.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import DataClass, Resource
from grip.access.peer_deps import PeerAccess
from grip.calc import CalcError, Month
from grip.federation.bridge.access import peer_access, pull_context
from grip.federation.bridge.organisations import organisation_by_id, reference
from grip.federation.models import Peer
from grip.federation.problems import FederationProblem
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.cost import CostItem
from grip.models.person import Person
from grip.models.person_details import PersonScale
from grip.models.vacancy import Vacancy
from grip.repositories.domain import (
    AssignmentRepository,
    CostRepository,
    MonthCloseRepository,
)
from grip.services import month_close, pricing
from grip.services.assignments import is_shared_with
from grip.services.errors import DomainError
from grip.services.phase import counterparty_status

CURRENCY = "EUR"
Answer = dict[str, Any] | None


def _money(cents: int) -> dict[str, Any]:
    return {"amount_cents": cents, "currency": CURRENCY}


def _decimal_text(value: Decimal) -> str:
    text = format(Decimal(value).normalize(), "f")
    return text if text != "-0" else "0"


def _today() -> str:
    return date.today().isoformat()


def _month(text: str) -> Month:
    year, month = text.split("-")
    return Month(int(year), int(month))


def _period(start: date | None, end: date | None) -> dict[str, Any] | None:
    if start is None:
        return None
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
    }


def _forbidden(what: str) -> FederationProblem:
    return FederationProblem(
        403,
        "Inzage niet toegestaan",
        f"Inzage in {what} is voor deze opdrachtgever niet toegestaan. "
        "De opdrachtnemer staat die op verzoek toe.",
    )


async def _assignment_by_id(db: AsyncSession, assignment_id: UUID) -> Assignment | None:
    """The assignment whose URI ends in this id.

    The id in a path is the uuid of the assignment URI, which the client
    minted. On the contractor's side the row has its own primary key.
    """
    rows = (
        (
            await db.execute(
                select(Assignment).where(Assignment.uri.like(f"%/{assignment_id}"))
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if len(rows) == 1 else None


async def _readable(
    db: AsyncSession, access: PeerAccess, peer: Peer, assignment_id: UUID
) -> Assignment | None:
    assignment = await _assignment_by_id(db, assignment_id)
    # A client reads what was exchanged with it. An assignment that names it
    # as client but was never shared with its instance is not there for it.
    if assignment is None or not is_shared_with(assignment, peer.base_uri):
        return None
    resource = Resource.assignment(assignment.id)
    if not await access.reads(resource, DataClass.ASSIGNMENT_BASIC, pull_context(peer)):
        return None
    return assignment


async def _assignment_body(db: AsyncSession, assignment: Assignment) -> dict[str, Any]:
    """Class A of an assignment."""
    body: dict[str, Any] = {
        "uri": assignment.uri,
        "name": assignment.name,
        "kind": assignment.kind,
        "status": counterparty_status(assignment.status),
        "context_refs": list(assignment.context_refs or []),
        "parent_assignment_uri": assignment.parent_assignment_uri,
    }
    client = reference(await organisation_by_id(db, assignment.client_organisation_id))
    contractor = reference(
        await organisation_by_id(db, assignment.contractor_organisation_id)
    )
    body["client"] = client
    if contractor is not None:
        body["contractor"] = contractor
    period = _period(assignment.start_date, assignment.end_date)
    if period is not None:
        body["period"] = period
    return body


async def _totals(
    db: AsyncSession, assignment: Assignment, year: int | None = None
) -> pricing.AssignmentOverview:
    return await pricing.assignment_overview(db, assignment.id, year=year)


def _pricing_problem(error: Exception) -> FederationProblem:
    return FederationProblem(
        409,
        "Bedragen niet te berekenen",
        "De bedragen van deze opdracht zijn nu niet te berekenen, "
        "bijvoorbeeld omdat een tarievenkaart ontbreekt.",
    )


# --- for the client of an assignment ---------------------------------------


async def get_assignment(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    assignment = await _readable(
        db, peer_access(db, peer), peer, parameters["assignmentId"]
    )
    if assignment is None:
        return None
    return await _assignment_body(db, assignment)


async def get_progress(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    assignment = await _readable(
        db, peer_access(db, peer), peer, parameters["assignmentId"]
    )
    if assignment is None:
        return None
    return {
        "assignment_uri": assignment.uri,
        "status": counterparty_status(assignment.status),
        "as_of": _today(),
    }


async def _financial(
    db: AsyncSession, peer: Peer, assignment_id: UUID, what: str
) -> Assignment | None:
    """The assignment, if this peer may read its financial data.

    No relation is "not found". A relation without the financial part of the
    contract is a refusal the client can act on.
    """
    access = peer_access(db, peer)
    assignment = await _readable(db, access, peer, assignment_id)
    if assignment is None:
        return None
    if not await access.reads(
        Resource.assignment(assignment.id),
        DataClass.ASSIGNMENT_FINANCIAL,
        pull_context(peer),
    ):
        raise _forbidden(what)
    return assignment


async def get_budget_usage(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    assignment = await _financial(db, peer, parameters["assignmentId"], "de uitputting")
    if assignment is None:
        return None
    year = parameters.get("year")
    try:
        overview = await _totals(db, assignment, year)
    except (CalcError, DomainError) as error:
        raise _pricing_problem(error) from error
    lines = {
        line.id: line
        for line in await AssignmentRepository(db).budget_lines([assignment.id])
    }
    return {
        "assignment_uri": assignment.uri,
        "as_of": _today(),
        "year": year,
        "budgeted": _money(overview.budgeted_cents),
        "used": _money(overview.used_cents),
        "available": _money(overview.available_cents),
        # Per budget line: the role or the item, never who fills it.
        "lines": [
            {
                "description": lines[item.budget_line_id].description,
                "budgeted": _money(item.budgeted_cents),
                "used": _money(item.used_cents),
                "available": _money(item.available_cents),
            }
            for item in overview.lines
            if item.budget_line_id in lines
        ],
    }


async def _billing_body(
    db: AsyncSession, assignment: Assignment, month: Month
) -> dict[str, Any] | None:
    """Billing data of a closed month, per budget line and without names."""
    if await MonthCloseRepository(db).in_force(assignment.id, month.first_day) is None:
        return None
    data = await month_close.billing_data(db, assignment.id, month)
    lines = {
        str(line.id): line
        for line in await AssignmentRepository(db).budget_lines([assignment.id])
    }
    per_line: dict[str, int] = defaultdict(int)
    for billed in data.lines:
        per_line[billed.budget_line_id] += billed.amount_cents
    return {
        "assignment_uri": assignment.uri,
        "month": f"{month.year:04d}-{month.month:02d}",
        "basis": "actual_allocation",
        "lines": [
            {
                "description": lines[line_id].description
                if line_id in lines
                else "Inzet",
                "amount": _money(cents),
            }
            for line_id, cents in per_line.items()
        ],
        "total": _money(data.total_cents),
        "closed_at": data.closed_at.astimezone(UTC).isoformat(),
    }


async def get_billing_data(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    assignment = await _financial(
        db, peer, parameters["assignmentId"], "de factuurgegevens"
    )
    if assignment is None:
        return None
    try:
        return await _billing_body(db, assignment, _month(parameters["month"]))
    except (CalcError, DomainError) as error:
        raise _pricing_problem(error) from error


# --- for a corpus system ---------------------------------------------------


async def list_assignments_by_node(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    """Assignments that refer to a node, for the corpus that holds the node."""
    access = peer_access(db, peer)
    context = pull_context(peer)
    found = []
    for assignment in await AssignmentRepository(db).list(
        node_uri=parameters["nodeUri"]
    ):
        if not await access.reads(
            Resource.assignment(assignment.id), DataClass.ASSIGNMENT_BASIC, context
        ):
            continue
        found.append(assignment)
    page, page_size = parameters.get("page", 1), parameters.get("pageSize", 20)
    results = []
    for assignment in found[(page - 1) * page_size : page * page_size]:
        body = await _assignment_body(db, assignment)
        if (await access.spending_totals(assignment.id)).allowed:
            try:
                overview = await _totals(db, assignment)
            except (CalcError, DomainError):
                overview = None
            if overview is not None:
                body["spending"] = {
                    "budgeted": _money(overview.budgeted_cents),
                    "used": _money(overview.used_cents),
                    "as_of": _today(),
                }
        results.append(body)
    return {
        "results": results,
        "page": page,
        "page_size": page_size,
        "total": len(found),
    }


# --- hand-over to the parent instance --------------------------------------


async def _parent_reads(
    db: AsyncSession, peer: Peer, resource: Resource, data_class: DataClass
) -> bool:
    return await peer_access(db, peer).reads(resource, data_class, pull_context(peer))


def _no_handover() -> FederationProblem:
    return FederationProblem(
        403, "Geen toegang", "Deze doorgifte is alleen voor de moederinstantie."
    )


async def get_handover_assignments(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    access = peer_access(db, peer)
    context = pull_context(peer)
    results = []
    for assignment in await AssignmentRepository(db).list():
        resource = Resource.assignment(assignment.id)
        if not (
            await access.reads(resource, DataClass.ASSIGNMENT_BASIC, context)
            and await access.reads(resource, DataClass.ASSIGNMENT_FINANCIAL, context)
        ):
            continue
        try:
            overview = await _totals(db, assignment)
        except (CalcError, DomainError):
            # An assignment that cannot be priced is left out, not guessed.
            continue
        results.append(
            {
                "assignment": await _assignment_body(db, assignment),
                "quoted_amount": _money(assignment.quoted_amount_cents)
                if assignment.quoted_amount_cents is not None
                else None,
                "budgeted": _money(overview.budgeted_cents),
                "used": _money(overview.used_cents),
                "available": _money(overview.available_cents),
            }
        )
    return {"as_of": _today(), "results": results}


async def get_handover_billing_data(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    access = peer_access(db, peer)
    context = pull_context(peer)
    month = _month(parameters["month"])
    results = []
    for assignment in await AssignmentRepository(db).list():
        if not await access.reads(
            Resource.assignment(assignment.id),
            DataClass.ASSIGNMENT_FINANCIAL,
            context,
        ):
            continue
        try:
            body = await _billing_body(db, assignment, month)
        except (CalcError, DomainError):
            continue
        if body is not None:
            results.append(body)
    return {"month": parameters["month"], "results": results}


async def get_handover_staffing(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    """Who is deployed in a month: head counts per role, or persons.

    Names leave this instance only when its beheerder switched that on; the
    access model decides, this function only shapes the answer.
    """
    month = _month(parameters["month"])
    with_names = await _parent_reads(
        db, peer, Resource.assignment(), DataClass.STAFFING
    )
    if not with_names and not await _parent_reads(
        db, peer, Resource.instance(), DataClass.STAFFING_COUNTS
    ):
        raise _no_handover()
    rows = (
        await db.execute(
            select(Allocation, BudgetLine, Assignment, Person)
            .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
            .join(Assignment, Assignment.id == BudgetLine.assignment_id)
            .join(Person, Person.id == Allocation.person_id)
            .where(
                Allocation.start_date <= month.last_day,
                Allocation.end_date >= month.first_day,
            )
            .order_by(Assignment.name, BudgetLine.position, Person.name)
        )
    ).all()
    period = {
        "start_date": month.first_day.isoformat(),
        "end_date": month.last_day.isoformat(),
    }
    results: list[dict[str, Any]] = []
    if with_names:
        for allocation, line, assignment, person in rows:
            entry: dict[str, Any] = {
                "assignment_uri": assignment.uri,
                "person": {"name": person.name, "email": person.email},
                "fte_pct": _decimal_text(allocation.fte_pct),
                "period": _period(allocation.start_date, allocation.end_date),
            }
            if line.role:
                entry["role"] = line.role
            results.append(entry)
    else:
        groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for allocation, line, assignment, _person in rows:
            groups[(assignment.uri, line.role or line.description)].append(allocation)
        for (assignment_uri, role), allocations in groups.items():
            results.append(
                {
                    "assignment_uri": assignment_uri,
                    "headcount": len({a.person_id for a in allocations}),
                    "role": role,
                    "fte_pct": _decimal_text(
                        sum((a.fte_pct for a in allocations), Decimal(0))
                    ),
                    "period": period,
                }
            )
    return {"period": period, "results": results}


async def get_handover_capacity(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    """Deployed, available and sought capacity of this instance, today.

    Capacity is one FTE for every active person with a billing scale valid
    today; deployed is the sum of today's allocations; available is what is
    left. Sought is the FTE of the open vacancies.
    """
    if not await _parent_reads(
        db, peer, Resource.instance(), DataClass.STAFFING_COUNTS
    ):
        raise _no_handover()
    today = date.today()
    percentages = (
        (
            await db.execute(
                select(Allocation.fte_pct).where(
                    Allocation.start_date <= today, Allocation.end_date >= today
                )
            )
        )
        .scalars()
        .all()
    )
    deployed = sum(percentages, Decimal(0)) / Decimal(100)
    people = (
        (
            await db.execute(
                select(PersonScale.person_id)
                .join(Person, Person.id == PersonScale.person_id)
                .where(
                    Person.is_active.is_(True),
                    PersonScale.valid_from <= today,
                    (PersonScale.valid_to.is_(None)) | (PersonScale.valid_to >= today),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    open_vacancies = (
        (await db.execute(select(Vacancy.fte).where(Vacancy.status == "open")))
        .scalars()
        .all()
    )
    available = max(Decimal(len(people)) - deployed, Decimal(0))
    return {
        "as_of": _today(),
        "deployed_fte": _decimal_text(deployed),
        "available_fte": _decimal_text(available),
        "sought_fte": _decimal_text(sum(open_vacancies, Decimal(0))),
        "open_roles": len(open_vacancies),
    }


async def get_handover_costs(
    db: AsyncSession, peer: Peer, parameters: dict[str, Any]
) -> Answer:
    """Cost items with their coverage. A cost item is not tied to one year;
    the year selects the invoice lines that make up the forecast."""
    if not await _parent_reads(
        db, peer, Resource.cost_item(), DataClass.ASSIGNMENT_FINANCIAL
    ):
        raise _no_handover()
    year = parameters["year"]
    items = (
        (await db.execute(select(CostItem).order_by(CostItem.description)))
        .scalars()
        .all()
    )
    costs = CostRepository(db)
    assignments = AssignmentRepository(db)
    results = []
    for item in items:
        # Rules R6 to R8 live in the calculation module; this only selects
        # the invoice lines of the year and shapes the answer.
        calc_item = pricing.to_calc_cost_item(item)
        year_lines = tuple(
            pricing.to_calc_invoice_line(line)
            for line in await costs.invoice_lines([item.id])
            if line.period is not None and line.period.year == year
        )
        coverage = []
        covered = 0
        for share in await costs.coverages_of_item(item.id):
            lines = await assignments.budget_lines_by_id([share.budget_line_id])
            if not lines:
                continue
            assignment = await assignments.get(lines[0].assignment_id)
            if assignment is None:
                continue
            amount = calc.coverage_amount(
                pricing.to_calc_coverage(share), calc_item, year_lines
            )
            covered += amount
            coverage.append(
                {
                    "assignment_uri": assignment.uri,
                    "budget_line": lines[0].description,
                    "pct": _decimal_text(share.pct),
                    "amount": _money(amount),
                }
            )
        results.append(
            {
                "description": item.description,
                "budgeted": _money(item.budgeted_cents),
                "forecast": _money(calc.forecast(calc_item, year_lines)),
                "covered": _money(covered),
                "coverage": coverage,
            }
        )
    return {"year": year, "results": results}


PROVIDERS = {
    "listAssignmentsByNode": list_assignments_by_node,
    "getAssignment": get_assignment,
    "getProgress": get_progress,
    "getBudgetUsage": get_budget_usage,
    "getBillingData": get_billing_data,
    "getHandoverAssignments": get_handover_assignments,
    "getHandoverBillingData": get_handover_billing_data,
    "getHandoverStaffing": get_handover_staffing,
    "getHandoverCapacity": get_handover_capacity,
    "getHandoverCosts": get_handover_costs,
}
