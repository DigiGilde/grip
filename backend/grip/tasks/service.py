"""Reading and changing tasks as a person.

The engine (``grip.tasks.engine``) makes and closes the tasks of the plan;
this module is what a person does with tasks: see the ones that are theirs,
see the work on a case per track, add a task by hand, hand one over, move
its status, write a note. Nothing here touches a domain table, and a task
that a fact closes cannot be ticked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.task import OPEN_STATUSES, Task, TaskCase, TaskNote
from grip.models.vacancy import Vacancy
from grip.services.errors import DomainValidationError, NotFoundError
from grip.tasks import access as task_access
from grip.tasks import catalogue, telling
from grip.tasks.access import TaskAccess
from grip.tasks.plan import Plan, current_plan, plan_for

# The tasks that ask for an advice or the approval on a vacancy.
_DECISION_TASKS = ("werving.advies_hr", "werving.advies_control", "werving.akkoord")

SEPARATED = (
    "Deze stap is van wie erover beslist. Hij kan niet worden overgenomen of "
    "aan een ander gegeven."
)

# What a person may set a status to. "obsolete" is for a manual task only.
_HUMAN_STATUSES = ("todo", "doing", "waiting", "done", "obsolete")
# How long a finished task stays in the view of its case.
RECENT_DONE = 20


@dataclass
class TaskView:
    """A task as one reader sees it."""

    task: Task
    case_label: str
    assignment_name: str | None
    vacancy_title: str | None
    track_label: str
    assignee_name: str | None
    assignee_label: str
    completed_by_name: str | None
    is_mine: bool
    can_change: bool
    # The reader runs the case with others: its owner or a manager, the
    # requester or a writer of a vacancy. Not whoever may merely change it.
    has_part: bool
    # The reader holds what the step asks for and may do it for the one at
    # move; never a step where someone else must decide.
    can_take_over: bool
    can_complete: bool
    closes_by_fact: bool
    closing_fact_label: str | None
    overdue: bool
    note_count: int = 0
    notes: list[NoteView] = field(default_factory=list)
    # What this reader must hear about the task; set by ``telling.tell``.
    telling: telling.Telling | None = None

    @property
    def needs_me(self) -> bool:
        return self.telling is not None and self.telling.needs_me


@dataclass
class NoteView:
    id: UUID
    body: str
    created_at: datetime
    author_name: str | None


@dataclass
class TrackView:
    key: str
    label: str
    open_count: int
    waiting_count: int
    # The one line a header shows: where this track stands.
    standing: str
    tasks: list[TaskView]


def _template_manual(task: Task) -> bool:
    if task.template_key is None:
        return True
    template = plan_for(task.plan_version).template(task.template_key)
    return template is None or template.closes_by_hand


def closes_by_fact_only(task: Task) -> bool:
    """A person cannot tick this task: only its fact closes it."""
    return task.closing_fact is not None and not _template_manual(task)


async def _names(db: AsyncSession, tasks: list[Task]) -> dict[str, dict[UUID, str]]:
    assignment_ids = {t.assignment_id for t in tasks} - {None}
    vacancy_ids = {t.vacancy_id for t in tasks} - {None}
    person_ids = ({t.assignee_person_id for t in tasks} - {None}) | (
        {t.completed_by_id for t in tasks} - {None}
    )
    names: dict[str, dict[UUID, str]] = {"assignment": {}, "vacancy": {}, "person": {}}
    if assignment_ids:
        rows = await db.execute(
            select(Assignment.id, Assignment.name).where(
                Assignment.id.in_(assignment_ids)
            )
        )
        names["assignment"] = {row[0]: row[1] for row in rows}
    if vacancy_ids:
        rows = await db.execute(
            select(Vacancy.id, Vacancy.function_title).where(
                Vacancy.id.in_(vacancy_ids)
            )
        )
        names["vacancy"] = {row[0]: row[1] for row in rows}
    if person_ids:
        rows = await db.execute(
            select(Person.id, Person.name).where(Person.id.in_(person_ids))
        )
        names["person"] = {row[0]: row[1] for row in rows}
    return names


async def _views(
    db: AsyncSession,
    access: TaskAccess,
    tasks: list[Task],
    *,
    today: date,
    with_notes: bool = False,
) -> list[TaskView]:
    """The tasks the reader may see, as the reader sees them."""
    await access.prime_vacancies({t.vacancy_id for t in tasks if t.vacancy_id})
    await access.prime_parts(
        {t.vacancy_id for t in tasks if t.vacancy_id and t.case_kind == "vacancy"}
    )
    visible = [task for task in tasks if (await access.of_task(task)).read]
    names = await _names(db, visible)
    views = []
    for task in visible:
        rights = await access.of_task(task)
        mine = await access.is_for_reader(task)
        plan = plan_for(task.plan_version)
        fact_only = closes_by_fact_only(task)
        vacancy_title = (
            names["vacancy"].get(task.vacancy_id) if task.vacancy_id else None
        )
        assignment_name = None
        if task.assignment_id and (
            task.case_kind == "assignment"
            or (await access.assignment(task.assignment_id)).read
        ):
            assignment_name = names["assignment"].get(task.assignment_id)
        if task.case_kind == "vacancy":
            case_label = f"Vacature {vacancy_title}" if vacancy_title else "Vacature"
        else:
            case_label = assignment_name or "Opdracht"
        assignee_name = (
            names["person"].get(task.assignee_person_id)
            if task.assignee_person_id
            else None
        )
        assignee_label = assignee_name or catalogue.ROLE_LABELS.get(
            task.assignee_role or "", "Niemand"
        )
        can_change = task.is_open and (rights.edit or mine)
        notes: list[NoteView] = []
        if with_notes:
            authors = {n.created_by_id for n in task.notes} - {None}
            author_names: dict[UUID, str] = {}
            if authors:
                rows = await db.execute(
                    select(Person.id, Person.name).where(Person.id.in_(authors))
                )
                author_names = {row[0]: row[1] for row in rows}
            notes = [
                NoteView(
                    id=note.id,
                    body=note.body,
                    created_at=note.created_at,
                    author_name=author_names.get(note.created_by_id)
                    if note.created_by_id
                    else None,
                )
                for note in task.notes
            ]
        views.append(
            TaskView(
                task=task,
                case_label=case_label,
                assignment_name=assignment_name,
                vacancy_title=vacancy_title,
                track_label=plan.track_label(task.case_kind, task.track),
                assignee_name=assignee_name,
                assignee_label=assignee_label,
                completed_by_name=names["person"].get(task.completed_by_id)
                if task.completed_by_id
                else None,
                is_mine=mine,
                can_change=can_change,
                has_part=task.is_open and (mine or await access.has_part_in(task)),
                can_take_over=not mine and await access.may_take_over(task),
                can_complete=can_change and not fact_only,
                closes_by_fact=fact_only,
                closing_fact_label=catalogue.FACT_LABELS.get(task.closing_fact or "")
                if task.closing_fact
                else None,
                overdue=task.is_open
                and task.due_on is not None
                and task.due_on < today,
                note_count=len(task.notes),
                notes=notes,
            )
        )
    await telling.tell(db, access, views, today=today)
    return views


async def views_for(
    db: AsyncSession, access: TaskAccess, tasks: list[Task], *, today: date
) -> list[TaskView]:
    """Tasks as the reader sees them, each with what the reader must hear."""
    return await _views(db, access, sorted(tasks, key=_sort_key), today=today)


def _sort_key(task: Task) -> tuple[Any, ...]:
    return (
        task.due_on is None,
        task.due_on or date.max,
        task.created_at or datetime.min.replace(tzinfo=UTC),
        str(task.id),
    )


async def _mine_condition(access: TaskAccess) -> Any:
    subject = access.subject
    roles = await access.assignment_roles()
    conditions = [Task.assignee_person_id == subject.person_id]
    held = sorted(subject.functions & catalogue.FUNCTION_ROLES)
    by_role = Task.assignee_person_id.is_(None)
    if held:
        conditions.append(by_role & Task.assignee_role.in_(held))
    owned = [a for a, role in roles.items() if role == "owner"]
    if owned:
        conditions.append(
            by_role & (Task.assignee_role == "owner") & Task.assignment_id.in_(owned)
        )
    if roles:
        conditions.append(
            by_role
            & (Task.assignee_role == "manager")
            & Task.assignment_id.in_(list(roles))
        )
        # Staffing her own assignment is also the owner's or a manager's to
        # do; ``is_for_reader`` confirms it with the access model.
        conditions.append(
            by_role
            & (Task.assignee_role == "planner")
            & Task.assignment_id.in_(list(roles))
        )
    if subject.functions:
        # Advice or approval from someone without an account is recorded by
        # whoever may record it; the telling decides whether that is her.
        conditions.append(
            (Task.case_kind == "vacancy") & Task.template_key.in_(_DECISION_TASKS)
        )
    return or_(*conditions)


async def my_tasks(
    db: AsyncSession, access: TaskAccess, *, today: date
) -> list[TaskView]:
    """Open tasks that are the reader's to do."""
    if access.subject.person_id is None:
        return []
    rows = await db.scalars(
        select(Task)
        .where(Task.status.in_(OPEN_STATUSES), await _mine_condition(access))
        .options(selectinload(Task.notes))
    )
    tasks = sorted(rows.all(), key=_sort_key)
    # The query finds by role; whose a task really is, the access model says
    # (not hers who asked for the approval she could otherwise give).
    views = await _views(db, access, tasks, today=today)
    return [view for view in views if view.is_mine or view.needs_me]


