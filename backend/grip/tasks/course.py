"""Where a case stands and what is next, for one reader.

The course of a case is a few steps from the plan, each behind us once its
facts hold. The same facts open and close the tasks, so the steps, the
sentence about what is next and the task list are three views of one thing
and cannot disagree. Nothing here is stored.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.models.task import Task, TaskCase
from grip.tasks import service
from grip.tasks.access import TaskAccess
from grip.tasks.cases import (
    CaseSnapshot,
    Subject,
    load_assignment_cases,
    load_vacancy_cases,
)
from grip.tasks.plan import Course, CourseStep, Plan, current_plan, plan_for

DONE = "done"
CURRENT = "current"
FUTURE = "future"

ACTS = "acts"
WAITS = "waits"
WATCHES = "watches"

_NOTHING_TO_DO = "Er is nu niets te doen."


@dataclass(frozen=True)
class StepView:
    key: str
    label: str
    state: str
    # What happened at this step, when that is worth saying.
    note: str | None = None


@dataclass(frozen=True)
class NextView:
    """The one thing that must happen now, as this reader must hear it."""

    # The reader must act; false when the reader waits or only looks on.
    mine: bool
    # What must happen, in a few words: the same words as the task.
    headline: str
    # The sentence addressed to this reader.
    sentence: str
    # Who is waited on, when that is not the reader.
    who: str | None = None
    since: date | None = None
    due_on: date | None = None
    overdue: bool = False
    # The one action and where it is done; absent when it is not the
    # reader's move.
    action_text: str | None = None
    action_href: str | None = None
    # What still stands in the way of the action.
    missing: tuple[str, ...] = ()
    # Nobody can do this until something outside the task changes.
    blocked: str | None = None
    task_id: UUID | None = None
    # Which kind of work this is (the key of its template in the plan), for
    # a screen that can do the step in place.
    task_key: str | None = None
    # How the reader stands to this step: "acts" (their move), "waits"
    # (someone else's move on a case the reader runs or works on) or
    # "watches" (no part in it: told where it stands, never "je wacht").
    part: str = "watches"
    # The reader runs the case and may do this step for the one whose move
    # it is. Never for a step that waits on someone outside.
    may_take_over: bool = False


@dataclass(frozen=True)
class CourseView:
    key: str
    label: str
    # "case", or the kind of subject the course is about, with its key.
    subject: str
    subject_key: str
    subject_label: str | None
    steps: tuple[StepView, ...]
    # The step the case is at; None once every step is behind us.
    current_key: str | None
    current_label: str | None
    # "2 van 4", for a list.
    position: str | None
    next: NextView | None
    # How the case ended, when it did.
    ended: str | None = None
    # Open tasks of this course for the reader, beyond the one in ``next``.
    more_to_do: int = 0
    more_waiting: int = 0


@dataclass
class _CaseWork:
    snapshot: CaseSnapshot
    plan: Plan
    views: list[service.TaskView] = field(default_factory=list)


def _value(name: str, case: CaseSnapshot, subject: Subject | None) -> bool:
    if "." in name:
        kind, fact = name.split(".", 1)
        return any(other.facts.get(fact, False) for other in case.subjects_of(kind))
    if subject is not None and name in subject.facts:
        return subject.facts[name]
    return case.facts.get(name, False)


def holds(condition: str, case: CaseSnapshot, subject: Subject | None = None) -> bool:
    """Whether one condition of a course holds for this case or subject."""
    if condition.startswith("not "):
        return not _value(condition[4:], case, subject)
    return _value(condition, case, subject)


def _all(
    conditions: Iterable[str], case: CaseSnapshot, subject: Subject | None
) -> bool:
    return all(holds(condition, case, subject) for condition in conditions)


def steps_of(
    course: Course, case: CaseSnapshot, subject: Subject | None = None
) -> list[tuple[CourseStep, str]]:
    """The steps that apply to this case, each with its state.

    A step whose facts hold is behind us wherever it stands: work may be
    done out of order. The first one that is not, is where the case is.
    """
    applicable = [step for step in course.steps if _all(step.when, case, subject)]
    result: list[tuple[CourseStep, str]] = []
    current_seen = False
    for step in applicable:
        if _all(step.done_when, case, subject):
            result.append((step, DONE))
        elif not current_seen:
            result.append((step, CURRENT))
            current_seen = True
        else:
            result.append((step, FUTURE))
    return result


def _note(step: CourseStep, case: CaseSnapshot, subject: Subject | None) -> str | None:
    for note in step.notes:
        if holds(note.when, case, subject):
            return note.text
    return None


def _belongs(view: service.TaskView, course: Course, subject: Subject | None) -> bool:
    task = view.task
    keys = {key for step in course.steps for key in step.tasks}
    if task.template_key not in keys:
        return False
    if subject is None or course.subject == "case":
        return True
    own = subject.repeat_key
    if task.repeat_key == own or task.repeat_key.startswith(f"{own}:"):
        return True
    # A period is made of months: closing one of them is work of the period.
    parts = (subject.subject_id or "").split(",")
    return course.subject == "billing_period" and task.repeat_key in parts


def _next(
    course: Course,
    states: list[tuple[CourseStep, str]],
    views: list[service.TaskView],
) -> tuple[NextView | None, int, int]:
    """The task to tell about, and how many more wait behind it."""
    order = {key: index for index, (step, _) in enumerate(states) for key in step.tasks}
    current = next((step for step, state in states if state == CURRENT), None)
    in_current = set(current.tasks) if current else set()

    def rank(view: service.TaskView) -> tuple[int, int, int, str]:
        task = view.task
        return (
            0 if view.needs_me else 1,
            0 if task.template_key in in_current else 1,
            order.get(task.template_key or "", len(order)),
            task.due_on.isoformat() if task.due_on else "9999",
        )

    ranked = sorted(views, key=rank)
    if not ranked:
        if current is None:
            return None, 0, 0
        sentence = current.idle or _NOTHING_TO_DO
        return NextView(mine=False, headline=current.label, sentence=sentence), 0, 0
    first = ranked[0]
    told = first.telling
    task = first.task
    rest = ranked[1:]
    more_to_do = sum(1 for view in rest if view.needs_me)
    more_waiting = len(rest) - more_to_do
    if told is None:
        return (
            NextView(
                mine=first.is_mine,
                part=ACTS if first.is_mine else WAITS if first.can_change else WATCHES,
                headline=task.title,
                sentence=task.title,
                who=None if first.is_mine else first.assignee_label,
                since=task.created_at.date() if task.created_at else None,
                due_on=task.due_on,
                overdue=first.overdue,
                action_href=task.link if first.is_mine else None,
                task_id=task.id,
                task_key=task.template_key,
            ),
            more_to_do,
            more_waiting,
        )
    mine = told.needs_me
    # Whoever may change the task runs the case or is the one it is for:
    # that reader waits for the step. Anyone else only looks on.
    part = ACTS if mine else WAITS if first.can_change or first.is_mine else WATCHES
    who = None if mine else (told.waits_on or first.assignee_label)
    sentence = told.instruction
    if part == WATCHES:
        # No "je wacht" and no deadline for someone who has no part in it.
        awaited = told.headline[:1].lower() + told.headline[1:]
        sentence = (
            f"{who[:1].upper()}{who[1:]} is aan zet: {awaited}."
            if who
            else told.headline
        )
    return (
        NextView(
            mine=mine,
            part=part,
            headline=told.headline,
            sentence=sentence,
            who=who,
            since=task.created_at.date() if task.created_at else None,
            due_on=task.due_on if part != WATCHES else None,
            overdue=first.overdue and part != WATCHES,
            action_text=told.action_text if mine else None,
            action_href=told.work_href if mine else None,
            missing=tuple(item.text for item in told.checklist if not item.done)
            if part != WATCHES
            else (),
            blocked=told.blocked if part != WATCHES else None,
            task_id=task.id,
            task_key=task.template_key,
            may_take_over=not mine
            and first.can_change
            and task.status != "waiting"
            and not task.waiting_on,
        ),
        more_to_do,
        more_waiting,
    )


def _subject_label(subject: Subject) -> str | None:
    for value in subject.variables.values():
        if value:
            return value
    return subject.repeat_key or None


def _view(
    course: Course,
    case: CaseSnapshot,
    subject: Subject | None,
    views: list[service.TaskView],
    ended: str | None,
) -> CourseView:
    states = steps_of(course, case, subject)
    steps = tuple(
        StepView(
            key=step.key,
            label=step.label,
            state=state,
            note=_note(step, case, subject) if state != FUTURE else None,
        )
        for step, state in states
    )
    current = next((step for step, state in states if state == CURRENT), None)
    own = [view for view in views if _belongs(view, course, subject)]
    told, more_to_do, more_waiting = (
        (None, 0, 0) if ended else _next(course, states, own)
    )
    position = None
    if current is not None:
        index = [step.key for step, _ in states].index(current.key) + 1
        position = f"{index} van {len(states)}"
    return CourseView(
        key=course.key,
        label=course.label,
        subject=course.subject,
        subject_key=subject.repeat_key if subject and course.subject != "case" else "",
        subject_label=_subject_label(subject)
        if subject and course.subject != "case"
        else None,
        steps=steps,
        current_key=current.key if current else None,
        current_label=current.label if current else None,
        position=position,
        next=told,
        ended=ended,
        more_to_do=more_to_do,
        more_waiting=more_waiting,
    )


def _plan_with_courses(plan: Plan, case_kind: str) -> Plan:
    """A plan from before courses existed takes them from the current one."""
    return plan if plan.courses.get(case_kind) else current_plan()


def views_of(work: _CaseWork) -> list[CourseView]:
    """The course of the case itself first, then of each of its subjects."""
    case = work.snapshot
    plan = _plan_with_courses(work.plan, case.case_kind)
    ended = next(
        (
            end.label
            for end in plan.ends.get(case.case_kind, ())
            if holds(end.when, case)
        ),
        None,
    )
    result: list[CourseView] = []
    case_course_taken = False
    for course in plan.courses.get(case.case_kind, ()):
        if course.subject == "case":
            if case_course_taken or not _all(course.when, case, None):
                continue
            case_course_taken = True
            result.insert(0, _view(course, case, None, work.views, ended))
            continue
        if not _all(course.when, case, None):
            continue
        for subject in case.subjects_of(course.subject):
            result.append(_view(course, case, subject, work.views, ended))
    if ended and not case_course_taken:
        # A case that ended outside every course still says how it ended.
        result.insert(
            0,
            CourseView(
                key="",
                label="",
                subject="case",
                subject_key="",
                subject_label=None,
                steps=(),
                current_key=None,
                current_label=None,
                position=None,
                next=None,
                ended=ended,
            ),
        )
    return result


async def _snapshots(
    db: AsyncSession,
    case_kind: str,
    case_ids: set[UUID],
    *,
    today: date,
    instance_base_uri: str,
) -> list[CaseSnapshot]:
    if case_kind == "assignment":
        return await load_assignment_cases(
            db, case_ids, today=today, instance_base_uri=instance_base_uri
        )
    return await load_vacancy_cases(db, case_ids)


async def of_cases(
    db: AsyncSession,
    access: TaskAccess,
    case_kind: str,
    case_ids: set[UUID],
    *,
    today: date,
    instance_base_uri: str,
    snapshots: list[CaseSnapshot] | None = None,
) -> dict[UUID, list[CourseView]]:
    """The courses of several cases, for a list. The caller checked that the
    reader may read each case and brought the tasks up to date; it hands
    over the facts that run read, when it has them."""
    if not case_ids:
        return {}
    if snapshots is None:
        snapshots = await _snapshots(
            db, case_kind, case_ids, today=today, instance_base_uri=instance_base_uri
        )
    versions = dict(
        (
            await db.execute(
                select(TaskCase.case_id, TaskCase.plan_version).where(
                    TaskCase.case_kind == case_kind, TaskCase.case_id.in_(case_ids)
                )
            )
        ).all()
    )
    column = Task.assignment_id if case_kind == "assignment" else Task.vacancy_id
    tasks = (
        await db.scalars(
            select(Task)
            .where(
                Task.case_kind == case_kind,
                column.in_(case_ids),
                Task.status.in_(("todo", "doing", "waiting")),
            )
            .options(selectinload(Task.notes))
        )
    ).all()
    views = await service.views_for(db, access, list(tasks), today=today)
    by_case: dict[UUID, list[service.TaskView]] = {}
    for view in views:
        case_id = (
            view.task.assignment_id
            if case_kind == "assignment"
            else view.task.vacancy_id
        )
        if case_id is not None:
            by_case.setdefault(case_id, []).append(view)
    return {
        snapshot.case_id: views_of(
            _CaseWork(
                snapshot=snapshot,
                plan=plan_for(versions.get(snapshot.case_id)),
                views=by_case.get(snapshot.case_id, []),
            )
        )
        for snapshot in snapshots
    }


async def of_case(
    db: AsyncSession,
    access: TaskAccess,
    case_kind: str,
    case_id: UUID,
    *,
    today: date,
    instance_base_uri: str,
    snapshots: list[CaseSnapshot] | None = None,
) -> list[CourseView]:
    found = await of_cases(
        db,
        access,
        case_kind,
        {case_id},
        today=today,
        instance_base_uri=instance_base_uri,
        snapshots=snapshots,
    )
    return found.get(case_id, [])
