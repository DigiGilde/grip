"""Tasks: my work, the work on a case, and the board.

Reading tasks first lets the engine bring them in line with the facts, so a
task that a fact closed is never shown as open. Every read and write goes
through the access model: a task is data class A of its case.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import DataClass, build_response
from grip.access.deps import AccessDecider, CurrentSubject
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.models.task import Task
from grip.schema.tasks import (
    CaseKind,
    CaseTasksOut,
    TaskCountsOut,
    TaskCreateIn,
    TaskListOut,
    TaskNoteIn,
    TaskNoteOut,
    TaskOut,
    TaskUpdateIn,
    TrackOut,
)
from grip.services.errors import NotFoundError
from grip.tasks import catalogue, engine, service
from grip.tasks.access import TaskAccess
from grip.tasks.handlers import register_task_handlers
from grip.tasks.service import TaskView

router = APIRouter(prefix="/tasks", tags=["tasks"])

_CLASSES = frozenset({DataClass.ASSIGNMENT_BASIC})
# The badge in the navigation is asked for on every page: it may be this
# many seconds behind. Lists always look first.
_COUNT_MAX_AGE_SECONDS = 15

# Domain events make the next reader look again at once.
register_task_handlers()


def _out(view: TaskView) -> TaskOut:
    task = view.task
    return TaskOut(
        id=task.id,
        case_kind=task.case_kind,
        assignment_id=task.assignment_id if view.assignment_name else None,
        assignment_name=view.assignment_name,
        vacancy_id=task.vacancy_id,
        vacancy_title=view.vacancy_title,
        case_label=view.case_label,
        title=task.title,
        track=task.track,
        track_label=view.track_label,
        status=task.status,
        status_label=catalogue.STATUS_LABELS[task.status],
        origin=task.origin,
        due_on=task.due_on,
        overdue=view.overdue,
        assignee_person_id=task.assignee_person_id,
        assignee_role=task.assignee_role if task.assignee_person_id is None else None,
        assignee_label=view.assignee_label,
        waiting_on=task.waiting_on,
        link=task.link,
        is_mine=view.is_mine,
        can_change=view.can_change,
        can_complete=view.can_complete,
        closes_by_fact=view.closes_by_fact,
        closing_fact_label=view.closing_fact_label,
        completed_at=task.completed_at,
        completed_by_name=view.completed_by_name,
        completed_by_fact=task.completed_by_fact is not None,
        note_count=view.note_count,
        notes=[
            TaskNoteOut(
                id=note.id,
                body=note.body,
                created_at=note.created_at,
                author_name=note.author_name,
            )
            for note in view.notes
        ],
    )


async def _look(db: AsyncSession, settings: Settings, *, max_age: int = 0) -> None:
    await engine.ensure_fresh(
        db,
        today=date.today(),
        instance_base_uri=settings.INSTANCE_BASE_URI,
        max_age_seconds=max_age,
    )


def _access(db: AsyncSession, decider: Any, subject: Any) -> TaskAccess:
    return TaskAccess(db, decider, subject)


@router.get("/mine", response_model=None)
async def list_my_tasks(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The open tasks that are mine to do, soonest first."""
    await _look(db, settings)
    access = _access(db, decider, subject)
    views = await service.my_tasks(db, access, today=date.today())
    counts = TaskCountsOut(
        open=len(views),
        to_do=sum(1 for view in views if view.task.status != "waiting"),
        overdue=sum(1 for view in views if view.overdue),
    )
    return build_response(
        TaskListOut(items=[_out(view) for view in views], counts=counts), _CLASSES
    )