def counts_of(views: list[TaskView]) -> dict[str, int]:
    """How much of the reader's own tasks needs the reader now."""
    to_do = [view for view in views if view.needs_me]
    return {
        "open": len(views),
        "to_do": len(to_do),
        "overdue": sum(1 for view in to_do if view.overdue),
    }


async def my_counts(
    db: AsyncSession, access: TaskAccess, *, today: date
) -> dict[str, int]:
    return counts_of(await my_tasks(db, access, today=today))


@dataclass(frozen=True)
class ToDo:
    """One task a person must do now, for a notification outside the screens."""

    task_id: UUID
    # The template of the plan, or "manual": a stable kind to group on.
    kind: str
    headline: str
    instruction: str
    # Where the work is done, inside the application.
    href: str | None
    due_on: date | None
    overdue: bool


async def to_do_of(db: AsyncSession, access: TaskAccess, *, today: date) -> list[ToDo]:
    """What the person behind ``access`` must do now, the soonest first.

    Never a task the person only waits on. A caller that notifies remembers
    which ``task_id`` it told about: a task appears here when it opens for
    the person or is handed to them, and ``overdue`` turns true when its
    date passes.
    """
    return [
        ToDo(
            task_id=view.task.id,
            kind=view.task.template_key or "manual",
            headline=view.telling.headline if view.telling else view.task.title,
            instruction=view.telling.instruction if view.telling else "",
            href=view.telling.work_href if view.telling else view.task.link,
            due_on=view.task.due_on,
            overdue=view.overdue,
        )
        for view in await my_tasks(db, access, today=today)
        if view.needs_me
    ]


