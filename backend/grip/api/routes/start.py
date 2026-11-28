"""The start page: what is to do and what is going on for the reader.

One answer with a block per relation. Each block asks here what the reader may
read and gets its content from ``grip.services.start``. A block the reader has
no right to, or nothing in, is absent.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from grip.access import Action, DataClass, Resource, build_response
from grip.access.deps import AccessDecider, CurrentSubject
from grip.api.assignment_support import Access, DbSession, RequestAccess
from grip.core import clock
from grip.core.config import Settings, get_settings
from grip.schema.start import (
    ConnectionsOut,
    MyAssignmentRowOut,
    MyAssignmentsOut,
    MyPeopleOut,
    MyPersonRowOut,
    MyRequestRowOut,
    MyRequestsOut,
    MyWorkOut,
    MyWorkRowOut,
    PlanningOut,
    StartFiguresOut,
    ToDoGroupOut,
    ToDoOut,
)
from grip.services import start
from grip.services.reports import investment
from grip.tasks import engine
from grip.tasks import service as tasks
from grip.tasks.access import TaskAccess

router = APIRouter(prefix="/start", tags=["start"])

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
COUNTS = DataClass.STAFFING_COUNTS
M = DataClass.MASTER_DATA
F = DataClass.PERSON_KPI
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL

_ROW_CLASSES = frozenset({A, B, C, ROSTER, SIGNAL})


async def _to_do(
    access: Access, task_access: TaskAccess, db: DbSession, today: date
) -> dict[str, Any]:
    views = await tasks.my_tasks(db, task_access, today=today)
    cases = start.top_five(start.cases_of(views))
    countable = set()
    for case in cases:
        assignment_id = case.assignment_with_month
        # How many months wait is class B or C, whoever the task was handed to.
        if assignment_id is not None and await access.classes(
            Resource.assignment(assignment_id), {B, C}
        ):
            countable.add(assignment_id)
    months = await start.months_to_close(db, countable, today)
    groups = []
    for case in cases:
        task = case.head.task
        told = case.head.telling
        reads_case = await task_access.case(
            task.case_kind, task.assignment_id, task.vacancy_id
        )
        groups.append(
            ToDoGroupOut(
                case_kind=task.case_kind,
                case_id=task.vacancy_id
                if task.case_kind == "vacancy"
                else task.assignment_id,
                case_label=case.head.case_label,
                task_id=task.id,
                headline=told.headline if told else task.title,
                href=(told.work_href if told else None)
                or (start.case_path(case) if reads_case.read else None),
                overdue=case.head.overdue,
                due_on=task.due_on,
                more_text=start.more_text(
                    case,
                    months.get(case.assignment_with_month)
                    if case.assignment_with_month
                    else None,
                ),
            )
        )
    return build_response(
        ToDoOut(groups=groups, total=tasks.counts_of(views)["to_do"]), {A}
    )


async def _my_work(access: Access, db: DbSession, today: date) -> dict[str, Any] | None:
    me = access.subject.person_id
    if me is None:
        return None
    rows = [
        row
        for row in await start.own_work(db, me, today)
        if await access.may(Action.READ, Resource.assignment(row.assignment_id), A)
        and await access.may(Action.READ, Resource.allocation(row.assignment_id, me), C)
    ]
    if not rows:
        return None
    shown, total = start.capped(rows)
    return build_response(
        MyWorkOut(
            person_id=me,
            rows=[
                MyWorkRowOut(
                    assignment_id=row.assignment_id,
                    name=row.name,
                    line=row.line,
                    warning=row.warning,
                )
                for row in shown
            ],
            total=total,
        ),
        {A, C},
    )


async def _my_assignments(
    access: Access,
    task_access: TaskAccess,
    db: DbSession,
    settings: Settings,
    today: date,
    left_out: set[UUID],
) -> dict[str, Any] | None:
    classes_of = {}
    for assignment_id in await task_access.assignment_roles():
        if assignment_id in left_out:
            continue
        classes = await access.classes(Resource.assignment(assignment_id), _ROW_CLASSES)
        if A in classes:
            classes_of[assignment_id] = classes
    found = await start.my_assignments(db, classes_of, today)
    if not found:
        return None
    shown, total = start.capped(found)
    stands = await start.stands_of(
        db, shown, today=today, instance_base_uri=settings.INSTANCE_BASE_URI
    )
    rows = [
        build_response(
            MyAssignmentRowOut(
                assignment_id=item.assignment_id,
                name=item.name,
                line=start.line_of(stands[item.assignment_id], item.notice),
                verdict=item.verdict,
            ),
            classes_of[item.assignment_id],
        )
        for item in shown
    ]
    head = build_response(MyAssignmentsOut(rows=[], total=total), {A})
    return {**head, "rows": rows}


async def _plans(access: Access) -> bool:
    """Whether the reader staffs every assignment. Others may read the same
    figures, and have the board in their own work."""
    return await access.may(Action.EDIT, Resource.assignment(), C)


async def _planning(
    access: Access, db: DbSession, ahead: list[start.PersonAhead], today: date
) -> dict[str, Any] | None:
    if not await _plans(access):
        return None
    if not await access.may(Action.READ, Resource.person(), C):
        return None
    data = await start.planning(db, ahead, today)
    if data.is_empty:
        return None
    return build_response(
        PlanningOut(
            open_roles=data.open_roles,
            open_fte=data.open_fte,
            idle_people=data.idle_people,
            idle_from=data.idle_from,
        ),
        {COUNTS},
    )


async def _my_people(
    access: Access,
    people: list[tuple[UUID, str]],
    ahead: dict[UUID, start.PersonAhead],
) -> dict[str, Any] | None:
    readable = [
        (person_id, name, ahead.get(person_id))
        for person_id, name in people
        if C in await access.classes(Resource.person(person_id), {ROSTER, C})
    ]
    if not readable:
        return None
    ordered = start.people_in_order(readable)
    shown, total = start.capped(ordered)
    return build_response(
        MyPeopleOut(
            rows=[
                MyPersonRowOut(
                    person_id=person_id,
                    name=name,
                    now_pct=person.now_pct if person else None,
                    free_from=person.idle_from if person else None,
                )
                for person_id, name, person in shown
            ],
            total=total,
        ),
        {ROSTER, C},
    )


async def _figures(access: Access, db: DbSession, today: date) -> dict[str, Any] | None:
    if not await access.may(Action.READ, Resource.assignment(), B):
        return None
    data = await start.figures(db, today.year, today)
    withheld = investment.money_withheld(
        data.money.target_person_count,
        sees_targets=await access.may(Action.READ, Resource.person(), F),
    )
    room = None if withheld else data.money.room_cents
    if not any(
        (
            data.expected_cents,
            data.budgeted_cents,
            room,
            data.potential_cents,
            data.quotes_waiting,
        )
    ):
        return None
    body = build_response(
        StartFiguresOut(
            year=data.year,
            expected_cents=data.expected_cents,
            budgeted_cents=data.budgeted_cents,
            room_cents=room,
            shortfall=None if withheld else data.money.shortfall,
            potential_cents=data.potential_cents,
            quotes_waiting=data.quotes_waiting,
            incomplete_by=list(data.incomplete_by),
        ),
        {B},
    )
    return {name: value for name, value in body.items() if value is not None}


async def _my_requests(
    access: Access, task_access: TaskAccess, db: DbSession, today: date
) -> tuple[dict[str, Any] | None, set[UUID]]:
    """The block, and the assignments it holds. Reading a request of someone
    else does not make it mine: the requester is its owner."""
    if not await access.may(Action.REQUEST_ASSIGNMENT, Resource.instance()):
        return None, set()
    roles = await task_access.assignment_roles()
    classes_of = {}
    readable = []
    for row in start.requests_in_order(await start.client_rows(db)):
        if row.assignment.id not in roles:
            continue
        resource = Resource.assignment(row.assignment.id)
        classes = await access.classes(resource, {A, B})
        if A in classes:
            classes_of[row.assignment.id] = classes
            readable.append(row)
    if not readable:
        return None, set()
    shown, total = start.capped(readable)
    requests = await start.my_requests(db, shown, classes_of, today)
    block = build_response(
        MyRequestsOut(
            rows=[
                MyRequestRowOut(
                    assignment_id=item.assignment_id, name=item.name, line=item.line
                )
                for item in requests
            ],
            total=total,
        ),
        {A},
    )
    return block, set(classes_of)


async def _connections(access: Access, db: DbSession) -> dict[str, Any] | None:
    if not await access.may(Action.MANAGE_USERS, Resource.instance()):
        return None
    problems = await start.dead_messages(db)
    if not problems:
        return None
    return build_response(ConnectionsOut(problems=problems), {M})


@router.get("", response_model=None)
async def get_start(
    access: RequestAccess,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """What lies ready for this reader: a block per relation, never by setting."""
    await engine.look(db, settings)
    task_access = TaskAccess(db, decider, subject)
    today = clock.today()
    me = subject.person_id
    people = await start.people_of(db, me) if me is not None else []
    ahead = (
        await start.people_ahead(db, today) if people or await _plans(access) else {}
    )
    my_requests, asked = await _my_requests(access, task_access, db, today)
    blocks = {
        "my_work": await _my_work(access, db, today),
        "my_assignments": await _my_assignments(
            access, task_access, db, settings, today, asked
        ),
        "planning": await _planning(access, db, list(ahead.values()), today),
        "my_people": await _my_people(access, people, ahead),
        "figures": await _figures(access, db, today),
        "my_requests": my_requests,
        "connections": await _connections(access, db),
    }
    return {
        "to_do": await _to_do(access, task_access, db, today),
        **{name: block for name, block in blocks.items() if block is not None},
    }
