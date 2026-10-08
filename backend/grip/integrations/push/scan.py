"""What to notify about: the scanner the worker runs.

A notification interrupts someone on a locked screen. It is right for
"something now waits on you" and wrong for everything else. So the scanner
looks for exactly three things:

- a task that became yours to do (not one you merely wait on);
- a task of yours whose date passed, once;
- a decision on something you offered: a quote accepted or rejected, an
  internal approval given or sent back.

Tasks are found by asking the task layer the question the screen asks
("which tasks are mine to do?") for every person with a device, and
comparing with what they were told before. Decisions are read from the
stream of events by a cursor. Nothing in the task layer or the domain calls
this module.

Not notified: what the person caused themselves, a kind the person switched
off, and whatever is yours at the moment you register your first device.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.decider import LocalDecider
from grip.access.sql import SqlRelationSource
from grip.access.types import Subject
from grip.core import clock
from grip.core.config import Settings
from grip.integrations.push import outbox
from grip.integrations.push.config import push_config
from grip.models.assignment import AssignmentRole
from grip.models.push import (
    KIND_APPROVAL_GIVEN,
    KIND_APPROVAL_SENT_BACK,
    KIND_OVERDUE,
    KIND_QUOTE_ACCEPTED,
    KIND_QUOTE_REJECTED,
    KIND_TASKS,
    PushCursor,
    PushNotice,
    PushSubscription,
)
from grip.models.stream_event import StreamEvent
from grip.models.task import Task
from grip.repositories.person import PersonRepository
from grip.services import events as domain_events
from grip.services import notifications
from grip.tasks import service as task_service
from grip.tasks.access import TaskAccess

logger = logging.getLogger(__name__)

TASKS_PATH = "/taken"
TASK_PARAM = "taak"
CURSOR_DECISIONS = "decisions"
# A person who changed something on a case this shortly before a task of
# that case opened is looking at it: the task is their own doing.
OWN_ACTION_WINDOW = timedelta(minutes=10)
# A burst is held back at most this long before it is sent anyway.
MAX_HOLD = timedelta(minutes=10)

DECISION_KINDS = {
    domain_events.QUOTE_ACCEPTED: KIND_QUOTE_ACCEPTED,
    domain_events.QUOTE_REJECTED: KIND_QUOTE_REJECTED,
    domain_events.QUOTE_APPROVAL_APPROVED: KIND_APPROVAL_GIVEN,
    domain_events.QUOTE_APPROVAL_SENT_BACK: KIND_APPROVAL_SENT_BACK,
}


async def _people_with_devices(db: AsyncSession) -> set[UUID]:
    rows = await db.execute(select(PushSubscription.person_id).distinct())
    return {row[0] for row in rows}


@dataclass(frozen=True)
class _Mine:
    task: Task
    overdue: bool


async def _mine_to_do(
    db: AsyncSession, person_id: UUID, settings: Settings, today: date
) -> list[_Mine]:
    """The tasks the task layer says are this person's to do now.

    The question is the task layer's own (``to_do_of``): the same answer as
    the number in the navigation, and never a task the person only waits on.
    Its headline and instruction may name an assignment or a vacancy; they
    are not used here.
    """
    functions = await PersonRepository(db).active_function_ids(person_id)
    subject = Subject.for_person(person_id, frozenset(functions))
    decider = LocalDecider(
        SqlRelationSource(db, instance_base_uri=settings.INSTANCE_BASE_URI)
    )
    to_do = await task_service.to_do_of(
        db, TaskAccess(db, decider, subject), today=today
    )
    if not to_do:
        return []
    tasks = {
        task.id: task
        for task in await db.scalars(
            select(Task).where(Task.id.in_([item.task_id for item in to_do]))
        )
    }
    return [
        _Mine(task=tasks[item.task_id], overdue=item.overdue)
        for item in to_do
        if item.task_id in tasks
    ]


async def _noticed(db: AsyncSession, person_id: UUID) -> set[tuple[UUID, str]]:
    rows = await db.execute(
        select(PushNotice.task_id, PushNotice.kind).where(
            PushNotice.person_id == person_id
        )
    )
    return {(task_id, kind) for task_id, kind in rows}


async def _own_doing(db: AsyncSession, person_id: UUID, task: Task) -> bool:
    if task.created_by_id == person_id or task.assigned_by_id == person_id:
        return True
    case_id = task.vacancy_id or task.assignment_id
    if case_id is None or task.created_at is None:
        return False
    found = await db.execute(
        select(func.count())
        .select_from(StreamEvent)
        .where(
            StreamEvent.actor_person_id == person_id,
            StreamEvent.case_id.in_(
                [c for c in (task.vacancy_id, task.assignment_id) if c is not None]
            ),
            StreamEvent.occurred_at >= task.created_at - OWN_ACTION_WINDOW,
            StreamEvent.occurred_at <= task.created_at + timedelta(minutes=1),
        )
    )
    return bool(found.scalar())


def _key(prefix: str, person_id: UUID, task_ids: list[UUID]) -> str:
    digest = hashlib.sha256(
        ",".join(sorted(str(task_id) for task_id in task_ids)).encode()
    ).hexdigest()[:32]
    return f"{prefix}:{person_id}:{digest}"


def _path(tasks: list[Task]) -> str:
    if len(tasks) == 1:
        return f"{TASKS_PATH}?{TASK_PARAM}={tasks[0].id}"
    return TASKS_PATH


async def seed(db: AsyncSession, person_id: UUID, settings: Settings) -> int:
    """Mark what is the person's now as known, without notifying.

    Called when a person registers their first device: what already waited
    is on their screen at that moment and needs no notification.
    """
    views = await _mine_to_do(db, person_id, settings, clock.today())
    known = await _noticed(db, person_id)
    added = 0
    for view in views:
        kinds = [KIND_TASKS] + ([KIND_OVERDUE] if view.overdue else [])
        for kind in kinds:
            if (view.task.id, kind) not in known:
                db.add(
                    PushNotice(
                        person_id=person_id,
                        task_id=view.task.id,
                        kind=kind,
                        notified=False,
                    )
                )
                added += 1
    await db.flush()
    return added


async def scan_tasks(
    db: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
    today: date | None = None,
) -> int:
    """Queue a notice for every person with tasks that are newly theirs."""
    config = push_config(settings)
    if config is None:
        return 0
    moment = now or datetime.now(UTC)
    day = today or moment.astimezone(config.timezone).date()
    people = await _people_with_devices(db)
    preferences = await notifications.preferences_of(db, people)
    queued = 0
    for person_id in people:
        try:
            views = await _mine_to_do(db, person_id, settings, day)
        except Exception:
            # The task layer could not answer for this person; the others
            # still get theirs, and the next look tries again.
            logger.exception("De taken van een persoon konden niet worden gelezen")
            continue
        known = await _noticed(db, person_id)
        preference = preferences[person_id]
        fresh = [view for view in views if (view.task.id, KIND_TASKS) not in known]
        late = [
            view
            for view in views
            if view.overdue
            and (view.task.id, KIND_OVERDUE) not in known
            and (view.task.id, KIND_TASKS) in known
        ]
        if fresh:
            created = [view.task.created_at or moment for view in fresh]
            window = timedelta(seconds=config.batch_seconds)
            # More may follow: hold a burst until it has been quiet for the
            # window, but never longer than the maximum.
            if moment - max(created) < window and moment - min(created) < MAX_HOLD:
                fresh = []
        tell: list[Task] = []
        for view in fresh:
            own = await _own_doing(db, person_id, view.task)
            wanted = preference.wants(notifications.GROUP_TASKS) and not own
            db.add(
                PushNotice(
                    person_id=person_id,
                    task_id=view.task.id,
                    kind=KIND_TASKS,
                    notified=wanted,
                )
            )
            # New and already past its date: one notice, not two.
            if view.overdue:
                db.add(
                    PushNotice(
                        person_id=person_id,
                        task_id=view.task.id,
                        kind=KIND_OVERDUE,
                        notified=False,
                    )
                )
            if wanted:
                tell.append(view.task)
        if tell:
            row = await outbox.enqueue(
                db,
                person_id=person_id,
                kind=KIND_TASKS,
                dedupe_key=_key("tasks", person_id, [task.id for task in tell]),
                count=len(tell),
                badge=len(views),
                path=_path(tell),
                now=moment,
            )
            queued += int(row is not None)
        overdue: list[Task] = []
        for view in late:
            wanted = preference.wants(notifications.GROUP_OVERDUE)
            db.add(
                PushNotice(
                    person_id=person_id,
                    task_id=view.task.id,
                    kind=KIND_OVERDUE,
                    notified=wanted,
                )
            )
            if wanted:
                overdue.append(view.task)
        if overdue:
            row = await outbox.enqueue(
                db,
                person_id=person_id,
                kind=KIND_OVERDUE,
                dedupe_key=_key("overdue", person_id, [task.id for task in overdue]),
                count=len(overdue),
                badge=len(views),
                path=_path(overdue),
                now=moment,
            )
            queued += int(row is not None)
        await db.flush()
    return queued


async def _recipients(db: AsyncSession, event: StreamEvent) -> set[UUID]:
    """Who offered the thing this event decides on."""
    payload = event.payload or {}
    if event.type in (domain_events.QUOTE_ACCEPTED, domain_events.QUOTE_REJECTED):
        assignment_id = payload.get("assignment_id")
        if not assignment_id:
            return set()
        rows = await db.execute(
            select(AssignmentRole.person_id).where(
                AssignmentRole.assignment_id == UUID(str(assignment_id))
            )
        )
        return {row[0] for row in rows}
    requester = payload.get("requested_by_id")
    return {UUID(str(requester))} if requester else set()


async def scan_decisions(
    db: AsyncSession, settings: Settings, *, now: datetime | None = None
) -> int:
    """Queue a notice for decisions on what someone offered, from the stream."""
    if push_config(settings) is None:
        return 0
    cursor = await db.get(PushCursor, CURSOR_DECISIONS)
    if cursor is None:
        # The first look starts at the end: nothing old is notified about.
        latest = (await db.execute(select(func.max(StreamEvent.seq)))).scalar() or 0
        db.add(PushCursor(name=CURSOR_DECISIONS, seq=int(latest)))
        await db.flush()
        return 0
    events = list(
        await db.scalars(
            select(StreamEvent)
            .where(StreamEvent.seq > cursor.seq, StreamEvent.type.in_(DECISION_KINDS))
            .order_by(StreamEvent.seq)
            .limit(500)
        )
    )
    highest = (await db.execute(select(func.max(StreamEvent.seq)))).scalar() or 0
    with_devices = await _people_with_devices(db)
    queued = 0
    for event in events:
        payload = event.payload or {}
        assignment_id = payload.get("assignment_id")
        path = f"/opdrachten/{assignment_id}/offerte" if assignment_id else "/"
        for person_id in await _recipients(db, event):
            # Not for who made the decision themselves, and not for who has
            # no device.
            if person_id == event.actor_person_id or person_id not in with_devices:
                continue
            row = await outbox.enqueue(
                db,
                person_id=person_id,
                kind=DECISION_KINDS[event.type],
                dedupe_key=f"event:{event.id}:{person_id}",
                path=path,
                now=now,
            )
            queued += int(row is not None)
    cursor.seq = int(highest) if len(events) < 500 else int(events[-1].seq)
    await db.flush()
    return queued


async def scan(db: AsyncSession, settings: Settings) -> int:
    return await scan_tasks(db, settings) + await scan_decisions(db, settings)
