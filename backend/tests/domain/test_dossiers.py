"""The dossier of an assignment: closed with a fact, and then left alone (ADR 0057)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from grip.calc import Month
from grip.chronicle.verify import differences
from grip.core import clock
from grip.events import context, stream
from grip.models.stream_event import StreamEvent
from grip.models.task import Task
from grip.services import (
    assignments,
    billing_deliveries,
    budget_intent,
    costs,
    dossiers,
    instance_settings,
    month_close,
    outgoing_invoices,
    quote_approval,
    quote_drafts,
    quotes,
    restatements,
)
from grip.services.errors import DomainValidationError
from grip.services.guards import DossierClosedError

PROPOSE = dossiers.PROPOSE_CLOSE_AFTER_DAYS.key
AFTER = dossiers.CLOSE_AFTER_PROPOSAL_DAYS.key


async def _finish(db, assignment, actor, *, to: str = "completed"):
    path = ["quoted", "accepted", "in_progress", "completed"]
    if to == "accounted":
        path.append("accounted")
    for step in path:
        if assignment.status == step:
            continue
        await assignments.transition(db, assignment.id, step, actor=actor)
    return assignment


async def _facts(db, assignment_id) -> list[StreamEvent]:
    await db.flush()
    rows = await db.scalars(
        select(StreamEvent)
        .where(
            StreamEvent.subject_kind == "chronolexogram",
            StreamEvent.subject_id == str(assignment_id),
            StreamEvent.type.like("chronolexogram.dossier_%"),
        )
        .order_by(StreamEvent.seq)
    )
    return list(rows)


def _created_on(assignment) -> date:
    return clock.local_date(assignment.created_at)


@pytest.fixture
async def ended(db_session, beheerder, make_assignment):
    return await _finish(db_session, await make_assignment(), beheerder)


@pytest.fixture
async def ended_earlier(db_session, beheerder, make_assignment):
    """Finished a week ago and not changed since."""
    with stream.recording_at(datetime.now(UTC) - timedelta(days=7)):
        assignment = await _finish(db_session, await make_assignment(), beheerder)
        await db_session.flush()
    return assignment


# --- the facts ---------------------------------------------------------------


async def test_closing_is_one_fact_that_sets_the_day(
    db_session, beheerder, ended_earlier
):
    ended = ended_earlier
    day = clock.today() - timedelta(days=3)
    await dossiers.close_dossier(db_session, ended.id, actor=beheerder, closed_on=day)

    assert ended.dossier_closed_on == day
    [fact] = await _facts(db_session, ended.id)
    assert fact.type == "chronolexogram.dossier_closed"
    assert fact.actor_person_id == beheerder.id
    assert fact.new_value["kind"] == "decretogram"
    assert fact.new_value["effective_on"] == day.isoformat()
    assert fact.new_value["fields"] == {
        "assignment_id": str(ended.id),
        "dossier_closed_on": day.isoformat(),
    }
    report = await differences(db_session, ended.id)
    assert report.checked and not report.differences


async def test_reopening_clears_the_day_and_keeping_open_changes_no_row(
    db_session, beheerder, ended
):
    await dossiers.keep_dossier_open(db_session, ended.id, actor=beheerder)
    assert ended.dossier_closed_on is None
    await dossiers.close_dossier(
        db_session, ended.id, actor=beheerder, closed_on=clock.today()
    )
    await dossiers.reopen_dossier(db_session, ended.id, actor=beheerder)

    assert ended.dossier_closed_on is None
    facts = await _facts(db_session, ended.id)
    assert [f.type.removeprefix("chronolexogram.") for f in facts] == [
        "dossier_kept_open",
        "dossier_closed",
        "dossier_reopened",
    ]
    assert facts[0].new_value["fields"] == {"assignment_id": str(ended.id)}
    assert facts[2].new_value["fields"] == {"assignment_id": str(ended.id)}
    report = await differences(db_session, ended.id)
    assert report.checked and not report.differences


@pytest.mark.parametrize("to", ["completed", "accounted"])
async def test_an_ended_assignment_can_close(
    db_session, beheerder, make_assignment, to
):
    assignment = await _finish(db_session, await make_assignment(), beheerder, to=to)
    await dossiers.close_dossier(
        db_session, assignment.id, actor=beheerder, closed_on=clock.today()
    )
    assert assignment.dossier_closed_on == clock.today()


async def test_a_cancelled_assignment_can_close(db_session, beheerder, make_assignment):
    assignment = await make_assignment()
    await assignments.transition(
        db_session, assignment.id, "cancelled", actor=beheerder
    )
    await dossiers.close_dossier(
        db_session, assignment.id, actor=beheerder, closed_on=clock.today()
    )
    assert assignment.dossier_closed_on == clock.today()


# --- what is refused ---------------------------------------------------------


@pytest.mark.parametrize(
    "path", [[], ["quoted"], ["quoted", "accepted", "in_progress"]]
)
async def test_a_running_assignment_cannot_close(
    db_session, beheerder, make_assignment, path
):
    assignment = await make_assignment()
    for step in path:
        await assignments.transition(db_session, assignment.id, step, actor=beheerder)
    with pytest.raises(DomainValidationError, match="afgerond, verantwoord"):
        await dossiers.close_dossier(
            db_session, assignment.id, actor=beheerder, closed_on=clock.today()
        )
    with pytest.raises(DomainValidationError):
        await dossiers.keep_dossier_open(db_session, assignment.id, actor=beheerder)
    assert await _facts(db_session, assignment.id) == []


async def test_a_dossier_closes_once_and_not_after_today(db_session, beheerder, ended):
    with pytest.raises(DomainValidationError, match="na vandaag"):
        await dossiers.close_dossier(
            db_session,
            ended.id,
            actor=beheerder,
            closed_on=clock.today() + timedelta(days=1),
        )
    await dossiers.close_dossier(
        db_session, ended.id, actor=beheerder, closed_on=clock.today()
    )
    with pytest.raises(DomainValidationError, match="al gesloten"):
        await dossiers.close_dossier(
            db_session, ended.id, actor=beheerder, closed_on=clock.today()
        )
    with pytest.raises(DossierClosedError):
        await dossiers.keep_dossier_open(db_session, ended.id, actor=beheerder)


async def test_a_dossier_does_not_close_before_the_case_last_changed(
    db_session, beheerder, ended_earlier
):
    last = await dossiers.last_activity_on(db_session, ended_earlier.id)
    assert last == clock.today() - timedelta(days=7)
    with pytest.raises(DomainValidationError, match="voor de laatste wijziging"):
        await dossiers.close_dossier(
            db_session,
            ended_earlier.id,
            actor=beheerder,
            closed_on=last - timedelta(days=1),
        )
    await dossiers.close_dossier(
        db_session, ended_earlier.id, actor=beheerder, closed_on=last
    )
    assert ended_earlier.dossier_closed_on == last


async def test_after_a_reopen_the_dossier_closes_no_earlier_than_that(
    db_session, beheerder, ended_earlier
):
    week_ago = clock.today() - timedelta(days=7)
    await dossiers.close_dossier(
        db_session, ended_earlier.id, actor=beheerder, closed_on=week_ago
    )
    await dossiers.reopen_dossier(db_session, ended_earlier.id, actor=beheerder)
    with pytest.raises(DomainValidationError, match="voor de laatste wijziging"):
        await dossiers.close_dossier(
            db_session, ended_earlier.id, actor=beheerder, closed_on=week_ago
        )


async def test_an_open_dossier_does_not_reopen(db_session, beheerder, ended):
    with pytest.raises(DomainValidationError, match="niet gesloten"):
        await dossiers.reopen_dossier(db_session, ended.id, actor=beheerder)


# --- a closed dossier changes nothing ----------------------------------------


@pytest.fixture
async def closed_case(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line, make_person
):
    """A quoted, staffed and completed assignment whose dossier is closed."""
    assignment = await make_assignment()
    line = await add_personnel_line(assignment)
    person = await make_person()
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        person.id,
        fte_pct=Decimal("50"),
        actor=beheerder,
    )
    quote = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    await _finish(db_session, assignment, beheerder)
    await dossiers.close_dossier(
        db_session, assignment.id, actor=beheerder, closed_on=clock.today()
    )
    return assignment, line, allocation, quote, person


async def test_every_write_path_refuses_a_closed_dossier(
    db_session, beheerder, closed_case
):
    assignment, line, allocation, quote, person = closed_case
    db = db_session
    cost_item = await costs.create_cost_item(
        db, description="Licenties", actor=beheerder, budgeted_cents=1000
    )
    writes = {
        "update_assignment": lambda: assignments.update_assignment(
            db, assignment.id, actor=beheerder, name="Opdracht Anders"
        ),
        "transition back to in_progress": lambda: assignments.transition(
            db, assignment.id, "in_progress", actor=beheerder
        ),
        "final report": lambda: assignments.issue_final_report(
            db, assignment.id, {"geleverd": []}, actor=beheerder
        ),
        "set role": lambda: assignments.set_assignment_role(
            db, assignment.id, person.id, "manager", actor=beheerder
        ),
        "remove role": lambda: assignments.remove_assignment_role(
            db, assignment.id, beheerder.id, actor=beheerder
        ),
        "add line": lambda: assignments.add_budget_line(
            db,
            assignment.id,
            description="Hosting",
            kind="fixed",
            amount_cents=100,
            year=2026,
            actor=beheerder,
        ),
        "change line": lambda: assignments.update_budget_line(
            db, line.id, actor=beheerder, fte=Decimal("0.5")
        ),
        "intended person": lambda: budget_intent.update_line(
            db, line.id, actor=beheerder, intended_person_id=person.id
        ),
        "remove line": lambda: budget_intent.delete_line(db, line.id, actor=beheerder),
        "add inzet": lambda: assignments.add_allocation(
            db, line.id, beheerder.id, fte_pct=Decimal("10"), actor=beheerder
        ),
        "change inzet": lambda: assignments.update_allocation(
            db, allocation.id, actor=beheerder, fte_pct=Decimal("40")
        ),
        "remove inzet": lambda: assignments.delete_allocation(
            db, allocation.id, actor=beheerder
        ),
        "issue quote": lambda: quotes.issue_quote(db, assignment.id, actor=beheerder),
        "offer quote": lambda: quotes.offer_quote(
            db, quote.id, channel="document", actor=beheerder
        ),
        "ask approval": lambda: quote_approval.request_approval(
            db, quote.id, actor=beheerder
        ),
        "close month": lambda: month_close.close_month(
            db, assignment.id, Month(2026, 1), actor=beheerder
        ),
        "billing terms": lambda: billing_deliveries.set_terms(
            db, assignment.id, actor=beheerder, rhythm="quarterly"
        ),
        "reopen month": lambda: month_close.reopen_month(
            db, assignment.id, Month(2026, 1), actor=beheerder, reason="Herstel"
        ),
        "billing export": lambda: month_close.create_billing_export(
            db, assignment.id, Month(2026, 1), actor=beheerder
        ),
        "quote draft": lambda: quote_drafts.restart(db, assignment, actor=beheerder),
        "draft by the model": lambda: quote_drafts.draft_section(
            db, assignment, "aanleiding", actor=beheerder
        ),
        "cost coverage": lambda: costs.set_coverage(
            db, cost_item.id, line.id, Decimal("50"), actor=beheerder
        ),
        "record invoice": lambda: outgoing_invoices.record_invoice(
            db,
            assignment.id,
            export_ids=[],
            invoice_number="F-1",
            invoice_date=date(2026, 2, 1),
            amount_cents=100,
            actor=beheerder,
        ),
    }
    for name, write in writes.items():
        with pytest.raises(DossierClosedError, match="Heropen het eerst"):
            await write()
            pytest.fail(f"{name} changed a closed dossier")


async def test_a_reopened_dossier_can_change_again(db_session, beheerder, ended):
    await dossiers.close_dossier(
        db_session, ended.id, actor=beheerder, closed_on=clock.today()
    )
    with pytest.raises(DossierClosedError):
        await assignments.update_assignment(
            db_session, ended.id, actor=beheerder, notes="Later"
        )
    await dossiers.reopen_dossier(db_session, ended.id, actor=beheerder)
    await assignments.update_assignment(
        db_session, ended.id, actor=beheerder, notes="Later"
    )
    await assignments.transition(db_session, ended.id, "in_progress", actor=beheerder)
    assert ended.notes == "Later" and ended.status == "in_progress"


# --- activity ----------------------------------------------------------------


async def test_activity_is_a_change_by_a_person_not_a_read_or_grip(
    db_session, beheerder, ended
):
    first = await dossiers.last_activity_on(db_session, ended.id)
    assert first == clock.today()
    later = datetime.now(UTC) + timedelta(days=40)
    with stream.recording_at(later):
        stream.append(
            db_session,
            "data.read",
            subject=("assignment", ended.id),
            actor_person_id=beheerder.id,
            assignment_id=ended.id,
            new={"fields": ["name"]},
        )
        with context.scope(job="test.system"):
            stream.append(
                db_session,
                subject=("assignment", ended.id),
                action="update",
                assignment_id=ended.id,
                old={"notes": None},
                new={"notes": None},
            )
            await db_session.flush()
    assert await dossiers.last_activity_on(db_session, ended.id) == first

    with stream.recording_at(later):
        await dossiers.keep_dossier_open(db_session, ended.id, actor=beheerder)
        await db_session.flush()
    assert await dossiers.last_activity_on(db_session, ended.id) == clock.local_date(
        later
    )


async def test_taking_up_a_task_of_the_case_is_no_activity(
    db_session, beheerder, ended_earlier
):
    from grip.tasks import service as task_service

    before = await dossiers.last_activity_on(db_session, ended_earlier.id)
    task = await task_service.create_manual_task(
        db_session,
        case_kind="assignment",
        case_id=ended_earlier.id,
        title="Voorbeeldtaak",
        track=None,
        actor=beheerder,
    )
    await task_service.set_status(db_session, task, "doing", actor=beheerder)
    await db_session.flush()
    assert await dossiers.last_activity_on(db_session, ended_earlier.id) == before


async def test_taking_a_text_out_of_the_record_is_no_activity(
    db_session, beheerder, make_assignment
):
    with stream.recording_at(datetime.now(UTC) - timedelta(days=7)):
        assignment = await make_assignment()
        await assignments.update_assignment(
            db_session,
            assignment.id,
            actor=beheerder,
            notes="Afwezig wegens een operatie aan de knie",
        )
        await _finish(db_session, assignment, beheerder)
        await db_session.flush()
    before = await dossiers.last_activity_on(db_session, assignment.id)
    changed = await db_session.scalar(
        select(StreamEvent.seq).where(
            StreamEvent.subject_kind == "chronolexogram",
            StreamEvent.subject_id == str(assignment.id),
            StreamEvent.type == "chronolexogram.assignment_changed",
        )
    )
    await restatements.restate_moment(
        db_session, assignment.id, changed, ["assignment.notes"], actor=beheerder
    )
    await db_session.flush()
    assert before is not None and before < clock.today()
    assert await dossiers.last_activity_on(db_session, assignment.id) == before


async def test_a_change_in_the_trace_of_a_herstelfeit_still_counts(
    db_session, beheerder, make_assignment
):
    # A caller chooses its trace id (traceparent): sharing the one of a
    # herstelfeit must not hide a change.
    trace = "4bf92f3577b34da6a3ce929d0e0e4736"
    with stream.recording_at(datetime.now(UTC) - timedelta(days=7)):
        assignment = await make_assignment()
        await assignments.update_assignment(
            db_session,
            assignment.id,
            actor=beheerder,
            notes="Afwezig wegens een operatie aan de knie",
        )
        await _finish(db_session, assignment, beheerder)
        await db_session.flush()
    changed = await db_session.scalar(
        select(StreamEvent.seq).where(
            StreamEvent.subject_kind == "chronolexogram",
            StreamEvent.subject_id == str(assignment.id),
            StreamEvent.type == "chronolexogram.assignment_changed",
        )
    )
    with context.scope(correlation_id=trace):
        await restatements.restate_moment(
            db_session, assignment.id, changed, ["assignment.notes"], actor=beheerder
        )
        await db_session.flush()
    with context.scope(correlation_id=trace):
        await dossiers.keep_dossier_open(db_session, assignment.id, actor=beheerder)
        await db_session.flush()
    assert await dossiers.last_activity_on(db_session, assignment.id) == clock.today()


async def test_without_any_activity_a_case_counts_from_its_row(db_session, ended):
    from grip.models.assignment import Assignment

    stranger = Assignment(
        uri="https://grip.example/id/opdracht/zonder-activiteit",
        name="Opdracht zonder activiteit",
        status="cancelled",
    )
    db_session.add(stranger)
    await db_session.flush()
    await db_session.refresh(stranger)
    assert await dossiers.last_activity_on(db_session, stranger.id) is None
    start = _created_on(stranger)
    assert not await dossiers.dossier_due(
        db_session, stranger, today=start + timedelta(days=364)
    )
    assert await dossiers.dossier_due(
        db_session, stranger, today=start + timedelta(days=365)
    )


# --- the proposal and closing by grip ----------------------------------------


async def test_a_dossier_is_due_after_the_proposal_period(
    db_session, beheerder, make_assignment, ended
):
    quiet = clock.today()
    assert not await dossiers.dossier_due(
        db_session, ended, today=quiet + timedelta(days=364)
    )
    assert await dossiers.dossier_due(
        db_session, ended, today=quiet + timedelta(days=365)
    )
    running = await make_assignment("Opdracht Lopend")
    assert not await dossiers.dossier_due(
        db_session, running, today=quiet + timedelta(days=900)
    )

    await instance_settings.set_values(db_session, {PROPOSE: None}, actor=beheerder)
    assert not await dossiers.dossier_due(
        db_session, ended, today=quiet + timedelta(days=900)
    )
    await instance_settings.set_values(db_session, {PROPOSE: 30}, actor=beheerder)
    # The change of the setting is no activity on the case.
    assert await dossiers.dossier_due(
        db_session, ended, today=quiet + timedelta(days=30)
    )

    await dossiers.close_dossier(db_session, ended.id, actor=beheerder, closed_on=quiet)
    assert not await dossiers.dossier_due(
        db_session, ended, today=quiet + timedelta(days=900)
    )


async def test_settings_are_whole_days_or_empty(db_session, beheerder):
    for wrong in (-1, "365", 1.5, True):
        with pytest.raises(DomainValidationError):
            await instance_settings.set_values(
                db_session, {PROPOSE: wrong}, actor=beheerder
            )
    values = await instance_settings.set_values(
        db_session, {PROPOSE: 0, AFTER: None}, actor=beheerder
    )
    assert values[PROPOSE] == 0 and values[AFTER] is None


async def _propose(db, assignment, on: date) -> Task:
    """The task of the plan that proposes closing, as last changed on a day."""
    task = Task(
        case_kind="assignment",
        assignment_id=assignment.id,
        origin="plan",
        template_key=dossiers.PROPOSAL_TASK,
        plan_version="2026.4",
        dedupe_key=f"{dossiers.PROPOSAL_TASK}|assignment:{assignment.id}|",
        title="Sluit het dossier",
        track="uitvoering",
        assignee_role="owner",
        closing_fact="dossier_closed",
    )
    db.add(task)
    await db.flush()
    task.updated_at = datetime.combine(on, datetime.min.time(), UTC) + timedelta(
        hours=12
    )
    await db.flush()
    return task


async def test_grip_closes_what_nobody_settled(
    db_session, beheerder, make_assignment, ended
):
    other = await _finish(db_session, await make_assignment("Opdracht Beta"), beheerder)
    quiet = clock.today()
    proposed = quiet + timedelta(days=365)
    overdue = proposed + timedelta(days=90)
    await _propose(db_session, ended, proposed)
    await _propose(db_session, other, proposed)

    assert (
        await dossiers.close_overdue_dossiers(
            db_session, today=overdue - timedelta(days=1)
        )
        == 0
    )
    # Kept open just in time: the clock starts again for this one.
    with stream.recording_at(
        datetime.combine(overdue - timedelta(days=1), datetime.min.time(), UTC)
        + timedelta(hours=12)
    ):
        await dossiers.keep_dossier_open(db_session, other.id, actor=beheerder)
        await db_session.flush()

    assert await dossiers.close_overdue_dossiers(db_session, today=overdue) == 1
    assert ended.dossier_closed_on == overdue
    assert other.dossier_closed_on is None
    [fact] = await _facts(db_session, ended.id)
    assert fact.type == "chronolexogram.dossier_closed"
    assert fact.actor_kind == "system" and fact.actor_person_id is None
    assert fact.new_value["fields"]["dossier_closed_on"] == overdue.isoformat()
    # Grip closing a dossier is no activity: the day stays where it was.
    assert await dossiers.last_activity_on(db_session, ended.id) == quiet
    assert await dossiers.close_overdue_dossiers(db_session, today=overdue) == 0


async def test_without_a_proposal_grip_closes_nothing(db_session, ended):
    # The first run on old cases: quiet for years, and nobody was asked yet.
    far = clock.today() + timedelta(days=3000)
    assert await dossiers.close_overdue_dossiers(db_session, today=far) == 0
    assert ended.dossier_closed_on is None


async def test_the_period_after_the_proposal_counts_from_the_proposal(
    db_session, ended
):
    # Quiet long enough for both periods, but proposed only lately.
    proposed = clock.today() + timedelta(days=2000)
    await _propose(db_session, ended, proposed)
    assert (
        await dossiers.close_overdue_dossiers(
            db_session, today=proposed + timedelta(days=89)
        )
        == 0
    )
    assert (
        await dossiers.close_overdue_dossiers(
            db_session, today=proposed + timedelta(days=90)
        )
        == 1
    )


async def test_grip_closes_nothing_when_either_period_is_off(
    db_session, beheerder, ended
):
    far = clock.today() + timedelta(days=3000)
    await instance_settings.set_values(db_session, {AFTER: None}, actor=beheerder)
    assert await dossiers.close_overdue_dossiers(db_session, today=far) == 0
    await instance_settings.set_values(
        db_session, {AFTER: 90, PROPOSE: None}, actor=beheerder
    )
    assert await dossiers.close_overdue_dossiers(db_session, today=far) == 0
    assert ended.dossier_closed_on is None
