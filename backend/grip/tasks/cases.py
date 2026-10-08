"""What the task engine knows about a case: its facts and its subjects.

A snapshot is read from the domain tables in a handful of queries for any
number of cases, and holds nothing the domain does not already hold. Every
fact in the catalogue is computed here and nowhere else.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.audit_log import AuditLog
from grip.models.month_close import BillingExport, MonthClose
from grip.models.organisation import Organisation
from grip.models.outgoing_invoice import OutgoingInvoice, OutgoingInvoiceDelivery
from grip.models.person import Person
from grip.models.quote import Quote, QuoteOffer
from grip.models.task import OPEN_STATUSES, Task
from grip.models.vacancy import Vacancy
from grip.models.vacancy_hire import VacancyHire
from grip.services import phase

MONTHS_NL = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)

# An unfilled remainder below this share of a full-time job is not a role
# to fill.
OPEN_ROLE_THRESHOLD = Decimal("0.05")
# Never look further back than this for months that were not closed.
MAX_MONTHS_BACK = 36
# How long after a hire the follow-up tasks of a filled vacancy stay in view.
HIRE_FOLLOW_UP_DAYS = 180

# Statuses in which nothing is left to do on a case.
_ASSIGNMENT_DONE = ("accounted", "rejected", "cancelled")
_VACANCY_LIVE = ("draft", "requested", "approved", "open")
_VACANCY_NEEDS_OPENING = ("regulier", "specialistisch")


def month_label(month: date) -> str:
    return f"{MONTHS_NL[month.month - 1]} {month.year}"


def month_key(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _next_month(month: date) -> date:
    return (month.replace(day=28) + timedelta(days=4)).replace(day=1)


def _month_end(month: date) -> date:
    return _next_month(month) - timedelta(days=1)


@dataclass
class Subject:
    """One thing on a case that a task can be about."""

    kind: str
    repeat_key: str = ""
    subject_id: str | None = None
    facts: dict[str, bool] = field(default_factory=dict)
    anchors: dict[str, date | None] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)


@dataclass
class CaseSnapshot:
    case_kind: str
    case_id: UUID
    assignment_id: UUID | None
    vacancy_id: UUID | None
    facts: dict[str, bool]
    subjects: dict[str, list[Subject]]
    # Persons a vacancy role resolves to ("requester", "decision:hr_advice").
    people: dict[str, UUID | None] = field(default_factory=dict)

    def subjects_of(self, kind: str) -> list[Subject]:
        return self.subjects.get(kind, [])


def _same_base(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.rstrip("/") == b.rstrip("/")  # type: ignore[union-attr]


async def open_task_case_ids(db: AsyncSession, case_kind: str) -> set[UUID]:
    """Cases that still have an open task from the plan."""
    column = Task.assignment_id if case_kind == "assignment" else Task.vacancy_id
    rows = await db.execute(
        select(column)
        .where(
            Task.case_kind == case_kind,
            Task.origin == "plan",
            Task.status.in_(OPEN_STATUSES),
            column.is_not(None),
        )
        .distinct()
    )
    return {row[0] for row in rows if row[0] is not None}


# --- assignments --------------------------------------------------------------


async def live_assignment_ids(db: AsyncSession) -> set[UUID]:
    """Assignments on which work may still arise, or that have open tasks."""
    rows = await db.execute(
        select(Assignment.id).where(Assignment.status.notin_(_ASSIGNMENT_DONE))
    )
    return {row[0] for row in rows} | await open_task_case_ids(db, "assignment")


def _grouped(rows: Any, key: str) -> dict[Any, list[Any]]:
    groups: dict[Any, list[Any]] = defaultdict(list)
    for row in rows:
        groups[getattr(row, key)].append(row)
    return groups


def _open_roles(
    lines: list[BudgetLine], allocations: dict[UUID, list[Allocation]], today: date
) -> list[Subject]:
    subjects = []
    for line in sorted(lines, key=lambda item: (item.position, str(item.id))):
        if line.kind != "personnel" or line.fte is None:
            continue
        if line.end_date is not None and line.end_date < today:
            continue
        reference = max(today, line.start_date) if line.start_date else today
        staffed = sum(
            (
                allocation.fte_pct
                for allocation in allocations.get(line.id, [])
                if allocation.start_date <= reference <= allocation.end_date
            ),
            Decimal(0),
        )
        remainder = line.fte - staffed / Decimal(100)
        subjects.append(
            Subject(
                kind="open_role",
                repeat_key=str(line.id),
                subject_id=str(line.id),
                facts={"role_staffed": remainder < OPEN_ROLE_THRESHOLD},
                anchors={"needed_from": line.start_date},
                variables={"rol": line.description or line.role or "rol"},
            )
        )
    return subjects


def _months_with_inzet(allocations: list[Allocation], today: date) -> list[date]:
    """Ended months in which someone was planned on the assignment."""
    if not allocations:
        return []
    last_ended = _month_start(today) - timedelta(days=1)
    first = _month_start(min(allocation.start_date for allocation in allocations))
    last = min(max(allocation.end_date for allocation in allocations), last_ended)
    floor = _month_start(last_ended)
    for _ in range(MAX_MONTHS_BACK - 1):
        floor = _month_start(floor - timedelta(days=1))
    month = max(first, floor)
    months = []
    while month <= last:
        end = _month_end(month)
        if any(a.start_date <= end and a.end_date >= month for a in allocations):
            months.append(month)
        month = _next_month(month)
    return months


async def load_assignment_cases(
    db: AsyncSession,
    assignment_ids: set[UUID],
    *,
    today: date,
    instance_base_uri: str,
) -> list[CaseSnapshot]:
    if not assignment_ids:
        return []
    ids = list(assignment_ids)
    assignments = (
        await db.scalars(select(Assignment).where(Assignment.id.in_(ids)))
    ).all()
    client_ids = {a.client_organisation_id for a in assignments} - {None}
    client_uris: dict[UUID, str | None] = {}
    if client_ids:
        rows = await db.execute(
            select(Organisation.id, Organisation.instance_uri).where(
                Organisation.id.in_(client_ids)
            )
        )
        client_uris = {row[0]: row[1] for row in rows}

    lines = (
        await db.scalars(select(BudgetLine).where(BudgetLine.assignment_id.in_(ids)))
    ).all()
    lines_by_assignment = _grouped(lines, "assignment_id")
    line_ids = [line.id for line in lines]
    allocations = (
        (
            await db.scalars(
                select(Allocation).where(Allocation.budget_line_id.in_(line_ids))
            )
        ).all()
        if line_ids
        else []
    )
    allocations_by_line = _grouped(allocations, "budget_line_id")

    # Only the columns a fact is read from: a table that other work is
    # extending does not break the engine.
    quotes = (
        await db.execute(
            select(Quote.id, Quote.assignment_id, Quote.status, Quote.issued_at)
            .where(Quote.assignment_id.in_(ids))
            .order_by(Quote.issued_at, Quote.created_at)
        )
    ).all()
    quotes_by_assignment = _grouped(quotes, "assignment_id")
    quote_ids = [quote.id for quote in quotes]
    offered: set[UUID] = set()
    if quote_ids:
        rows = await db.execute(
            select(QuoteOffer.quote_id).where(QuoteOffer.quote_id.in_(quote_ids))
        )
        offered = {row[0] for row in rows}

    closes = (
        await db.execute(
            select(
                MonthClose.id,
                MonthClose.assignment_id,
                MonthClose.month,
                MonthClose.closed_at,
            ).where(MonthClose.assignment_id.in_(ids), MonthClose.reopened_at.is_(None))
        )
    ).all()
    closes_by_assignment = _grouped(closes, "assignment_id")
    exports = (
        await db.execute(
            select(
                BillingExport.id, BillingExport.month_close_id, BillingExport.created_at
            ).where(BillingExport.assignment_id.in_(ids))
        )
    ).all()
    exports_by_close = _grouped(exports, "month_close_id")
    export_ids = [export.id for export in exports]
    invoiced: set[UUID] = set()
    if export_ids:
        rows = await db.execute(
            select(OutgoingInvoiceDelivery.billing_export_id)
            .join(
                OutgoingInvoice,
                OutgoingInvoice.id == OutgoingInvoiceDelivery.outgoing_invoice_id,
            )
            .where(
                OutgoingInvoiceDelivery.billing_export_id.in_(export_ids),
                OutgoingInvoice.withdrawn_at.is_(None),
            )
        )
        invoiced = {row[0] for row in rows}

    rows = await db.execute(
        select(AuditLog.entity_id).where(
            AuditLog.entity == "final_report",
            AuditLog.entity_id.in_([str(i) for i in ids]),
        )
    )
    reported = {row[0] for row in rows}

    snapshots = []
    for assignment in assignments:
        status = assignment.status
        own_lines = lines_by_assignment.get(assignment.id, [])
        own_allocations = [
            allocation
            for line in own_lines
            for allocation in allocations_by_line.get(line.id, [])
        ]
        own_quotes = quotes_by_assignment.get(assignment.id, [])
        is_client = _same_base(
            client_uris.get(assignment.client_organisation_id)
            if assignment.client_organisation_id
            else None,
            instance_base_uri,
        )
        case_phase = phase.phase_of(status)
        facts = {
            "external": assignment.kind == "external",
            "client": is_client,
            "contractor": not is_client,
            "potential": case_phase is phase.Phase.POTENTIAL,
            "agreed": status in ("accepted", "in_progress", "completed", "accounted"),
            "started": status in ("in_progress", "completed", "accounted"),
            "completed": status in ("completed", "accounted"),
            "closed": case_phase is phase.Phase.CLOSED,
            "budget_has_line": bool(own_lines),
            "budget_has_personnel_line": any(
                line.kind == "personnel" for line in own_lines
            ),
            "may_close_months": phase.allows_month_close(status),
            "may_bill": phase.allows_billing(status),
            "final_report_issued": str(assignment.id) in reported,
        }

        rejected = [quote for quote in own_quotes if quote.status == "rejected"]
        live = [q for q in own_quotes if q.status in ("issued", "accepted")]
        # Staffing comes into view once the work is agreed, or a quote is out:
        # a draft that nobody has seen yet is no reason to line people up.
        facts["staffing_in_view"] = (
            case_phase is not phase.Phase.POTENTIAL
            or bool(live)
            or status == phase.VERBALLY_AGREED
        )
        current = live[-1] if live else None
        round_number = len(rejected) + 1
        subjects: dict[str, list[Subject]] = {
            "case": [Subject(kind="case")],
            "quote_round": [
                Subject(
                    kind="quote_round",
                    repeat_key=f"ronde-{round_number}",
                    subject_id=str(current.id) if current else None,
                    facts={
                        "quote_issued": current is not None,
                        "quote_offered": current is not None
                        and (current.id in offered or current.status == "accepted"),
                        "quote_accepted": current is not None
                        and current.status == "accepted",
                    },
                )
            ],
            "rejected_quote": [
                Subject(
                    kind="rejected_quote",
                    repeat_key=str(quote.id),
                    subject_id=str(quote.id),
                    facts={
                        "quote_superseded": any(
                            later.issued_at > quote.issued_at for later in own_quotes
                        )
                    },
                )
                for quote in rejected
            ],
            "received_quote": [
                Subject(
                    kind="received_quote",
                    repeat_key=str(quote.id),
                    subject_id=str(quote.id),
                    facts={"quote_decided": quote.status != "issued"},
                )
                for quote in own_quotes
                if quote.status != "superseded"
            ],
            "open_role": _open_roles(own_lines, allocations_by_line, today),
        }

        closed_by_month = {
            close.month: close for close in closes_by_assignment.get(assignment.id, [])
        }
        subjects["month_to_close"] = [
            Subject(
                kind="month_to_close",
                repeat_key=month_key(month),
                subject_id=month_key(month),
                facts={"month_closed": month in closed_by_month},
                anchors={"month_end": _month_end(month)},
                variables={"maand": month_label(month)},
            )
            for month in _months_with_inzet(own_allocations, today)
        ]
        closed_months = []
        for month in sorted(closed_by_month):
            close = closed_by_month[month]
            delivered = exports_by_close.get(close.id, [])
            closed_months.append(
                Subject(
                    kind="closed_month",
                    repeat_key=month_key(month),
                    subject_id=month_key(month),
                    facts={
                        "billing_delivered": bool(delivered),
                        "invoice_recorded": any(e.id in invoiced for e in delivered),
                    },
                    anchors={
                        "closed_on": close.closed_at.date(),
                        "delivered_on": min(
                            (e.created_at.date() for e in delivered), default=None
                        ),
                    },
                    variables={"maand": month_label(month)},
                )
            )
        subjects["closed_month"] = closed_months

        snapshots.append(
            CaseSnapshot(
                case_kind="assignment",
                case_id=assignment.id,
                assignment_id=assignment.id,
                vacancy_id=None,
                facts=facts,
                subjects=subjects,
            )
        )
    return snapshots


# --- vacancies ----------------------------------------------------------------


async def live_vacancy_ids(db: AsyncSession, *, today: date) -> set[UUID]:
    rows = await db.execute(select(Vacancy.id).where(Vacancy.status.in_(_VACANCY_LIVE)))
    ids = {row[0] for row in rows}
    recent = today - timedelta(days=HIRE_FOLLOW_UP_DAYS)
    rows = await db.execute(
        select(VacancyHire.vacancy_id).where(VacancyHire.start_date >= recent)
    )
    ids |= {row[0] for row in rows}
    return ids | await open_task_case_ids(db, "vacancy")


async def load_vacancy_cases(
    db: AsyncSession, vacancy_ids: set[UUID]
) -> list[CaseSnapshot]:
    if not vacancy_ids:
        return []
    ids = list(vacancy_ids)
    vacancies = (
        await db.scalars(
            select(Vacancy)
            .where(Vacancy.id.in_(ids))
            .options(selectinload(Vacancy.decisions))
        )
    ).all()
    line_ids = {v.budget_line_id for v in vacancies} - {None}
    assignment_of_line: dict[UUID, UUID] = {}
    if line_ids:
        rows = await db.execute(
            select(BudgetLine.id, BudgetLine.assignment_id).where(
                BudgetLine.id.in_(line_ids)
            )
        )
        assignment_of_line = {row[0]: row[1] for row in rows}
    hires = {
        hire.vacancy_id: hire
        for hire in (
            await db.scalars(select(VacancyHire).where(VacancyHire.vacancy_id.in_(ids)))
        ).all()
    }
    person_ids = {hire.person_id for hire in hires.values()} - {None}
    persons: dict[UUID, Person] = {}
    if person_ids:
        persons = {
            person.id: person
            for person in (
                await db.scalars(select(Person).where(Person.id.in_(person_ids)))
            ).all()
        }

    snapshots = []
    for vacancy in vacancies:
        status = vacancy.status
        decisions = {decision.kind: decision for decision in vacancy.decisions}

        def given(kind: str, decisions: dict[str, Any] = decisions) -> bool:
            decision = decisions.get(kind)
            return decision is not None and decision.agreed is not None

        needs_opening = vacancy.vacancy_type in _VACANCY_NEEDS_OPENING
        hire = hires.get(vacancy.id)
        hired = persons.get(hire.person_id) if hire and hire.person_id else None
        facts = {
            "draft": status == "draft",
            "requested": status
            in ("requested", "approved", "rejected", "open", "filled"),
            "in_procedure": status == "requested",
            "hr_advice_given": given("hr_advice"),
            "control_advice_given": given("control_advice"),
            "advices_given": given("hr_advice") and given("control_advice"),
            "approval_given": given("approval"),
            "approved": status == "approved",
            "needs_opening": needs_opening,
            "opened": status in ("open", "filled"),
            "ready_to_fill": status == "open"
            or (status == "approved" and not needs_opening),
            "hire_recorded": hire is not None and status == "filled",
            "colleague_known_in_wies": hired is not None and bool(hired.wies_public_id),
            "colleague_has_email": hired is not None and bool(hired.email),
        }
        people: dict[str, UUID | None] = {"requester": vacancy.requester_id}
        for kind in ("hr_advice", "control_advice", "approval"):
            decision = decisions.get(kind)
            people[f"decision:{kind}"] = decision.person_id if decision else None
        if people["decision:approval"] is None:
            people["decision:approval"] = vacancy.addressee_id
        snapshots.append(
            CaseSnapshot(
                case_kind="vacancy",
                case_id=vacancy.id,
                assignment_id=assignment_of_line.get(vacancy.budget_line_id)
                if vacancy.budget_line_id
                else None,
                vacancy_id=vacancy.id,
                facts=facts,
                subjects={
                    "case": [
                        Subject(
                            kind="case",
                            anchors={"requested_on": vacancy.requested_on},
                        )
                    ]
                },
                people=people,
            )
        )
    return snapshots