@router.get("/count", response_model=None)
async def count_my_tasks(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """How many tasks wait for me: the badge in the navigation."""
    await _look(db, settings, max_age=_COUNT_MAX_AGE_SECONDS)
    access = _access(db, decider, subject)
    counts = await service.my_counts(db, access, today=date.today())
    return build_response(TaskCountsOut(**counts), _CLASSES)


@router.get("", response_model=None)
async def list_tasks(
    subject: CurrentSubject,
    decider: AccessDecider,
    assignment_id: UUID | None = None,
    vacancy_id: UUID | None = None,
    person_id: UUID | None = None,
    track: str | None = None,
    mine: bool = False,
    include_closed: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Tasks of every case I may see, for the board."""
    await _look(db, settings)
    access = _access(db, decider, subject)
    views = await service.all_tasks(
        db,
        access,
        today=date.today(),
        assignment_id=assignment_id,
        vacancy_id=vacancy_id,
        person_id=person_id,
        track=track,
        include_closed=include_closed,
        only_mine=mine,
    )
    return build_response(TaskListOut(items=[_out(view) for view in views]), _CLASSES)


@router.get("/cases/{case_kind}/{case_id}", response_model=None)
async def list_case_tasks(
    case_kind: CaseKind,
    case_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The work on one assignment or vacancy, per track."""
    access = _access(db, decider, subject)
    rights = await access.case(
        case_kind,
        case_id if case_kind == "assignment" else None,
        case_id if case_kind == "vacancy" else None,
    )
    if not rights.read:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden"
        )
    today = date.today()
    if case_kind == "assignment":
        await engine.evaluate_assignments(
            db, {case_id}, today=today, instance_base_uri=settings.INSTANCE_BASE_URI
        )
    else:
        await engine.evaluate_vacancies(db, {case_id})
    plan, tracks = await service.case_tasks(db, access, case_kind, case_id, today=today)
    return build_response(
        CaseTasksOut(
            case_kind=case_kind,
            case_id=case_id,
            plan_version=plan.version,
            can_add=rights.edit,
            tracks=[
                TrackOut(
                    key=track.key,
                    label=track.label,
                    open_count=track.open_count,
                    waiting_count=track.waiting_count,
                    standing=track.standing,
                    tasks=[_out(view) for view in track.tasks],
                )
                for track in tracks
            ],
        ),
        _CLASSES,
    )


async def _load(
    db: AsyncSession, access: TaskAccess, task_id: UUID
) -> tuple[Task, bool, bool]:
    """The task, whether the reader may edit its case, and whether it is theirs."""
    try:
        task = await service.get_task(db, task_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden"
        ) from None
    rights = await access.of_task(task)
    if not rights.read:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden"
        )
    return task, rights.edit, await access.is_for_reader(task)


async def _one(db: AsyncSession, access: TaskAccess, task: Task) -> dict[str, Any]:
    fresh = await service.get_task(db, task.id)
    view = await service.view_task(db, access, fresh, today=date.today())
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden"
        )
    return build_response(_out(view), _CLASSES)


@router.get("/{task_id}", response_model=None)
async def get_task(
    task_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    access = _access(db, decider, subject)
    task, _, _ = await _load(db, access, task_id)
    return await _one(db, access, task)


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreateIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Add a task by hand to a case I may edit."""
    access = _access(db, decider, subject)
    rights = await access.case(
        body.case_kind,
        body.case_id if body.case_kind == "assignment" else None,
        body.case_id if body.case_kind == "vacancy" else None,
    )
    if not rights.read:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden"
        )
    if not rights.edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Je kunt op deze zaak geen taak toevoegen",
        )
    task = await service.create_manual_task(
        db,
        case_kind=body.case_kind,
        case_id=body.case_id,
        title=body.title,
        track=body.track,
        actor=person,
        assignee_person_id=body.assignee_person_id,
        due_on=body.due_on,
    )
    return await _one(db, access, task)


@router.patch("/{task_id}", response_model=None)
async def update_task(
    task_id: UUID,
    body: TaskUpdateIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Move a task, hand it over, or change a manual task."""
    access = _access(db, decider, subject)
    task, may_edit, mine = await _load(db, access, task_id)
    if not (may_edit or mine):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deze taak is niet van jou en je beheert de zaak niet",
        )
    fields = body.model_fields_set
    if "assignee_person_id" in fields:
        await service.assign(db, task, body.assignee_person_id, actor=person)
    if "title" in fields or "due_on" in fields:
        if not may_edit and task.created_by_id != person.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Alleen wie de zaak beheert past een taak aan",
            )
        await service.update_details(
            db,
            task,
            title=body.title if "title" in fields else None,
            due_on=body.due_on,
            clear_due="due_on" in fields and body.due_on is None,
        )
    if body.status is not None:
        await service.set_status(db, task, body.status, actor=person)
    return await _one(db, access, task)


@router.post(
    "/{task_id}/notes", response_model=None, status_code=status.HTTP_201_CREATED
)
async def add_task_note(
    task_id: UUID,
    body: TaskNoteIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Write a note on a task of a case I may see."""
    access = _access(db, decider, subject)
    task, _, _ = await _load(db, access, task_id)
    await service.add_note(db, task, body.body, actor=person)
    return await _one(db, access, task)