async def awaited_tasks(
    db: AsyncSession, access: TaskAccess, *, today: date
) -> list[TaskView]:
    """Open tasks of others on the cases the reader started.

    The owner of an assignment and the requester of a vacancy wait for what
    others must do on it: a planner who fills a role, an adviser who gives
    advice. Those tasks are not theirs, and they want to see them.
    """
    person_id = access.subject.person_id
    if person_id is None:
        return []
    owned = [
        a for a, role in (await access.assignment_roles()).items() if role == "owner"
    ]
    requested = (
        await db.scalars(select(Vacancy.id).where(Vacancy.requester_id == person_id))
    ).all()
    conditions = []
    if owned:
        conditions.append(
            (Task.case_kind == "assignment") & Task.assignment_id.in_(owned)
        )
    if requested:
        conditions.append(
            (Task.case_kind == "vacancy") & Task.vacancy_id.in_(list(requested))
        )
    if not conditions:
        return []
    rows = await db.scalars(
        select(Task)
        .where(Task.status.in_(OPEN_STATUSES), or_(*conditions))
        .options(selectinload(Task.notes))
    )
    tasks = sorted(rows.all(), key=_sort_key)
    views = await _views(db, access, tasks, today=today)
    return [view for view in views if not view.is_mine]


async def all_tasks(
    db: AsyncSession,
    access: TaskAccess,
    *,
    today: date,
    assignment_id: UUID | None = None,
    vacancy_id: UUID | None = None,
    person_id: UUID | None = None,
    track: str | None = None,
    include_closed: bool = False,
    only_mine: bool = False,
) -> list[TaskView]:
    """Tasks of every case the reader may see, for the board."""
    query = select(Task).options(selectinload(Task.notes))
    if assignment_id is not None:
        query = query.where(Task.assignment_id == assignment_id)
    if vacancy_id is not None:
        query = query.where(Task.vacancy_id == vacancy_id)
    if person_id is not None:
        query = query.where(Task.assignee_person_id == person_id)
    if track:
        query = query.where(Task.track == track)
    if only_mine:
        if access.subject.person_id is None:
            return []
        query = query.where(await _mine_condition(access))
    if include_closed:
        query = query.where(Task.status != "obsolete")
    else:
        query = query.where(Task.status.in_(OPEN_STATUSES))
    rows = await db.scalars(query)
    tasks = sorted(rows.all(), key=_sort_key)
    views = await _views(db, access, tasks, today=today)
    if include_closed:
        # The board shows what was finished lately, not the whole history.
        done = [v for v in views if v.task.status == "done"]
        done.sort(
            key=lambda v: v.task.completed_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        keep = {v.task.id for v in done[:RECENT_DONE]}
        views = [v for v in views if v.task.status != "done" or v.task.id in keep]
    return views


def _headline(view: TaskView) -> str:
    return view.telling.title if view.telling else view.task.title


def _standing(open_views: list[TaskView], done_views: list[TaskView]) -> str:
    """Where a track stands, in one line."""
    waiting = [v for v in open_views if v.task.status == "waiting"]
    doing = [v for v in open_views if v.task.status != "waiting"]
    if doing:
        first = _headline(doing[0])
        more = len(open_views) - 1
        return f"{first}, en {more} andere" if more > 0 else first
    if waiting:
        return _headline(waiting[0])
    if done_views:
        return f"Laatst afgerond: {_headline(done_views[0])}"
    return "Niets te doen"


async def case_tasks(
    db: AsyncSession,
    access: TaskAccess,
    case_kind: str,
    case_id: UUID,
    *,
    today: date,
) -> tuple[Plan, list[TrackView]]:
    """The work on one case, grouped by track."""
    column = Task.assignment_id if case_kind == "assignment" else Task.vacancy_id
    rows = await db.scalars(
        select(Task)
        .where(Task.case_kind == case_kind, column == case_id)
        .where(Task.status != "obsolete")
        .options(selectinload(Task.notes))
    )
    views = await _views(db, access, sorted(rows.all(), key=_sort_key), today=today)
    version = await db.scalar(
        select(TaskCase.plan_version).where(
            TaskCase.case_kind == case_kind, TaskCase.case_id == case_id
        )
    )
    plan = plan_for(version) if version else current_plan()
    tracks = []
    known = [track.key for track in plan.tracks.get(case_kind, ())]
    extra = sorted({v.task.track for v in views} - set(known))
    for key in [*known, *extra]:
        in_track = [v for v in views if v.task.track == key]
        open_views = [v for v in in_track if v.task.is_open]
        done_views = sorted(
            (v for v in in_track if v.task.status == "done"),
            key=lambda v: v.task.completed_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        tracks.append(
            TrackView(
                key=key,
                label=plan.track_label(case_kind, key),
                open_count=len(open_views),
                waiting_count=sum(1 for v in open_views if v.task.status == "waiting"),
                standing=_standing(open_views, done_views),
                tasks=[*open_views, *done_views[:5]],
            )
        )
    return plan, tracks


async def get_task(db: AsyncSession, task_id: UUID) -> Task:
    task = await db.scalar(
        select(Task).where(Task.id == task_id).options(selectinload(Task.notes))
    )
    if task is None:
        raise NotFoundError("Taak", task_id)
    return task


async def view_task(
    db: AsyncSession, access: TaskAccess, task: Task, *, today: date
) -> TaskView | None:
    views = await _views(db, access, [task], today=today, with_notes=True)
    return views[0] if views else None


async def create_manual_task(
    db: AsyncSession,
    *,
    case_kind: str,
    case_id: UUID,
    title: str,
    track: str | None,
    actor: Person,
    assignee_person_id: UUID | None = None,
    due_on: date | None = None,
) -> Task:
    """Add a task by hand to a case. The caller has checked the rights."""
    title = title.strip()
    if not title:
        raise DomainValidationError("Geef de taak een titel.")
    plan = current_plan()
    tracks = [item.key for item in plan.tracks.get(case_kind, ())]
    if case_kind not in catalogue.CASE_KINDS or not tracks:
        raise DomainValidationError("Een taak hoort bij een opdracht of een vacature.")
    if track is None:
        track = tracks[0]
    elif track not in tracks:
        raise DomainValidationError("Dit spoor bestaat niet voor deze zaak.")
    assignment_id: UUID | None = None
    vacancy_id: UUID | None = None
    if case_kind == "assignment":
        if await db.get(Assignment, case_id) is None:
            raise NotFoundError("Opdracht", case_id)
        assignment_id = case_id
    else:
        if await db.get(Vacancy, case_id) is None:
            raise NotFoundError("Vacature", case_id)
        vacancy_id = case_id
    if (
        assignee_person_id is not None
        and await db.get(Person, assignee_person_id) is None
    ):
        raise NotFoundError("Persoon", assignee_person_id)
    task = Task(
        case_kind=case_kind,
        assignment_id=assignment_id,
        vacancy_id=vacancy_id,
        origin="manual",
        title=title[:255],
        track=track,
        assignee_person_id=assignee_person_id or actor.id,
        assigned_by_id=actor.id,
        due_on=due_on,
        status="todo",
        created_by_id=actor.id,
    )
    db.add(task)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="task",
        entity_id=task.id,
        new_value={
            "title": task.title,
            "case_kind": case_kind,
            "case_id": str(case_id),
        },
    )
    return await get_task(db, task.id)


async def set_status(
    db: AsyncSession, task: Task, status: str, *, actor: Person
) -> Task:
    """Move a task. A task that a fact closes cannot be ticked by hand."""
    if status not in _HUMAN_STATUSES:
        raise DomainValidationError("Deze status bestaat niet.")
    if status == task.status:
        return task
    fact_only = closes_by_fact_only(task)
    if task.status == "done" and task.completed_by_fact is not None:
        raise DomainValidationError(
            "Deze taak is vanzelf gesloten en kan niet worden heropend."
        )
    if status == "done" and fact_only:
        label = catalogue.FACT_LABELS.get(task.closing_fact or "", "het werk is gedaan")
        raise DomainValidationError(
            f"Deze taak sluit vanzelf zodra {label}. Afvinken kan niet."
        )
    if status == "obsolete" and task.origin != "manual":
        raise DomainValidationError(
            "Een taak uit het plan vervalt vanzelf als de reden wegvalt."
        )
    old = task.status
    task.status = status
    if status in ("done", "obsolete"):
        task.completed_at = datetime.now(UTC)
        task.completed_by_id = actor.id
    else:
        task.completed_at = None
        task.completed_by_id = None
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="task",
        entity_id=task.id,
        old_value={"status": old},
        new_value={"status": status},
    )
    await db.flush()
    return task


