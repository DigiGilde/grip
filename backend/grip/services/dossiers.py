"""The dossier of an assignment: closing it, reopening it, keeping it open.

A closed dossier starts the retention period of the case and changes no more
(ADR 0057). A dossier nobody closes is proposed for closing after a time
without activity, and closes by itself some time after that proposal.
Activity is a change to the case by a person, a guest or another
organisation; a read is none, and neither is anything grip does itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle.restate import RESTATED
from grip.chronicle.writer import changes_of, establish, event_type
from grip.core import clock
from grip.core.audit import UPDATE, record_audit
from grip.events import context, stream
from grip.events.reading import READ_TYPE
from grip.events.retention import ERASED_TYPE
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.stream_event import (
    ACTOR_GUEST,
    ACTOR_PEER,
    ACTOR_PERSON,
    CASE_ASSIGNMENT,
    StreamEvent,
)
from grip.models.task import OPEN_STATUSES, Task
from grip.services import instance_settings, stale
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.guards import DossierClosedError
from grip.services.phase import Phase, phase_of, statuses_in_phase
from grip.services.reports.labels import MONTH_NAMES


def _days_or_off(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainValidationError(
            "Een termijn is een geheel aantal dagen van nul of meer, of leeg."
        )
    return value


PROPOSE_CLOSE_AFTER_DAYS = instance_settings.declare(
    "dossier.propose_close_after_days",
    365,
    _days_or_off,
    "Na hoeveel dagen zonder wijziging de eigenaar van een afgesloten opdracht "
    "het voorstel krijgt het dossier te sluiten (leeg is nooit)",
)
CLOSE_AFTER_PROPOSAL_DAYS = instance_settings.declare(
    "dossier.close_after_proposal_days",
    90,
    _days_or_off,
    "Na hoeveel dagen na dat voorstel grip het dossier zelf sluit (leeg is nooit)",
)

_ACTIVE_ACTORS = (ACTOR_PERSON, ACTOR_GUEST, ACTOR_PEER)
# A read changes nothing, and neither does taking a text out of the record: the
# herstelfeit and its erasure correct the record, not the case. Grip itself
# writes the change lines of a herstelfeit.
_NOT_ACTIVITY = (READ_TYPE, event_type(RESTATED), ERASED_TYPE)
# Taking up a task about the case is work on the case, not a change to it.
# Otherwise touching the proposal would withdraw it.
_NOT_A_CHANGE = ("task", "task_note")
# The task of the plan that carries the proposal (grip/data/tasks/plan.json).
PROPOSAL_TASK = "uitvoering.dossier_sluiten"
_CLOSED_STATUSES = statuses_in_phase(Phase.CLOSED)
_NOT_ENDED = (
    "Een dossier sluit pas als de opdracht is afgerond, verantwoord of geannuleerd."
)


def _check_ended(assignment: Assignment) -> None:
    if phase_of(assignment.status) is not Phase.CLOSED:
        raise DomainValidationError(_NOT_ENDED)


async def _held(session: AsyncSession, assignment_id: UUID) -> Assignment:
    """The assignment as committed once no other act can write to the stream.

    Two acts at the same moment would both pass a check made before the lock.
    """
    await stream.hold_head(session)
    assignment = await session.get(Assignment, assignment_id, populate_existing=True)
    if assignment is None:
        raise NotFoundError("Opdracht", assignment_id)
    return assignment


def _in_words(day: date) -> str:
    return f"{day.day} {MONTH_NAMES[day.month - 1]} {day.year}"


async def _close(
    session: AsyncSession,
    assignment: Assignment,
    *,
    actor: Person | None,
    closed_on: date,
) -> None:
    await establish(
        session,
        "dossier_closed",
        assignment_id=assignment.id,
        actor=actor,
        effective_on=closed_on,
        fields={
            "assignment_id": assignment.id,
            **changes_of(Assignment, dossier_closed_on=closed_on),
        },
    )
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="assignment",
        entity_id=assignment.id,
        old_value={"dossier_closed_on": None},
        new_value={"dossier_closed_on": closed_on.isoformat()},
    )


async def close_dossier(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    actor: Person | None,
    closed_on: date,
) -> Assignment:
    """Close the dossier of an ended assignment on a day up to today.

    Not before the case last changed: the retention period runs from this day.
    """
    assignment = await _held(session, assignment_id)
    await stale.check(session, assignment, "deze opdracht")
    _check_ended(assignment)
    if assignment.dossier_closed_on is not None:
        raise DomainValidationError("Het dossier is al gesloten.")
    if closed_on > clock.today():
        raise DomainValidationError(
            "De dag van sluiten ligt na vandaag. Kies vandaag of een eerdere dag."
        )
    earliest = _quiet_since(assignment, await last_activity(session, [assignment.id]))
    if closed_on < earliest:
        raise DomainValidationError(
            "Die dag ligt voor de laatste wijziging aan de opdracht, op "
            f"{_in_words(earliest)}. Kies die dag of later."
        )
    await _close(session, assignment, actor=actor, closed_on=closed_on)
    return assignment


async def reopen_dossier(
    session: AsyncSession, assignment_id: UUID, *, actor: Person | None, reason: str
) -> Assignment:
    """Open a closed dossier again, so the case can change.

    The reason goes into the fact and its change line, as the reason of a
    change of status does.
    """
    reason = reason.strip()
    if not reason:
        raise DomainValidationError("Geef een reden voor het heropenen.")
    assignment = await _held(session, assignment_id)
    await stale.check(session, assignment, "deze opdracht")
    if assignment.dossier_closed_on is None:
        raise DomainValidationError("Het dossier is niet gesloten.")
    old = assignment.dossier_closed_on
    await establish(
        session,
        "dossier_reopened",
        assignment_id=assignment.id,
        actor=actor,
        fields={"assignment_id": assignment.id, "reason": reason},
    )
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="assignment",
        entity_id=assignment.id,
        old_value={"dossier_closed_on": old.isoformat()},
        new_value={"dossier_closed_on": None, "reason": reason},
    )
    return assignment


async def keep_dossier_open(
    session: AsyncSession, assignment_id: UUID, *, actor: Person | None
) -> Assignment:
    """Say that the dossier of an ended assignment stays open.

    It changes no row; as activity on the case it starts the time until the
    next proposal again.
    """
    assignment = await _held(session, assignment_id)
    if assignment.dossier_closed_on is not None:
        raise DossierClosedError()
    _check_ended(assignment)
    await establish(
        session,
        "dossier_kept_open",
        assignment_id=assignment.id,
        actor=actor,
        fields={"assignment_id": assignment.id},
    )
    return assignment


async def last_activity(
    session: AsyncSession, assignment_ids: Iterable[UUID]
) -> dict[UUID, date]:
    """Per assignment, the day of the latest activity on it, where there is one."""
    ids = list(set(assignment_ids))
    if not ids:
        return {}
    rows = await session.execute(
        select(StreamEvent.case_id, func.max(StreamEvent.occurred_at))
        .where(
            StreamEvent.case_kind == CASE_ASSIGNMENT,
            StreamEvent.case_id.in_(ids),
            StreamEvent.type.notin_(_NOT_ACTIVITY),
            StreamEvent.actor_kind.in_(_ACTIVE_ACTORS),
            StreamEvent.subject_kind.notin_(_NOT_A_CHANGE),
        )
        .group_by(StreamEvent.case_id)
    )
    return {row[0]: clock.local_date(row[1]) for row in rows if row[0] is not None}


async def last_activity_on(session: AsyncSession, assignment_id: UUID) -> date | None:
    """The day of the latest activity on the assignment; None without any."""
    return (await last_activity(session, [assignment_id])).get(assignment_id)


def _quiet_since(assignment: Assignment, active: dict[UUID, date]) -> date:
    # A case nobody ever touched (taken over from elsewhere) counts from its row.
    return active.get(assignment.id) or clock.local_date(assignment.created_at)


def _waits(assignment: Assignment) -> bool:
    """Ended, with a dossier that is still open."""
    return (
        phase_of(assignment.status) is Phase.CLOSED
        and assignment.dossier_closed_on is None
    )


async def due_ids(
    session: AsyncSession,
    assignments: Iterable[Assignment],
    *,
    today: date | None = None,
) -> set[UUID]:
    """The assignments whose dossier is up for closing."""
    waiting = [a for a in assignments if _waits(a)]
    if not waiting:
        return set()
    propose = await instance_settings.get(session, PROPOSE_CLOSE_AFTER_DAYS.key)
    if propose is None:
        return set()
    day = today or clock.today()
    active = await last_activity(session, [a.id for a in waiting])
    return {a.id for a in waiting if (day - _quiet_since(a, active)).days >= propose}


async def dossier_due(
    session: AsyncSession, assignment: Assignment, *, today: date | None = None
) -> bool:
    """Whether the owner should be asked to close the dossier, or say it stays open."""
    return assignment.id in await due_ids(session, [assignment], today=today)


async def _proposed_on(
    session: AsyncSession, assignment_ids: list[UUID]
) -> dict[UUID, date]:
    """Per assignment with an open proposal, the day its task last changed.

    The task keeps its row when it lapses and comes back, so the day it was
    made can lie before the proposal that stands now. A later change to the
    task only moves the day on: grip never closes sooner than it said.
    """
    if not assignment_ids:
        return {}
    rows = await session.execute(
        select(Task.assignment_id, Task.updated_at).where(
            Task.case_kind == CASE_ASSIGNMENT,
            Task.template_key == PROPOSAL_TASK,
            Task.status.in_(OPEN_STATUSES),
            Task.assignment_id.in_(assignment_ids),
        )
    )
    return {row[0]: clock.local_date(row[1]) for row in rows}


async def close_overdue_dossiers(
    session: AsyncSession, *, today: date | None = None
) -> int:
    """Close, as grip itself, every dossier whose proposal nobody answered.

    A dossier closes when its owner has had the proposal for the second
    period and nothing changed on the case since it was made. Without a
    proposal, nothing closes. Returns how many closed; their closing day is
    the day they close.
    """
    propose = await instance_settings.get(session, PROPOSE_CLOSE_AFTER_DAYS.key)
    after = await instance_settings.get(session, CLOSE_AFTER_PROPOSAL_DAYS.key)
    if propose is None or after is None:
        return 0
    day = today or clock.today()
    await stream.hold_head(session)
    waiting = (
        await session.scalars(
            select(Assignment)
            .where(
                Assignment.status.in_(_CLOSED_STATUSES),
                Assignment.dossier_closed_on.is_(None),
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    ids = [a.id for a in waiting]
    proposed = await _proposed_on(session, ids)
    active = await last_activity(session, ids)
    overdue = []
    for assignment in waiting:
        proposed_on = proposed.get(assignment.id)
        quiet_since = _quiet_since(assignment, active)
        if (
            proposed_on is not None
            and (day - proposed_on).days >= after
            and quiet_since <= proposed_on
            and (day - quiet_since).days >= propose
        ):
            overdue.append(assignment)
    with context.scope(
        correlation_id=context.current().correlation_id,
        job="dossiers.close_overdue",
    ):
        for assignment in overdue:
            await _close(session, assignment, actor=None, closed_on=day)
        await session.flush()
    return len(overdue)
