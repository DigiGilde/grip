"""What the start page says, in the same words as the rest of grip.

Nothing here decides who may see what. The route asks that per block and per
row and hands over the classes. Two steps keep a sentence inside its class, as
on the opened assignment: ``facts_of_many`` reads only the facts of the classes
it is given, and ``parts_of`` asks the classes again.

The rows of one assignment are read by ``assignment_parts.load_facts``. That is
made for one assignment, so here the facts of many are read together, from the
read models the lists already use.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.types import DataClass
from grip.calc import Month
from grip.federation.models import OUTBOX_DEAD, FederationOutbox
from grip.models.assignment import Assignment
from grip.models.audit_log import AuditLog
from grip.models.month_close import MonthClose
from grip.models.person import Person
from grip.repositories.domain import AssignmentRepository
from grip.services import (
    assignment_finance,
    billing_deliveries,
    client_side,
    read_cache,
    staffing,
    staffing_board,
)
from grip.services import assignment_views as views
from grip.services.assignment_parts import (
    BillingFacts,
    BudgetFacts,
    MonthFacts,
    OwnInzet,
    PartsFacts,
    own_line_of,
    parts_of,
    quote_facts,
)
from grip.services.billing_periods import month_name
from grip.services.phase import (
    STATUS_LABELS,
    Phase,
    allows_billing,
    phase_of,
)
from grip.services.pricing import to_calc_allocation
from grip.services.reports import investment, steering
from grip.services.vacancies import service as vacancies
from grip.tasks import course, engine
from grip.tasks.service import TaskView

B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL

MAX_CASES = 5
MAX_ROWS = 8
# How far ahead the start page warns about inzet that stops: this month and the
# three after it, the window of Bezetting.
SOON_MONTHS = 4

MONTH_TASK = "month_to_close"

_ATTENTION_PARTS = ("close", "budget", "team", "report")
_DELIVERY_PROBLEMS = {
    "dead": "De aanvraag is niet aangekomen",
    "rejected": "De aanvraag is geweigerd door de opdrachtnemer",
}


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _count(number: int, one: str, many: str) -> str:
    return f"{number} {one if number == 1 else many}"


def capped[T](rows: Sequence[T]) -> tuple[list[T], int]:
    """What a block shows, and how many there are."""
    return list(rows[:MAX_ROWS]), len(rows)


# -- what is to do ------------------------------------------------------------


@dataclass(frozen=True)
class CaseTasks:
    """The tasks of one case that need the reader, the first one first."""

    head: TaskView
    rest: tuple[TaskView, ...]

    @property
    def tasks(self) -> tuple[TaskView, ...]:
        return (self.head, *self.rest)

    @property
    def assignment_with_month(self) -> UUID | None:
        """The assignment, when one of these tasks is to close a month."""
        if any(view.task.subject_kind == MONTH_TASK for view in self.tasks):
            return self.head.task.assignment_id
        return None


def cases_of(views_in_order: Iterable[TaskView]) -> list[CaseTasks]:
    """One entry per case, in the order of the tasks handed in: soonest first."""
    found: dict[tuple[str, UUID | None], list[TaskView]] = {}
    for view in views_in_order:
        if not view.needs_me:
            continue
        task = view.task
        case_id = task.vacancy_id if task.case_kind == "vacancy" else task.assignment_id
        found.setdefault((task.case_kind, case_id), []).append(view)
    return [CaseTasks(tasks[0], tuple(tasks[1:])) for tasks in found.values()]


def top_five(cases: Sequence[CaseTasks]) -> list[CaseTasks]:
    """The first five, where the last place goes to the first case without a
    date if it would drop out: late months must not hide "Bied de offerte aan"."""
    top = list(cases[:MAX_CASES])
    if all(case.head.task.due_on is not None for case in top):
        undated = next(
            (case for case in cases[MAX_CASES:] if case.head.task.due_on is None),
            None,
        )
        if undated is not None:
            top[-1] = undated
    return top


def more_words(months: int, others: int) -> str | None:
    pieces = []
    if months:
        pieces.append(_count(months, "maand", "maanden"))
    if others:
        pieces.append(_count(others, "taak", "taken"))
    return f"daarna nog {' en '.join(pieces)}" if pieces else None


def more_text(case: CaseTasks, months_to_close: int | None) -> str | None:
    """What follows the first task. A month to close is one task however many
    months wait, so the months come from ``months_to_close``; None means the
    reader may not know how many, and then a month counts as any other task."""
    if months_to_close is None:
        return more_words(0, len(case.rest))
    head_is_month = case.head.task.subject_kind == MONTH_TASK
    months = months_to_close - 1 if head_is_month else months_to_close
    others = sum(1 for view in case.rest if view.task.subject_kind != MONTH_TASK)
    return more_words(max(months, 0), others)


async def months_to_close(
    db: AsyncSession, assignment_ids: Set[UUID], today: date
) -> dict[UUID, int]:
    """Per assignment how many months with inzet wait to be closed."""
    if not assignment_ids:
        return {}
    repo = AssignmentRepository(db)
    lines = await repo.budget_lines(assignment_ids)
    assignment_of = {line.id: line.assignment_id for line in lines}
    allocations: dict[UUID, list[Any]] = defaultdict(list)
    for allocation in await repo.allocations_on_lines(list(assignment_of)):
        allocations[assignment_of[allocation.budget_line_id]].append(allocation)
    closed: dict[UUID, list[date]] = defaultdict(list)
    for assignment_id, month in await db.execute(
        select(MonthClose.assignment_id, MonthClose.month).where(
            MonthClose.assignment_id.in_(assignment_ids),
            MonthClose.reopened_at.is_(None),
        )
    ):
        closed[assignment_id].append(month)
    return {
        assignment_id: len(
            assignment_finance.overdue_months(
                [to_calc_allocation(a) for a in allocations[assignment_id]],
                closed[assignment_id],
                today,
            )
        )
        for assignment_id in assignment_ids
    }


def case_path(case: CaseTasks) -> str:
    task = case.head.task
    if task.case_kind == "vacancy":
        return f"/vacatures/{task.vacancy_id}"
    if task.case_kind == "instance":
        return "/beheer/koppelingen"
    return f"/opdrachten/{task.assignment_id}"


# -- my work ------------------------------------------------------------------


@dataclass(frozen=True)
class OwnWork:
    assignment_id: UUID
    name: str
    line: str
    warning: str | None


def _soon(month: Month, today: date) -> bool:
    return month <= steering.next_months(Month.of(today), SOON_MONTHS)[-1]


async def own_work(db: AsyncSession, person_id: UUID, today: date) -> list[OwnWork]:
    """The inzet of this person that has not ended, per assignment, in the words
    of the assignment itself; what ends last says when the inzet stops."""
    allocations = await staffing.staffed_allocations(db, person_ids=[person_id])
    current = [a for a in allocations if a.end_date >= today]
    if not current:
        return []
    lines = {
        line.id: line
        for line in await AssignmentRepository(db).budget_lines_by_id(
            {a.budget_line_id for a in current}
        )
    }
    by_assignment: dict[UUID, list[OwnInzet]] = defaultdict(list)
    ends: dict[UUID, date] = {}
    for allocation in current:
        line = lines[allocation.budget_line_id]
        by_assignment[allocation.assignment_id].append(
            OwnInzet(
                role=line.role or line.description,
                fte_pct=allocation.fte_pct,
                start_date=allocation.start_date,
                end_date=allocation.end_date,
            )
        )
        ends[allocation.assignment_id] = max(
            allocation.end_date, ends.get(allocation.assignment_id, allocation.end_date)
        )
    names = dict(
        (
            await db.execute(
                select(Assignment.id, Assignment.name).where(
                    Assignment.id.in_(by_assignment)
                )
            )
        ).all()
    )
    last = max(by_assignment, key=lambda assignment_id: ends[assignment_id])
    stops = Month.of(ends[last]).next()
    work = [
        OwnWork(
            assignment_id=assignment_id,
            name=names[assignment_id],
            line=own_line_of(inzet, today) or "",
            warning=f"Geen inzet vanaf {month_name(stops)}"
            if assignment_id == last and _soon(stops, today)
            else None,
        )
        for assignment_id, inzet in by_assignment.items()
    ]
    work.sort(key=lambda row: (row.warning is None, row.name.lower()))
    return work


# -- my assignments -----------------------------------------------------------


@dataclass(frozen=True)
class MyAssignment:
    assignment_id: UUID
    name: str
    status: str
    # What the assignment asks, in the words of its rows.
    notice: str | None
    verdict: Literal["room", "overrun"] | None
    as_client: bool

    @property
    def rank(self) -> tuple[int, str]:
        attention = (
            0 if self.verdict == "overrun" else 1 if self.notice is not None else 2
        )
        return attention, self.name.lower()


def notice_of(facts: PartsFacts, classes: Set[DataClass]) -> str | None:
    """The first row that asks something. The stand of the assignment already
    says how far the quote is, and a number of lines is no request."""
    for part in parts_of(facts, classes):
        if part.key not in _ATTENTION_PARTS or part.notice is None:
            continue
        budget = facts.budget
        asks = budget is None or budget.over_budget or budget.not_priced
        if part.key == "budget" and not asks:
            continue
        return part.notice
    return None


def _verdict(
    data: assignment_finance.AssignmentFinance, status: str
) -> Literal["room", "overrun"] | None:
    """Against the budget of the whole period. A potential assignment has no
    expectation yet, so all of its budget would read as room."""
    totals = data.totals
    if totals is None or not totals.budgeted_cents:
        return None
    if phase_of(status) is Phase.POTENTIAL:
        return None
    return "overrun" if totals.overrun else "room"


def _billing_of(overview: billing_deliveries.Overview) -> BillingFacts | None:
    step = overview.next_step
    labels = {view.period.key: view.period.label for view in overview.periods}
    if step.kind == "deliver" and not step.correction:
        return BillingFacts("deliver", labels[step.period_key])
    if step.kind == "record_invoice":
        return BillingFacts("record_invoice", labels[step.period_key])
    return None


async def _reports_issued(db: AsyncSession, assignment_ids: Iterable[UUID]) -> set[str]:
    wanted = [str(assignment_id) for assignment_id in assignment_ids]
    if not wanted:
        return set()
    rows = await db.scalars(
        select(AuditLog.entity_id).where(
            AuditLog.entity == "final_report", AuditLog.entity_id.in_(wanted)
        )
    )
    return set(rows.all())


def _facts_of(
    assignment: Assignment,
    classes: Set[DataClass],
    data: assignment_finance.AssignmentFinance | None,
    overview: billing_deliveries.Overview | None,
    *,
    is_client: bool,
    report_issued: bool,
    open_roles: int,
) -> PartsFacts:
    """The facts ``load_facts`` reads for one assignment, of ``classes`` only,
    from what was read for all. They come from the money of the assignment:
    without it, and on the side of the client, there is only the kind and the
    status: a reader with C but not B gets no months and no open roles here. A
    naverrekening needs the months of one assignment, so it waits for the row
    on the assignment itself."""
    if data is None or is_client:
        return PartsFacts(
            kind=assignment.kind, status=assignment.status, is_client=is_client
        )
    overdue = next((s.count for s in data.signals if s.kind == "months_not_closed"), 0)
    lines = data.lines
    return PartsFacts(
        kind=assignment.kind,
        status=assignment.status,
        months=MonthFacts(
            overdue=overdue or 0, any_closed=data.reference_month is not None
        )
        if classes & {B, C}
        else None,
        budget=BudgetFacts(
            lines=len(lines),
            over_budget=sum(
                1 for item in lines if item.figures and item.figures.overrun
            ),
            not_priced=sum(1 for item in lines if item.figures is None),
        )
        if B in classes
        else None,
        billing=_billing_of(overview) if overview and B in classes else None,
        report_issued=report_issued if B in classes else None,
        has_personnel_line=bool(classes & {C, ROSTER, SIGNAL})
        and any(item.line.kind == "personnel" for item in lines),
        open_roles=open_roles if C in classes else None,
        other_scale=len(
            {
                person.person_id
                for item in lines
                for person in item.persons
                if person.category_mismatch
            }
        )
        if SIGNAL in classes
        else None,
    )


async def _open_roles(db: AsyncSession, today: date) -> list[vacancies.OpenRole]:
    return await read_cache.remember_all(
        db,
        "start_open_roles",
        today,
        lambda: vacancies.open_roles(db, today=today),
    )


@dataclass(frozen=True)
class AssignmentRead:
    """What the row of one assignment is made from."""

    assignment: Assignment
    facts: PartsFacts
    # Class B.
    finance: assignment_finance.AssignmentFinance | None


async def facts_of_many(
    db: AsyncSession,
    classes_of: Mapping[UUID, Set[DataClass]],
    today: date,
) -> list[AssignmentRead]:
    """``load_facts`` for many assignments together: of each only the facts
    of the classes in ``classes_of``, and no others."""
    rows = await views.assignment_rows(db, only_ids=list(classes_of))
    money = [row for row in rows if B in classes_of[row.assignment.id]]
    finances = await assignment_finance.assignment_finances(
        db, money, year=None, today=today
    )
    billable = [
        row.assignment.id
        for row in money
        if row.assignment.kind == "external" and allows_billing(row.assignment.status)
    ]
    overviews = await billing_deliveries.overviews(db, billable, today=today)
    reports = await _reports_issued(db, finances)
    own = await client_side.own_organisation_ids(db)
    roles: dict[UUID, int] = defaultdict(int)
    if any(C in classes for classes in classes_of.values()):
        for role in await _open_roles(db, today):
            roles[role.assignment_id] += 1
    return [
        AssignmentRead(
            assignment=row.assignment,
            facts=_facts_of(
                row.assignment,
                classes_of[row.assignment.id],
                finances.get(row.assignment.id),
                overviews.get(row.assignment.id),
                is_client=row.assignment.client_organisation_id in own,
                report_issued=str(row.assignment.id) in reports,
                open_roles=roles[row.assignment.id],
            ),
            finance=finances.get(row.assignment.id),
        )
        for row in rows
    ]


async def my_assignments(
    db: AsyncSession,
    classes_of: Mapping[UUID, Set[DataClass]],
    today: date,
) -> list[MyAssignment]:
    """Every assignment that is running or still has to become work, and what
    has ended only while it still asks something. What asks something first."""
    if not classes_of:
        return []
    found = []
    for read in await facts_of_many(db, classes_of, today):
        assignment = read.assignment
        notice = notice_of(read.facts, classes_of[assignment.id])
        if phase_of(assignment.status) is Phase.CLOSED and notice is None:
            continue
        found.append(
            MyAssignment(
                assignment_id=assignment.id,
                name=assignment.name,
                status=assignment.status,
                notice=notice,
                verdict=_verdict(read.finance, assignment.status)
                if read.finance
                else None,
                as_client=read.facts.is_client,
            )
        )
    found.sort(key=lambda item: item.rank)
    return found


async def stands_of(
    db: AsyncSession,
    assignments: Sequence[MyAssignment],
    *,
    today: date,
    instance_base_uri: str,
) -> dict[UUID, str]:
    """Where each stands, in the words of its course on the opened assignment.

    The current step follows from the facts of the case alone, so no task is
    read. Those facts are the ones the task engine keeps per assignment: a
    visit reads them again only for a case something happened on. The stand
    is the same for every reader."""
    labels = {item.assignment_id: STATUS_LABELS[item.status] for item in assignments}
    if not labels:
        return {}
    cases = await engine.assignment_facts(
        db, set(labels), today=today, instance_base_uri=instance_base_uri
    )
    current = await course.current_labels_of_cases(db, "assignment", cases)
    return {
        assignment_id: current.get(assignment_id) or status_label
        for assignment_id, status_label in labels.items()
    }


def line_of(stand: str, notice: str | None) -> str:
    return f"{stand}, {_lower_first(notice)}" if notice else stand


# -- planning and my people ---------------------------------------------------


def _board_span(today: date) -> tuple[Month, ...]:
    return staffing_board.window(
        staffing_board.default_start(today), staffing_board.DEFAULT_MONTHS
    )


@dataclass(frozen=True)
class PersonAhead:
    person_id: UUID
    now_pct: Decimal | None
    idle_from: date | None


async def people_ahead(db: AsyncSession, today: date) -> dict[UUID, PersonAhead]:
    """Per deployable person the inzet now and when it stops, as on the board."""

    async def compute() -> dict[UUID, PersonAhead]:
        ahead = {}
        for row in await steering.occupancy(db, _board_span(today)):
            now, _room, idle = staffing_board.summary(
                staffing_board.cells_of(row), Month.of(today).first_day
            )
            ahead[row.person_id] = PersonAhead(row.person_id, now, idle)
        return ahead

    return await read_cache.remember_all(db, "start_people_ahead", today, compute)


@dataclass(frozen=True)
class Planning:
    open_roles: int
    open_fte: Decimal
    idle_people: int
    idle_from: date | None

    @property
    def is_empty(self) -> bool:
        return not self.open_roles and not self.idle_people


def idle_count(ahead: Iterable[PersonAhead], today: date) -> tuple[int, date | None]:
    """Who has no inzet from the first month someone falls idle in the coming
    months. Whoever has none now is in it: the board shows them empty too."""
    current = Month.of(today).first_day
    days = [person.idle_from for person in ahead if person.idle_from]
    coming = [day for day in days if day > current and _soon(Month.of(day), today)]
    if coming:
        first = min(coming)
    elif current in days:
        first = current
    else:
        return 0, None
    return sum(1 for day in days if day <= first), first


async def planning(
    db: AsyncSession,
    ahead: Iterable[PersonAhead],
    today: date,
) -> Planning:
    """The open roles that are on the board, and who falls idle."""
    span = _board_span(today)
    roles = [
        role
        for role in await _open_roles(db, today)
        if staffing_board.role_in_span(role, span)
    ]
    people, month = idle_count(ahead, today)
    return Planning(
        open_roles=len(roles),
        open_fte=sum((role.unfilled_fte for role in roles), Decimal(0)),
        idle_people=people,
        idle_from=month,
    )


async def people_of(db: AsyncSession, leader_id: UUID) -> list[tuple[UUID, str]]:
    """Who has this person as line manager and still works here."""
    rows = await db.execute(
        select(Person.id, Person.name)
        .where(Person.manager_id == leader_id, Person.is_active.is_(True))
        .order_by(func.lower(Person.name), Person.id)
    )
    return [(row.id, row.name) for row in rows]


def people_in_order(
    people: Iterable[tuple[UUID, str, PersonAhead | None]],
) -> list[tuple[UUID, str, PersonAhead | None]]:
    """Over 100 percent first, then who falls idle first, then by name."""

    def key(item: tuple[UUID, str, PersonAhead | None]) -> tuple[bool, date, str]:
        _, name, person = item
        over = bool(person and person.now_pct and person.now_pct > 100)
        idle = (person.idle_from if person else None) or date.max
        return not over, idle, name.lower()

    return sorted(people, key=key)


# -- figures ------------------------------------------------------------------


@dataclass(frozen=True)
class Figures:
    year: int
    expected_cents: int
    budgeted_cents: int
    money: investment.MoneyReading
    potential_cents: int
    quotes_waiting: int
    # The executors whose cost items could not be counted in the agreed figures.
    incomplete_by: tuple[str, ...] = ()


async def figures(db: AsyncSession, year: int, today: date) -> Figures:
    """Of the whole organisation, from the read models of Geld."""

    async def compute() -> Figures:
        agreed, incomplete = await steering.agreed_figures(db, year)
        waiting = [
            quote
            for quote in await steering.quotes_of_year(db, year)
            if quote.status == "issued"
        ]
        return Figures(
            year=year,
            expected_cents=agreed.expected_total_cents,
            budgeted_cents=agreed.budgeted_cents,
            money=await investment.money_reading(db, year),
            potential_cents=sum(quote.total_cents for quote in waiting),
            quotes_waiting=len(waiting),
            incomplete_by=incomplete,
        )

    return await read_cache.remember_all(db, "start_figures", (year, today), compute)


# -- my requests --------------------------------------------------------------


@dataclass(frozen=True)
class MyRequest:
    assignment_id: UUID
    name: str
    line: str


async def client_rows(db: AsyncSession) -> list[client_side.ClientAssignment]:
    return await client_side.client_assignments(db)


def requests_in_order(
    rows: Iterable[client_side.ClientAssignment],
) -> list[client_side.ClientAssignment]:
    """What did not arrive first, then a quote that waits for an answer, then
    newest first as the rows came."""

    def key(row: client_side.ClientAssignment) -> int:
        delivery = row.request_delivery
        if delivery is not None and delivery.status in _DELIVERY_PROBLEMS:
            return 0
        waiting = row.latest_quote is not None and row.latest_quote.status == "issued"
        return 1 if waiting else 2

    return sorted(rows, key=key)


async def my_requests(
    db: AsyncSession,
    rows: Sequence[client_side.ClientAssignment],
    classes_of: Mapping[UUID, Set[DataClass]],
    today: date,
) -> list[MyRequest]:
    """Where each request stands: a message that did not arrive, else the quote,
    in the words of its row on the opened assignment."""

    async def quote_lines() -> dict[UUID, str | None]:
        lines = {}
        for row in rows:
            assignment = row.assignment
            classes = classes_of[assignment.id]
            facts = PartsFacts(
                kind=assignment.kind,
                status=assignment.status,
                is_client=True,
                quote=await quote_facts(db, assignment, is_client=True)
                if B in classes
                else None,
            )
            lines[assignment.id] = next(
                (
                    part.notice
                    for part in parts_of(facts, classes)
                    if part.key == "quote"
                ),
                None,
            )
        return lines

    # Reading a quote and its decision is six statements per row. Whether a
    # message arrived has no event, so that stays outside what is remembered.
    key = frozenset(
        (row.assignment.id, B in classes_of[row.assignment.id]) for row in rows
    )
    quotes = await read_cache.remember_all(
        db, "start_requests", (key, today), quote_lines
    )
    requests = []
    for row in rows:
        assignment = row.assignment
        delivery = row.request_delivery.status if row.request_delivery else ""
        line = (
            _DELIVERY_PROBLEMS.get(delivery)
            or quotes[assignment.id]
            or STATUS_LABELS[assignment.status]
        )
        requests.append(MyRequest(assignment.id, assignment.name, line))
    return requests


# -- connections --------------------------------------------------------------


async def dead_messages(db: AsyncSession) -> int:
    """Messages to other instances that are no longer retried."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(FederationOutbox)
            .where(FederationOutbox.status == OUTBOX_DEAD)
        )
        or 0
    )
