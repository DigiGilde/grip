"""The parts of one vacancy and where each one stands, for one reader.

A part stands where the tasks of the vacancy stand: it is at the move when an
open task that leads to it is the reader's, it waits when such a task is
someone else's, and otherwise it is behind us or ahead by the steps of the
course. Two parts can be at the move at once. Nothing here is stored.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Set
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.models.task import Task
from grip.models.vacancy import TextKind, Vacancy, VacancyStep, VacancyText
from grip.services.vacancies import service as vacancy_service
from grip.services.vacancies import text_flow
from grip.tasks import course, telling
from grip.tasks import service as task_service
from grip.tasks.access import TaskAccess
from grip.tasks.cases import CaseSnapshot

DONE = "done"
CURRENT = "current"
WAITING = "waiting"
FUTURE = "future"

_LABELS = {
    "request": "Aanvraag",
    "decisions": "Advies en akkoord",
    "text": "Tekst en openstellen",
    "fulfilment": "Vervullen",
    "details": "Gegevens",
    "history": "Geschiedenis",
}
# A ready candidate is not opened: what is left under the text is the text.
_TEXT_WITHOUT_OPENING = "Tekst"

# The step of the course each part stands for.
_STEPS = {
    "request": "aanvraag",
    "decisions": "advies",
    "text": "openstellen",
    "fulfilment": "vervullen",
}

_ROW_OF_DESTINATION = {
    "vacancy.request": "request",
    "vacancy.text": "text",
    "vacancy.text.write": "text",
    "vacancy.procedure": "text",
    "vacancy.fulfilment": "fulfilment",
}

_OPEN = ("todo", "doing", "waiting")
_COURSE_PARTS = ("request", "decisions", "text", "fulfilment")


@dataclass(frozen=True)
class Part:
    key: str
    label: str
    notice: str | None
    state: str | None


@dataclass(frozen=True)
class VacancyParts:
    parts: list[Part]
    tasks_link: bool


def row_of(task: Task) -> str | None:
    """The part of the vacancy a task leads to, by the destination of its guidance."""
    destination = telling.destination_of(task)
    if destination is None:
        return None
    if destination.startswith("vacancy.decision"):
        return "decisions"
    return _ROW_OF_DESTINATION.get(destination)


def _is_shown(
    key: str, steps: Collection[str], at_row: Collection[str], can_edit: bool
) -> bool:
    return (_STEPS[key] in steps or key in at_row) and (key != "fulfilment" or can_edit)


def has_text_matter(
    vacancy: Vacancy,
    *,
    has_texts: bool,
    has_vacancy_text: bool,
    has_steps: bool,
    can_edit: bool,
) -> bool:
    """Whether the text part holds anything for this reader: a text with
    versions, a procedure, or the choice to write a vacancy text. The one rule
    of ``parts_of`` and ``part_keys_of``."""
    may_want_text = (
        can_edit
        and not text_flow.is_needed(vacancy, TextKind.vacancy_text.value)
        and not has_vacancy_text
    )
    return has_texts or has_steps or may_want_text


def _headline(view: task_service.TaskView) -> str:
    return view.telling.headline if view.telling else view.task.title


def _at_the_move(views: list[task_service.TaskView]) -> str:
    first = _headline(views[0])
    more = len(views) - 1
    return f"{first}, en {more} andere" if more else first


def _waited_on(views: list[task_service.TaskView]) -> str:
    names: list[str] = []
    for view in views:
        told = view.telling
        who = told.waits_on if told and told.waits_on else view.assignee_label
        if who not in names:
            names.append(who)
    joined = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} en {names[-1]}"
    return f"Wacht op {joined}"


async def _open_tasks(db: AsyncSession, vacancy_id: UUID) -> list[Task]:
    rows = await db.scalars(
        select(Task)
        .where(
            Task.case_kind == "vacancy",
            Task.vacancy_id == vacancy_id,
            Task.status.in_(_OPEN),
        )
        .options(selectinload(Task.notes))
    )
    return list(rows)


async def parts_of(
    db: AsyncSession,
    access: TaskAccess,
    vacancy: Vacancy,
    snapshots: list[CaseSnapshot],
    *,
    can_edit: bool,
    sees_staffing: bool,
    today: date,
    instance_base_uri: str,
) -> VacancyParts:
    """The parts of a vacancy for a reader who gets more than its published text.

    ``can_edit`` is the right to change the vacancy; ``sees_staffing`` the
    right to read the names on it.
    """
    rights = await access.vacancy(vacancy.id)
    views = await task_service.views_for(
        db, access, await _open_tasks(db, vacancy.id), today=today
    )
    at_row: dict[str, list[task_service.TaskView]] = {}
    for view in views:
        row = row_of(view.task)
        if row is not None:
            at_row.setdefault(row, []).append(view)

    courses = await course.of_case(
        db,
        access,
        "vacancy",
        vacancy.id,
        today=today,
        instance_base_uri=instance_base_uri,
        snapshots=snapshots,
    )
    own = next((view for view in courses if view.subject == "case"), None)
    steps = {step.key: step.state for step in own.steps} if own else {}
    ended = own.ended if own else None
    current_step = own.current_key if own else None

    def part(key: str) -> Part:
        label = _LABELS[key]
        step = _STEPS.get(key)
        mine = [view for view in at_row.get(key, []) if view.needs_me]
        others = [view for view in at_row.get(key, []) if not view.needs_me]
        if key == "text" and "openstellen" not in steps:
            label = _TEXT_WITHOUT_OPENING
        if mine:
            return Part(key, label, _at_the_move(mine), CURRENT)
        if others:
            return Part(key, label, _waited_on(others), WAITING)
        state = steps.get(step) if step else None
        if state == course.DONE:
            return Part(key, label, None, DONE)
        if ended and state is not None:
            return Part(key, label, ended if step == current_step else None, None)
        if state == course.CURRENT:
            return Part(key, label, None, CURRENT)
        return Part(key, label, None, FUTURE if state else None)

    # A part of the course that does not apply is not there, unless a task
    # still leads to it or the reader has something under it: a ready
    # candidate has no opening, but a motivation, a procedure or the choice
    # to write a vacancy text anyway is still there.
    keys = {
        key for key in _COURSE_PARTS if _is_shown(key, steps, at_row.keys(), can_edit)
    }
    if has_text_matter(
        vacancy,
        has_texts=bool(vacancy.texts),
        has_vacancy_text=any(
            text.kind == TextKind.vacancy_text.value for text in vacancy.texts
        ),
        has_steps=bool(vacancy.steps),
        can_edit=can_edit,
    ):
        keys.add("text")
    shown = [key for key in _COURSE_PARTS if key in keys]
    candidate = (
        await vacancy_service.candidate_of(db, vacancy) if sees_staffing else None
    )
    if can_edit or candidate or vacancy.contract_type:
        shown.append("details")
    shown.append("history")

    return VacancyParts(
        parts=[part(key) for key in shown],
        tasks_link=rights.edit,
    )


async def part_keys_of(
    db: AsyncSession,
    access: TaskAccess,
    snapshots: list[CaseSnapshot],
    can_edit: Mapping[UUID, bool],
) -> dict[UUID, Set[str]]:
    """Which parts of the course each vacancy in ``can_edit`` has for this
    reader, without what each one says. The same decision as ``parts_of``,
    in a fixed number of statements however many vacancies there are."""
    ids = set(can_edit)
    if not ids:
        return {}
    await access.prime_vacancies(ids)
    readable = {
        vacancy_id for vacancy_id in ids if (await access.vacancy(vacancy_id)).read
    }
    at_row: dict[UUID, set[str]] = {vacancy_id: set() for vacancy_id in ids}
    if readable:
        tasks = await db.scalars(
            select(Task).where(
                Task.case_kind == "vacancy",
                Task.vacancy_id.in_(readable),
                Task.status.in_(_OPEN),
            )
        )
        for task in tasks:
            row = row_of(task)
            if row is not None and task.vacancy_id is not None:
                at_row[task.vacancy_id].add(row)
    steps = await course.step_keys_of_cases(
        db, "vacancy", [s for s in snapshots if s.case_id in ids]
    )
    kept = {
        vacancy_id: {
            key
            for key in _COURSE_PARTS
            if _is_shown(
                key,
                steps.get(vacancy_id, set()),
                at_row[vacancy_id],
                can_edit[vacancy_id],
            )
        }
        if vacancy_id in readable
        else set()
        for vacancy_id in ids
    }
    for vacancy, has_texts, has_vacancy_text, has_steps in await db.execute(
        select(
            Vacancy,
            exists().where(VacancyText.vacancy_id == Vacancy.id),
            exists().where(
                VacancyText.vacancy_id == Vacancy.id,
                VacancyText.kind == TextKind.vacancy_text.value,
            ),
            exists().where(VacancyStep.vacancy_id == Vacancy.id),
        ).where(Vacancy.id.in_(ids))
    ):
        if vacancy.id in readable and has_text_matter(
            vacancy,
            has_texts=has_texts,
            has_vacancy_text=has_vacancy_text,
            has_steps=has_steps,
            can_edit=can_edit[vacancy.id],
        ):
            kept[vacancy.id].add("text")
    return kept
