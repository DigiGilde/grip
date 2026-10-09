"""The task engine: bring the tasks of a case in line with its facts.

Events in, tasks out, facts close tasks. The engine does not remember what
happened; it compares what the plan asks for, given the facts of a case
today, with the tasks that exist, and changes only the difference:

- a task is created when everything under ``when`` holds and its closing
  fact does not;
- an open task is closed when its closing fact holds;
- an open task is marked obsolete when its reason is gone;
- a task that a fact closed is opened again when the fact no longer holds
  (a reopened month).

Running it twice changes nothing the second time, so the same event twice
never makes a second task. The engine never writes to a domain table.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.task import OPEN_STATUSES, Task, TaskCase, TaskEngineRun
from grip.services.vacancies.procedure import is_working_day
from grip.tasks import catalogue
from grip.tasks.cases import (
    CaseSnapshot,
    Subject,
    live_assignment_ids,
    live_vacancy_ids,
    load_assignment_cases,
    load_vacancy_cases,
)
from grip.tasks.plan import Plan, Template, current_plan, plan_for

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


logger = logging.getLogger(__name__)


@dataclass
class Outcome:
    """What one run changed."""

    created: int = 0
    closed: int = 0
    obsolete: int = 0
    reopened: int = 0
    cases: int = 0
    # The facts this run read, for a caller that tells about the same cases
    # right after: reading them twice costs a priced budget per open quote.
    snapshots: list[CaseSnapshot] = field(default_factory=list)
    # Cases whose facts could not be read: their tasks stay as they were.
    failed: list[tuple[str, UUID]] = field(default_factory=list)

    def add(self, other: Outcome) -> None:
        self.created += other.created
        self.closed += other.closed
        self.obsolete += other.obsolete
        self.reopened += other.reopened
        self.cases += other.cases
        self.failed += other.failed

    @property
    def changes(self) -> int:
        return self.created + self.closed + self.obsolete + self.reopened


def add_working_days(start: date, days: int) -> date:
    day = start
    remaining = days
    while remaining > 0:
        day += timedelta(days=1)
        if is_working_day(day):
            remaining -= 1
    return day


def _holds(condition: str, facts: dict[str, bool]) -> bool:
    if condition.startswith("not "):
        return not facts.get(condition[4:], False)
    return facts.get(condition, False)


def _dedupe_key(template: Template, case: CaseSnapshot, subject: Subject) -> str:
    return f"{template.key}|{case.case_kind}:{case.case_id}|{subject.repeat_key}"


def _format(text: str, case: CaseSnapshot, subject: Subject) -> str:
    values = {
        "assignment_id": str(case.assignment_id or ""),
        "vacancy_id": str(case.vacancy_id or ""),
        "subject_id": subject.subject_id or "",
        "repeat_key": subject.repeat_key,
        **subject.variables,
    }
    try:
        return text.format(**values)
    except (KeyError, IndexError):
        return text


@dataclass
class _Wanted:
    """A task the plan asks for, given the facts."""

    template: Template
    subject: Subject
    title: str
    link: str | None
    due_on: date | None
    assignee_person_id: UUID | None
    assignee_role: str | None
    waiting_on: str | None
    waiting: bool
    situation: str | None = None


def _assignee(
    template: Template, case: CaseSnapshot, subject: Subject
) -> tuple[UUID | None, str | None, str | None, bool]:
    """Person, role, who is waited on, and whether the task starts waiting."""
    role = template.assignee
    if role in catalogue.SUBJECT_PERSON_ROLES:
        if subject.person_id is not None:
            return subject.person_id, None, None, False
        if case.case_kind == "vacancy":
            # Nobody wrote yet: the requester starts, or else a planner.
            requester = case.people.get("requester")
            if requester is not None:
                return requester, None, None, False
            return None, "planner", None, False
        return None, "owner", None, False
    if role in catalogue.VACANCY_PERSON_ROLES:
        person_id = case.people.get(role)
        if person_id is not None:
            return person_id, None, None, False
        # Nobody with an account is named: the requester keeps an eye on it.
        requester = case.people.get("requester")
        waits = role != "requester"
        waiting_on = template.waiting_on if waits else None
        if requester is not None:
            return requester, None, waiting_on, waits
        return None, "planner", waiting_on, waits
    if template.waiting_on:
        return None, role, template.waiting_on, True
    return None, role, None, False


def _situation(template: Template, facts: dict[str, bool]) -> str | None:
    """The first fact that holds among those the guidance has other words for."""
    from grip.tasks import telling

    guide = telling.guidance().templates.get(template.key)
    if guide is None:
        return None
    return next((name for name in guide.situations if facts.get(name, False)), None)


def _due(template: Template, subject: Subject, existing: Task | None) -> date | None:
    if template.due is None:
        return None
    anchor = subject.anchors.get(template.due.after)
    if anchor is None:
        return existing.due_on if existing else None
    return add_working_days(anchor, template.due.working_days)


def _apply(task: Task, wanted: _Wanted) -> None:
    """Keep what the plan decides in step; leave what a person changed."""
    task.title = wanted.title
    task.link = wanted.link
    task.due_on = wanted.due_on
    task.situation = wanted.situation
    if task.assigned_by_id is not None:
        return
    # Waiting set by the plan follows the plan: once the person waited for
    # is named, the task is theirs to do.
    if wanted.waiting and task.status == "todo" and task.waiting_on is None:
        task.status = "waiting"
    elif (
        not wanted.waiting and task.status == "waiting" and task.waiting_on is not None
    ):
        task.status = "todo"
    task.assignee_person_id = wanted.assignee_person_id
    task.assignee_role = wanted.assignee_role
    task.waiting_on = wanted.waiting_on


async def _reconcile_case(
    db: AsyncSession,
    case: CaseSnapshot,
    plan: Plan,
    existing: list[Task],
    *,
    now: datetime,
) -> Outcome:
    outcome = Outcome(cases=1)
    by_key = {task.dedupe_key: task for task in existing if task.dedupe_key}
    seen: set[str] = set()

    for template in plan.templates.get(case.case_kind, ()):
        first_open_taken = False
        for subject in case.subjects_of(template.subject):
            facts = {**case.facts, **subject.facts}
            key = _dedupe_key(template, case, subject)
            seen.add(key)
            task = by_key.get(key)
            done = template.done_when is not None and facts.get(
                template.done_when, False
            )
            applicable = all(_holds(condition, facts) for condition in template.when)

            if done:
                if task is not None and task.is_open:
                    task.status = "done"
                    task.completed_at = now
                    task.completed_by_fact = template.done_when
                    outcome.closed += 1
                continue
            if not applicable:
                if task is not None and task.is_open:
                    task.status = "obsolete"
                    task.completed_at = now
                    outcome.obsolete += 1
                continue

            if template.only_first:
                if first_open_taken and (task is None or not task.is_open):
                    continue
                first_open_taken = True

            person_id, role, waiting_on, waiting = _assignee(template, case, subject)
            wanted = _Wanted(
                template=template,
                subject=subject,
                title=_format(template.title, case, subject),
                link=_format(template.link, case, subject) if template.link else None,
                due_on=_due(template, subject, task),
                assignee_person_id=person_id,
                assignee_role=role,
                waiting_on=waiting_on,
                waiting=waiting,
                situation=_situation(template, facts),
            )
            if task is None:
                await _create(db, case, plan, wanted, key)
                outcome.created += 1
            elif task.is_open:
                _apply(task, wanted)
            elif task.status == "obsolete" or task.completed_by_fact is not None:
                # The reason came back, or the fact no longer holds.
                _apply(task, wanted)
                task.status = "waiting" if wanted.waiting else "todo"
                task.completed_at = None
                task.completed_by_fact = None
                task.completed_by_id = None
                outcome.reopened += 1
            # A task a person ticked stays ticked.

    # A task whose subject is gone (a deleted budget line, a round that
    # ended in a rejection) has lost its reason.
    for task in existing:
        if (
            task.origin == "plan"
            and task.is_open
            and task.dedupe_key
            and task.dedupe_key not in seen
        ):
            task.status = "obsolete"
            task.completed_at = now
            outcome.obsolete += 1
    return outcome


async def _create(
    db: AsyncSession, case: CaseSnapshot, plan: Plan, wanted: _Wanted, key: str
) -> None:
    template = wanted.template
    await db.execute(
        pg_insert(Task)
        .values(
            case_kind=case.case_kind,
            assignment_id=case.assignment_id,
            vacancy_id=case.vacancy_id,
            origin="plan",
            template_key=template.key,
            plan_version=plan.version,
            repeat_key=wanted.subject.repeat_key,
            dedupe_key=key,
            title=wanted.title,
            track=template.track,
            subject_kind=wanted.subject.kind,
            subject_id=wanted.subject.subject_id,
            link=wanted.link,
            assignee_person_id=wanted.assignee_person_id,
            assignee_role=wanted.assignee_role,
            waiting_on=wanted.waiting_on,
            due_on=wanted.due_on,
            status="waiting" if wanted.waiting else "todo",
            closing_fact=template.done_when,
            situation=wanted.situation,
        )
        .on_conflict_do_nothing()
    )


async def _case_plans(
    db: AsyncSession, cases: list[CaseSnapshot], *, now: datetime
) -> dict[UUID, Plan]:
    """The plan of each case; a case seen for the first time gets the current."""
    if not cases:
        return {}
    ids = [case.case_id for case in cases]
    rows = (await db.scalars(select(TaskCase).where(TaskCase.case_id.in_(ids)))).all()
    known = {(row.case_kind, row.case_id): row for row in rows}
    plans: dict[UUID, Plan] = {}
    for case in cases:
        row = known.get((case.case_kind, case.case_id))
        if row is None:
            plan = current_plan()
            await db.execute(
                pg_insert(TaskCase)
                .values(
                    case_kind=case.case_kind,
                    case_id=case.case_id,
                    plan_version=plan.version,
                    evaluated_at=now,
                )
                .on_conflict_do_nothing()
            )
        else:
            current = current_plan()
            if row.plan_version in current.replaces:
                # The current plan takes over the cases of this version. What
                # the old plan asked and the new one does not, lapses below;
                # what both ask keeps its task.
                row.plan_version = current.version
            plan = plan_for(row.plan_version)
            row.evaluated_at = now
        plans[case.case_id] = plan
    return plans


async def _reconcile(
    db: AsyncSession, cases: list[CaseSnapshot], *, now: datetime
) -> Outcome:
    outcome = Outcome()
    if not cases:
        return outcome
    await db.flush()
    plans = await _case_plans(db, cases, now=now)
    assignment_ids = [c.case_id for c in cases if c.case_kind == "assignment"]
    vacancy_ids = [c.case_id for c in cases if c.case_kind == "vacancy"]
    tasks: dict[tuple[str, UUID], list[Task]] = {}
    if assignment_ids:
        rows = await db.scalars(
            select(Task).where(
                Task.case_kind == "assignment",
                Task.origin == "plan",
                Task.assignment_id.in_(assignment_ids),
            )
        )
        for task in rows:
            if task.assignment_id is not None:
                tasks.setdefault(("assignment", task.assignment_id), []).append(task)
    if vacancy_ids:
        rows = await db.scalars(
            select(Task).where(
                Task.case_kind == "vacancy",
                Task.origin == "plan",
                Task.vacancy_id.in_(vacancy_ids),
            )
        )
        for task in rows:
            if task.vacancy_id is not None:
                tasks.setdefault(("vacancy", task.vacancy_id), []).append(task)
    for case in cases:
        outcome.add(
            await _reconcile_case(
                db,
                case,
                plans[case.case_id],
                tasks.get((case.case_kind, case.case_id), []),
                now=now,
            )
        )
    await db.flush()
    return outcome


async def _load_each_if_needed(
    db: AsyncSession,
    case_kind: str,
    ids: set[UUID],
    load: Callable[[set[UUID]], Awaitable[list[CaseSnapshot]]],
) -> tuple[list[CaseSnapshot], list[tuple[str, UUID]]]:
    """The facts of the cases, and the cases whose facts could not be read.

    One case with facts that fail must not take the tasks of everyone down:
    when reading them together fails, each case is read on its own, the one
    that fails is logged and left as it was, and the rest goes on. Each
    attempt runs in a savepoint, so a failed read leaves the session usable.
    """
    try:
        async with db.begin_nested():
            return await load(ids), []
    except Exception:
        logger.exception("Reading the facts of %s cases failed; one by one", case_kind)
    cases: list[CaseSnapshot] = []
    failed: list[tuple[str, UUID]] = []
    for case_id in sorted(ids, key=str):
        try:
            async with db.begin_nested():
                cases.extend(await load({case_id}))
        except Exception:
            logger.exception(
                "The facts of %s %s could not be read; its tasks stay as they were",
                case_kind,
                case_id,
            )
            failed.append((case_kind, case_id))
    return cases, failed


async def evaluate_assignments(
    db: AsyncSession,
    assignment_ids: set[UUID],
    *,
    today: date,
    instance_base_uri: str,
    now: datetime | None = None,
) -> Outcome:
    await db.flush()

    async def load(ids: set[UUID]) -> list[CaseSnapshot]:
        return await load_assignment_cases(
            db, ids, today=today, instance_base_uri=instance_base_uri
        )

    cases, failed = await _load_each_if_needed(db, "assignment", assignment_ids, load)
    outcome = await _reconcile(db, cases, now=now or datetime.now(UTC))
    outcome.snapshots = cases
    outcome.failed = failed
    return outcome


async def evaluate_vacancies(
    db: AsyncSession, vacancy_ids: set[UUID], *, now: datetime | None = None
) -> Outcome:
    await db.flush()

    async def load(ids: set[UUID]) -> list[CaseSnapshot]:
        return await load_vacancy_cases(db, ids)

    cases, failed = await _load_each_if_needed(db, "vacancy", vacancy_ids, load)
    outcome = await _reconcile(db, cases, now=now or datetime.now(UTC))
    outcome.snapshots = cases
    outcome.failed = failed
    return outcome


async def evaluate_all(
    db: AsyncSession,
    *,
    today: date,
    instance_base_uri: str,
    now: datetime | None = None,
) -> Outcome:
    """Look at every case on which work may arise. Also the backfill."""
    moment = now or datetime.now(UTC)
    outcome = await evaluate_assignments(
        db,
        await live_assignment_ids(db),
        today=today,
        instance_base_uri=instance_base_uri,
        now=moment,
    )
    outcome.add(
        await evaluate_vacancies(
            db, await live_vacancy_ids(db, today=today), now=moment
        )
    )
    await db.execute(
        pg_insert(TaskEngineRun)
        .values(id=1, last_run_at=moment)
        .on_conflict_do_update(index_elements=["id"], set_={"last_run_at": moment})
    )
    return outcome


async def ensure_fresh(
    db: AsyncSession,
    *,
    today: date,
    instance_base_uri: str,
    max_age_seconds: int = 0,
    now: datetime | None = None,
) -> Outcome | None:
    """Evaluate every case unless that happened less than a moment ago."""
    moment = now or datetime.now(UTC)
    if max_age_seconds > 0:
        last = await db.scalar(
            select(TaskEngineRun.last_run_at).where(TaskEngineRun.id == 1)
        )
        if last is not None and (moment - last).total_seconds() < max_age_seconds:
            return None
    return await evaluate_all(
        db, today=today, instance_base_uri=instance_base_uri, now=moment
    )


async def invalidate(db: AsyncSession) -> None:
    """Make the next reader evaluate again: something changed on a case."""
    await db.execute(
        pg_insert(TaskEngineRun)
        .values(id=1, last_run_at=_EPOCH)
        .on_conflict_do_update(index_elements=["id"], set_={"last_run_at": _EPOCH})
    )


def open_statuses() -> tuple[str, ...]:
    return OPEN_STATUSES