async def assign(
    db: AsyncSession, task: Task, person_id: UUID | None, *, actor: Person
) -> Task:
    """Hand a task to a person, or back to the role the plan gave it."""
    if person_id is not None and task_access.separated(task):
        raise DomainValidationError(SEPARATED)
    if person_id is not None and await db.get(Person, person_id) is None:
        raise NotFoundError("Persoon", person_id)
    if person_id is None and task.origin == "manual":
        raise DomainValidationError("Een eigen taak is altijd van iemand.")
    old = str(task.assignee_person_id) if task.assignee_person_id else None
    task.assignee_person_id = person_id
    # Without a person the plan decides again at its next look.
    task.assigned_by_id = actor.id if person_id is not None else None
    if person_id is not None and task.waiting_on is not None:
        task.waiting_on = None
        if task.status == "waiting":
            task.status = "todo"
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="task",
        entity_id=task.id,
        old_value={"assignee_person_id": old},
        new_value={"assignee_person_id": str(person_id) if person_id else None},
    )
    await db.flush()
    return task


async def take_over(db: AsyncSession, task: Task, *, actor: Person) -> Task:
    """Do someone else's step for them: the task becomes the actor's, and a
    note on the task says from whom it was taken."""
    if not task.is_open:
        raise DomainValidationError("Deze taak is al afgerond.")
    if task.assignee_person_id == actor.id:
        return task
    if task_access.separated(task):
        raise DomainValidationError(SEPARATED)
    previous = (
        await db.get(Person, task.assignee_person_id)
        if task.assignee_person_id
        else None
    )
    holder = (
        previous.name
        if previous is not None
        else telling.role_words(task.assignee_role)
    )
    await assign(db, task, actor.id, actor=actor)
    task.notes.append(
        TaskNote(body=f"Overgenomen van {holder}.", created_by_id=actor.id)
    )
    await db.flush()
    return task


async def update_details(
    db: AsyncSession,
    task: Task,
    *,
    title: str | None = None,
    due_on: date | None = None,
    clear_due: bool = False,
) -> Task:
    """Change title or deadline of a manual task."""
    if task.origin != "manual":
        raise DomainValidationError(
            "Titel en termijn van een taak uit het plan volgen het plan."
        )
    if title is not None:
        if not title.strip():
            raise DomainValidationError("Geef de taak een titel.")
        task.title = title.strip()[:255]
    if clear_due:
        task.due_on = None
    elif due_on is not None:
        task.due_on = due_on
    await db.flush()
    return task


async def add_note(
    db: AsyncSession, task: Task, body: str, *, actor: Person
) -> TaskNote:
    body = body.strip()
    if not body:
        raise DomainValidationError("Een notitie kan niet leeg zijn.")
    note = TaskNote(body=body, created_by_id=actor.id)
    task.notes.append(note)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="task",
        entity_id=task.id,
        new_value={"note_id": str(note.id)},
        assignment_id=task.assignment_id,
        vacancy_id=task.vacancy_id if task.case_kind == "vacancy" else None,
    )
    return note
