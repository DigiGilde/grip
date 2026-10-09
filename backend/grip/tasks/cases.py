"""What the task engine knows about a case: its facts and its subjects.

A snapshot is read from the domain tables in a handful of queries for any
number of cases, and holds nothing the domain does not already hold. Every
fact in the catalogue is computed here and nowhere else.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.core import clock
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.audit_log import AuditLog
from grip.models.billing_delivery import BillingDelivery, BillingTerms
from grip.models.month_close import BillingExport, MonthClose
from grip.models.organisation import Organisation
from grip.models.outgoing_invoice import OutgoingInvoice, OutgoingInvoiceDelivery
from grip.models.person import Person
from grip.models.quote import Quote, QuoteApproval, QuoteOffer
from grip.models.task import OPEN_STATUSES, Task
from grip.models.vacancy import Vacancy
from grip.models.vacancy_hire import VacancyHire
from grip.services import (
    billing_corrections,
    billing_periods,
    phase,
    quote_approval,
    quote_budget,
)

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
_ASSIGNMENT_DONE = ("accounted", "cancelled")
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
    # The person the subject names, for a template whose assignee is "maker".
    person_id: UUID | None = None


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
    # Internal approval: a request exists only where the instance asks for
    # one, so the request itself is the trigger and no setting is read here.
    approvals = (
        await db.execute(
            select(
                QuoteApproval.id,
                QuoteApproval.quote_id,
                QuoteApproval.status,
                QuoteApproval.requested_by_id,
                QuoteApproval.requested_at,
                QuoteApproval.decided_at,
                Quote.assignment_id,
                Quote.reference,
            )
            .join(Quote, Quote.id == QuoteApproval.quote_id)
            .where(Quote.assignment_id.in_(ids), QuoteApproval.status != "withdrawn")
        )
    ).all()
    approvals_by_assignment = _grouped(approvals, "assignment_id")
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
    # How each assignment is billed: its own terms, or else the instance's.
    from grip.services import billing_deliveries, instance_settings

    default_rhythm = await instance_settings.get(
        db, billing_deliveries.DEFAULT_RHYTHM.key
    )
    rows = await db.execute(
        select(BillingTerms.assignment_id, BillingTerms.rhythm).where(
            BillingTerms.assignment_id.in_(ids)
        )
    )
    rhythms = {row[0]: row[1] for row in rows}
    deliveries = (
        await db.execute(
            select(
                BillingDelivery.assignment_id,
                BillingDelivery.period_key,
                BillingDelivery.delivered_at,
            ).where(BillingDelivery.assignment_id.in_(ids))
        )
    ).all()
    deliveries_by_assignment = _grouped(deliveries, "assignment_id")
    # Stored when the price of a delivered month changed: read, not priced.
    corrections_by_assignment = await billing_corrections.all_corrections(db, ids)
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
        own_approvals = approvals_by_assignment.get(assignment.id, [])
        ever_agreed = any(quote.status == "accepted" for quote in own_quotes)
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
            "verbally_agreed": status == phase.VERBALLY_AGREED,
            "accounted": status == "accounted",
            "rejected": status == "rejected",
            "cancelled": status == "cancelled",
            # A rejected quote is no end for who made it: the way on is a new
            # quote, or ending without an assignment. For the client who said
            # no it is the end, until a new quote comes in.
            "declined": status == "rejected" and is_client,
            "not_proceeded": status == "cancelled" and not ever_agreed,
        }

        rejected = [quote for quote in own_quotes if quote.status == "rejected"]
        live = [q for q in own_quotes if q.status in ("issued", "accepted")]
        # TODO(stand van een potentiële opdracht): the assignment screens get
        # one function for where a potential assignment stands (budget, quote
        # made, offered, accepted). The facts of the quote round below must
        # come from that function once it exists, not from this second copy.
        # Staffing comes into view once the work is agreed, or a quote is out:
        # a draft that nobody has seen yet is no reason to line people up.
        facts["staffing_in_view"] = (
            case_phase is not phase.Phase.POTENTIAL
            or bool(live)
            or status == phase.VERBALLY_AGREED
        )
        current = live[-1] if live else None
        round_number = len(rejected) + 1
        # Internal approval is a step of the course only for a quote that
        # needs it; asked per quote, since the rule can depend on its amount.
        approval_needed = False
        approval_given = False
        approval_asked = False
        no_approver = False
        # The rows above carry only what every case needs; the quote in
        # force is read whole, for its amount, its validity and its hash.
        in_force = (
            await db.get(Quote, current.id)
            if current is not None and current.status == "issued"
            else None
        )
        if in_force is not None and not is_client:
            approval = await quote_approval.state_of(db, in_force)
            approval_needed = approval.requirement.required
            approval_given = approval.approved
            approval_asked = approval.status in ("requested", "approved")
            no_approver = approval_needed and not approval.approver_available
        facts["approval_needed"] = approval_needed
        facts["approval_given"] = approval_given
        facts["approval_asked"] = approval_asked
        facts["no_approver"] = no_approver
        received = [q for q in own_quotes if q.status != "superseded"]
        facts["quote_received"] = is_client and bool(received)
        facts["quote_answered"] = (
            is_client and bool(received) and all(q.status != "issued" for q in received)
        )
        valid_until = (in_force.snapshot or {}).get("valid_until") if in_force else None
        expired = (
            in_force is not None
            and isinstance(valid_until, str)
            and valid_until < today.isoformat()
        )
        # A quote that no longer matches the budget leads nowhere: the step
        # is to make a new one. Asked only while it can still matter.
        outdated = False
        if (
            current is not None
            and current.status == "issued"
            and not is_client
            and case_phase is phase.Phase.POTENTIAL
        ):
            moved, _ = await quote_budget.budget_moved(db, assignment)
            outdated = bool(moved)
        sent_back = any(
            a.status == "sent_back"
            and a.decided_at is not None
            and not any(later.issued_at > a.decided_at for later in own_quotes)
            for a in own_approvals
        )
        # A quote that was sent back internally is no longer the one to go on with.
        fresh = current is not None and not expired and not outdated and not sent_back
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
                        "quote_rejected_before": bool(rejected) and current is None,
                        "quote_sent_back": sent_back,
                        "quote_expired": expired,
                        "quote_outdated": outdated,
                        "quote_fresh": fresh,
                        "quote_may_offer": fresh
                        and (not approval_needed or approval_given),
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
            "quote_approval": [
                Subject(
                    kind="quote_approval",
                    repeat_key=str(approval.id),
                    subject_id=str(approval.quote_id),
                    facts={"approval_decided": approval.status != "requested"},
                    anchors={
                        "approval_requested_on": clock.local_date(approval.requested_at)
                    },
                    variables={"kenmerk": approval.reference or ""},
                )
                for approval in own_approvals
            ],
            "sent_back_quote": [
                Subject(
                    kind="sent_back_quote",
                    repeat_key=str(approval.id),
                    subject_id=str(approval.quote_id),
                    facts={
                        "quote_superseded": any(
                            later.issued_at > approval.decided_at
                            for later in own_quotes
                        )
                    },
                    variables={"kenmerk": approval.reference or ""},
                    person_id=approval.requested_by_id,
                )
                for approval in own_approvals
                if approval.status == "sent_back" and approval.decided_at is not None
            ],
            # Per month, as an older plan asked; corrections are kept per
            # billing period now.
            "correction_month": [],
            "period_correction": _period_corrections(
                corrections_by_assignment.get(assignment.id, [])
            ),
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
                        "closed_on": clock.local_date(close.closed_at),
                        "delivered_on": min(
                            (clock.local_date(e.created_at) for e in delivered),
                            default=None,
                        ),
                    },
                    variables={"maand": month_label(month)},
                )
            )
        subjects["closed_month"] = closed_months
        subjects["billing_period"] = _billing_periods(
            rhythms.get(assignment.id, default_rhythm),
            months_with_inzet=_months_with_inzet(own_allocations, today),
            closed_by_month=closed_by_month,
            exports_by_close=exports_by_close,
            invoiced=invoiced,
            delivered_keys={
                d.period_key: clock.local_date(d.delivered_at)
                for d in deliveries_by_assignment.get(assignment.id, [])
            },
            corrections_open={
                row.period_key
                for row in corrections_by_assignment.get(assignment.id, [])
                if row.delivered_at is None
            },
            today=today,
        )

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


def _period_corrections(rows: list[Any]) -> list[Subject]:
    """One subject per billing period that has, or had, a difference to
    deliver. Done while no difference is open; a period whose only
    correction was undone has no subject, and its task lapses."""
    by_period: dict[str, list[Any]] = {}
    for row in rows:
        by_period.setdefault(row.period_key, []).append(row)
    subjects = []
    for key, own in sorted(by_period.items()):
        still_open = next((row for row in own if row.delivered_at is None), None)
        latest = still_open or own[-1]
        subjects.append(
            Subject(
                kind="period_correction",
                repeat_key=key,
                subject_id=str(latest.id),
                facts={"correction_delivered": still_open is None},
                anchors={"correction_arose_on": clock.local_date(latest.arose_at)},
                variables={"periode": period_words(key)},
            )
        )
    return subjects


def period_words(key: str) -> str:
    """A period key in words: "juli 2026", "het derde kwartaal van 2026"."""
    year, rest = key.split("-", 1)
    if rest.startswith("Q"):
        ordinal = ("eerste", "tweede", "derde", "vierde")[int(rest[1:]) - 1]
        return f"het {ordinal} kwartaal van {year}"
    return f"{MONTHS_NL[int(rest) - 1]} {year}"


def _billing_periods(
    rhythm: str,
    *,
    months_with_inzet: list[date],
    closed_by_month: dict[date, Any],
    exports_by_close: dict[Any, list[Any]],
    invoiced: set[UUID],
    delivered_keys: dict[str, date],
    corrections_open: set[str],
    today: date,
) -> list[Subject]:
    """The billing periods of an assignment that have work in them.

    A period is ready to deliver when every month in it with planned work is
    closed and nothing more can come: its last month is closed, or it is over.
    """
    from grip.calc import Month

    if rhythm not in billing_periods.RHYTHMS:
        rhythm = billing_periods.MONTHLY
    months = sorted(set(months_with_inzet) | set(closed_by_month))
    periods = billing_periods.periods_of([Month.of(m) for m in months], rhythm)
    with_work = set(months_with_inzet)
    subjects = []
    for period in periods:
        days = [m.first_day for m in period.months]
        closed = [closed_by_month[d] for d in days if d in closed_by_month]
        if not closed:
            continue
        open_work = [d for d in days if d in with_work and d not in closed_by_month]
        # A quarter runs to its calendar end, also when the work stops sooner.
        if rhythm == billing_periods.QUARTERLY:
            last = period.last
            while billing_periods.quarter_of(last.next()) == billing_periods.quarter_of(
                last
            ):
                last = last.next()
            period_end = last.last_day
        else:
            period_end = period.end
        ready = not open_work and (
            period_end < today or _month_start(period_end) in closed_by_month
        )
        exports = [e for close in closed for e in exports_by_close.get(close.id, [])]
        delivered_on = delivered_keys.get(period.key) or (
            max(clock.local_date(e.created_at) for e in exports)
            if exports
            and all(exports_by_close.get(close.id) for close in closed)
            and ready
            else None
        )
        subjects.append(
            Subject(
                kind="billing_period",
                repeat_key=period.key,
                # The months of the period, for the address of the invoice sheet.
                subject_id=",".join(month_key(d) for d in days),
                facts={
                    "period_ready": ready,
                    "period_delivered": delivered_on is not None,
                    "period_invoiced": bool(exports)
                    and all(e.id in invoiced for e in exports),
                    "period_correction_open": period.key in corrections_open,
                },
                anchors={
                    "ready_on": max(
                        clock.local_date(close.closed_at) for close in closed
                    ),
                    "delivered_on": delivered_on,
                },
                variables={"periode": period_words(period.key)},
            )
        )
    return subjects


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


async def _vacancy_text_subjects(
    db: AsyncSession, vacancies: Sequence[Vacancy]
) -> tuple[dict[UUID, dict[str, list[Subject]]], set[UUID]]:
    """The texts of each vacancy as subjects, and which vacancies have a
    public address recorded.

    A text a vacancy needs is a subject with where it stands; every person
    asked to judge its latest version is one too.
    """
    from grip.models.vacancy_text_flow import VacancyPublication
    from grip.services.vacancies import text_flow

    result: dict[UUID, dict[str, list[Subject]]] = {}
    for vacancy in vacancies:
        works = await text_flow.work_of(db, vacancy)
        texts: list[Subject] = []
        reviews: list[Subject] = []
        for kind, work in works.items():
            if not work.needed and not work.versions:
                continue
            word = text_flow.KIND_WORDS[kind]
            state = work.state
            returned_before = any(
                review.withdrawn_at is None
                and any(v.verdict == "remarks" for v in review.verdicts)
                for review in work.reviews
            )
            texts.append(
                Subject(
                    kind="text",
                    repeat_key=kind,
                    subject_id=kind,
                    facts={
                        "text_due": text_flow.is_due(vacancy, kind),
                        "text_in_review": state == text_flow.STATE_IN_REVIEW,
                        "text_returned": state == text_flow.STATE_RETURNED,
                        "text_settled": state == text_flow.STATE_SETTLED,
                        "text_moved_on": returned_before
                        and state != text_flow.STATE_RETURNED,
                        "text_written": state
                        in (
                            text_flow.STATE_IN_REVIEW,
                            text_flow.STATE_AGREED,
                            text_flow.STATE_SETTLED,
                        ),
                        "text_judged": state
                        in (text_flow.STATE_AGREED, text_flow.STATE_SETTLED),
                        # The reviewers agreed: only settling is left.
                        "text_agreed": state == text_flow.STATE_AGREED,
                        # A complete draft: offer it for review, or settle it.
                        "text_ready": state == text_flow.STATE_DRAFT
                        and not work.open_passages,
                    },
                    variables={"tekst": word},
                    person_id=work.writer_id,
                )
            )
            review = work.round
            if review is None:
                continue
            for verdict in review.verdicts:
                reviews.append(
                    Subject(
                        kind="text_review",
                        repeat_key=f"{kind}:{review.round}:{verdict.reviewer_id}",
                        subject_id=str(review.id),
                        facts={"verdict_given": verdict.verdict is not None},
                        anchors={"offered_on": clock.local_date(review.offered_at)},
                        variables={"tekst": word},
                        person_id=verdict.reviewer_id,
                    )
                )
        result[vacancy.id] = {"text": texts, "text_review": reviews}
    ids = [vacancy.id for vacancy in vacancies]
    published = set(
        await db.scalars(
            select(VacancyPublication.vacancy_id).where(
                VacancyPublication.vacancy_id.in_(ids)
            )
        )
    )
    return result, published


async def _request_form_facts(db: AsyncSession, vacancy: Vacancy) -> dict[str, bool]:
    """Where the request form of a vacancy stands.

    Only looked at while the request runs or was just approved: reading the
    kept form is work, and before or long after that nobody needs one.
    """
    from grip.repositories.vacancy import FormTemplateRepository
    from grip.services.vacancies import request_forms, service

    facts = {
        "request_form_in_use": False,
        "request_form_current": False,
        "request_form_signed": False,
    }
    if vacancy.status not in ("requested", "approved"):
        return facts
    template = await FormTemplateRepository(db).active(service.VACANCY_REQUEST_FORM)
    if template is None:
        return facts
    standing = await request_forms.standing(db, vacancy)
    return {
        "request_form_in_use": True,
        "request_form_current": bool(standing.versions) and not standing.changed,
        "request_form_signed": bool(standing.signed),
    }


def _request_prepared(vacancy: Vacancy) -> bool:
    """Everything the request itself asks for is filled in."""
    return bool(
        vacancy.fgr_function_name
        and vacancy.scale is not None
        and vacancy.contract_type
        and vacancy.addressee_name
    )


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
            # The request form names the requester and who advises: loaded
            # here, never by a lazy load in the middle of reading facts.
            .options(selectinload(Vacancy.decisions), selectinload(Vacancy.requester))
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

    text_subjects, published = await _vacancy_text_subjects(db, vacancies)

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
            "publication_recorded": vacancy.id in published,
            "request_prepared": status != "draft" or _request_prepared(vacancy),
            "approval_passed": status in ("approved", "open", "filled"),
            "filled": status == "filled",
            "rejected": status == "rejected",
            "withdrawn": status == "withdrawn",
            **await _request_form_facts(db, vacancy),
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
                    ],
                    **text_subjects.get(vacancy.id, {}),
                },
                people=people,
            )
        )
    return snapshots
