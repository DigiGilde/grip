"""The proposal to close a dossier, as a task for the owner (ADR 0057)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from grip.core import clock
from grip.events import stream
from grip.services import dossiers
from grip.tasks import course, engine
from grip.tasks import service as task_service
from grip.tasks.cases import AssignmentInputs, assignment_snapshot, live_assignment_ids
from grip.tasks.plan import current_plan, known_plans

from .conftest import NOW
from .test_engine import tasks

KEY = "uitvoering.dossier_sluiten"


async def _ended(db, build, owner, status: str = "accounted"):
    assignment = await build.assignment(status=status, owner=owner)
    await db.refresh(assignment)
    return assignment, clock.local_date(assignment.created_at)


def test_plan_2026_4_asks_for_it_and_keeps_the_older_plans():
    plan = current_plan()
    assert plan.version == "2026.4"
    assert set(plan.replaces) == {"2026.2", "2026.3"}
    assert {"2026.2", "2026.3", "2026.4"} <= set(known_plans())
    assert known_plans()["2026.3"].template(KEY) is None
    template = plan.template(KEY)
    assert template is not None
    assert template.when == ("dossier_due_for_closing",)
    assert template.done_when == "dossier_closed"
    assert template.assignee == "owner"


async def test_a_quiet_ended_case_gets_the_task_for_its_owner(
    db_session, build, evaluate, create_person
):
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    assignment, since = await _ended(db_session, build, owner)

    await evaluate(today=since + timedelta(days=364))
    assert await tasks(db_session, key=KEY) == []

    await evaluate(today=since + timedelta(days=365))
    [task] = await tasks(db_session, key=KEY)
    assert task.status == "todo"
    assert task.assignee_role == "owner"
    assert task.assignment_id == assignment.id
    assert task.link == f"/opdrachten/{assignment.id}"


async def test_the_task_is_done_when_the_dossier_closes(
    db_session, build, evaluate, create_person
):
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    assignment, since = await _ended(db_session, build, owner, status="cancelled")
    day = since + timedelta(days=400)
    await evaluate(today=day)
    await dossiers.close_dossier(
        db_session, assignment.id, actor=owner, closed_on=clock.today()
    )
    await evaluate(today=day)
    [task] = await tasks(db_session, key=KEY)
    assert task.status == "done"
    assert task.completed_by_fact == "dossier_closed"


async def test_the_task_lapses_when_the_dossier_stays_open(
    db_session, build, evaluate, create_person
):
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    assignment, since = await _ended(db_session, build, owner, status="completed")
    day = since + timedelta(days=400)
    await evaluate(today=day)
    assert [t.status for t in await tasks(db_session, key=KEY)] == ["todo"]

    with stream.recording_at(datetime.combine(day, time(12), UTC)):
        await dossiers.keep_dossier_open(db_session, assignment.id, actor=owner)
        await db_session.flush()
    await evaluate(today=day)
    [task] = await tasks(db_session, key=KEY)
    assert task.status == "obsolete"


async def test_the_engine_looks_at_ended_cases_until_their_dossier_closes(
    db_session, build, create_person
):
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    accounted, _ = await _ended(db_session, build, owner)
    cancelled, _ = await _ended(db_session, build, owner, status="cancelled")
    await dossiers.close_dossier(
        db_session, cancelled.id, actor=owner, closed_on=clock.today()
    )
    await db_session.flush()
    live = await live_assignment_ids(db_session)
    assert accounted.id in live
    assert cancelled.id not in live


async def test_a_case_on_plan_2026_3_moves_to_the_current_plan(
    db_session, build, evaluate, create_person
):
    from grip.models.task import TaskCase

    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    assignment, since = await _ended(db_session, build, owner)
    db_session.add(
        TaskCase(
            case_kind="assignment",
            case_id=assignment.id,
            plan_version="2026.3",
            evaluated_at=NOW,
        )
    )
    await db_session.flush()
    await evaluate(today=since + timedelta(days=365))
    row = await db_session.get(TaskCase, ("assignment", assignment.id))
    assert row is not None and row.plan_version == "2026.4"
    assert [t.status for t in await tasks(db_session, key=KEY)] == ["todo"]


async def test_taking_up_the_task_does_not_withdraw_it(
    db_session, build, evaluate, create_person
):
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    _, since = await _ended(db_session, build, owner)
    day = since + timedelta(days=400)
    await evaluate(today=day)
    [task] = await tasks(db_session, key=KEY)
    with stream.recording_at(datetime.combine(day, time(12), UTC)):
        await task_service.set_status(db_session, task, "doing", actor=owner)
        await db_session.flush()
    await evaluate(today=day)
    [task] = await tasks(db_session, key=KEY)
    assert task.status == "doing"


async def test_an_ended_case_taken_in_for_its_dossier_gets_no_other_work(
    db_session, build, evaluate, create_person
):
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    # External and accounted without a final report: the plan would ask for
    # one, had the case not ended before anyone looked.
    _, since = await _ended(db_session, build, owner)
    await evaluate(today=since + timedelta(days=400))
    assert [t.template_key for t in await tasks(db_session)] == [KEY]


async def test_closing_the_dossier_ends_the_other_tasks_of_the_case(
    db_session, build, evaluate, create_person
):
    owner = await create_person("eigenaar@example.org", name="Voorbeeld Eigenaar")
    assignment, _ = await _ended(db_session, build, owner, status="completed")
    await evaluate()
    [report] = await tasks(db_session, key="uitvoering.eindrapport")
    assert report.status == "todo"

    await dossiers.close_dossier(
        db_session, assignment.id, actor=owner, closed_on=clock.today()
    )
    await evaluate()
    [report] = await tasks(db_session, key="uitvoering.eindrapport")
    assert report.status == "obsolete"

    await dossiers.reopen_dossier(db_session, assignment.id, actor=owner)
    await evaluate()
    [report] = await tasks(db_session, key="uitvoering.eindrapport")
    assert report.status == "todo"


def test_a_closed_dossier_ends_the_course_with_nothing_next():
    plan = current_plan()
    snapshot = assignment_snapshot(
        AssignmentInputs(
            id=uuid4(),
            kind="external",
            status="completed",
            is_client=False,
            dossier_closed=True,
        ),
        today=clock.today(),
    )
    [own, *_] = course.at_moment(snapshot, plan, engine.asked_for(snapshot, plan))
    assert own.ended == "Dossier gesloten"
    assert own.next is None
    assert [w.template.key for w in engine.asked_for(snapshot, plan)] == []
