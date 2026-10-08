"""The engine: created on a trigger, never twice, closed by a fact."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from grip.models.task import Task
from grip.tasks.engine import add_working_days

from .conftest import INSTANCE, NOW, TODAY


async def tasks(db, *, key: str | None = None, status: str | None = None) -> list[Task]:
    query = select(Task).order_by(Task.created_at, Task.repeat_key)
    if key:
        query = query.where(Task.template_key == key)
    if status:
        query = query.where(Task.status == status)
    await db.flush()
    rows = await db.scalars(query.execution_options(populate_existing=True))
    return list(rows.all())


async def one(db, key: str) -> Task:
    found = await tasks(db, key=key)
    assert len(found) == 1, [(t.template_key, t.repeat_key, t.status) for t in found]
    return found[0]


def keys(found: list[Task]) -> set[str]:
    return {task.template_key for task in found}


# --- the quote track ------------------------------------------------------------


async def test_a_new_external_assignment_asks_for_a_budget(db_session, build, evaluate):
    await build.assignment()
    await evaluate()
    open_tasks = await tasks(db_session, status="todo")
    assert keys(open_tasks) == {"offerte.aanvraag_uitwerken"}
    task = open_tasks[0]
    assert task.track == "offerte"
    assert task.assignee_role == "owner"
    assert task.link.endswith("/begroting")


async def test_running_twice_makes_no_second_task(db_session, build, evaluate):
    await build.assignment()
    first = await evaluate()
    second = await evaluate()
    assert first.created == 1
    assert second.changes == 0
    assert len(await tasks(db_session)) == 1


async def test_the_quote_track_follows_the_facts(db_session, build, evaluate):
    assignment = await build.assignment()
    await evaluate()
    await build.line(assignment)
    await evaluate()
    assert (await one(db_session, "offerte.aanvraag_uitwerken")).status == "done"
    assert (await one(db_session, "offerte.opstellen")).status == "todo"

    quote = await build.quote(assignment)
    assignment.status = "quoted"
    await evaluate()
    drafted = await one(db_session, "offerte.opstellen")
    assert drafted.status == "done"
    assert drafted.completed_by_fact == "quote_fresh"
    assert (await one(db_session, "offerte.aanbieden")).status == "todo"

    await build.offer(quote)
    await evaluate()
    assert (await one(db_session, "offerte.aanbieden")).status == "done"
    waiting = await one(db_session, "offerte.wacht_op_akkoord")
    assert waiting.status == "waiting"
    assert waiting.waiting_on == "de opdrachtgever"

    quote.status = "accepted"
    assignment.status = "accepted"
    await evaluate()
    assert (await one(db_session, "offerte.wacht_op_akkoord")).status == "done"
    assert (await one(db_session, "uitvoering.starten")).status == "todo"


async def test_a_rejection_opens_a_new_round(db_session, build, evaluate):
    assignment = await build.assignment(status="quoted")
    await build.line(assignment)
    quote = await build.quote(assignment, offered=True)
    await evaluate()
    quote.status = "rejected"
    assignment.status = "draft"
    await evaluate()

    waited = await tasks(db_session, key="offerte.wacht_op_akkoord")
    assert [task.status for task in waited] == ["obsolete"]
    assert (await one(db_session, "offerte.reactie_verwerken")).status == "todo"
    # One task for the new quote, the one that says who said no and why:
    # the plain "maak de offerte" does not open beside it.
    rounds = await tasks(db_session, key="offerte.opstellen")
    assert [task for task in rounds if task.status == "todo"] == []

    await build.quote(assignment, issued_at=NOW + timedelta(hours=1))
    await evaluate()
    assert (await one(db_session, "offerte.reactie_verwerken")).status == "done"


async def test_an_internal_assignment_has_no_quote_track(db_session, build, evaluate):
    await build.assignment(kind="internal")
    await evaluate()
    # No quote to make: its own short course starts at the budget.
    assert [task.template_key for task in await tasks(db_session)] == [
        "intern.begroten"
    ]


async def test_a_cancelled_assignment_drops_its_open_tasks(db_session, build, evaluate):
    assignment = await build.assignment()
    await evaluate()
    assignment.status = "cancelled"
    await evaluate()
    assert [task.status for task in await tasks(db_session)] == ["obsolete"]


# --- the client's side ----------------------------------------------------------


async def test_a_received_quote_is_work_for_the_client_only(
    db_session, build, evaluate
):
    us = await build.organisation("Wij als opdrachtgever", instance_uri=INSTANCE)
    assignment = await build.assignment(status="quoted", client=us)
    await build.line(assignment)
    quote = await build.quote(assignment)
    await evaluate()
    open_tasks = await tasks(db_session, status="todo")
    assert keys(open_tasks) == {"offerte.beoordelen_en_tekenen"}
    assert open_tasks[0].assignee_role == "tekenbevoegde"
    assert open_tasks[0].link == f"/aanvragen/offerte/{quote.id}"

    quote.status = "accepted"
    assignment.status = "accepted"
    await evaluate()
    assert (await one(db_session, "offerte.beoordelen_en_tekenen")).status == "done"
    # The contractor's tasks never arise on the client's side.
    assert keys(await tasks(db_session)) == {"offerte.beoordelen_en_tekenen"}


# --- staffing ---------------------------------------------------------------------


async def test_an_unfilled_role_is_a_task_until_it_is_staffed(
    db_session, build, evaluate, create_person
):
    person = await create_person("dev@example.org", name="Dee Developer")
    assignment = await build.assignment(status="accepted")
    line = await build.line(assignment, "Developer", fte="1")
    await build.line(assignment, "Ontwerper", fte="0.5")
    await evaluate()
    roles = await tasks(db_session, key="bemensing.rol_invullen")
    assert sorted(task.title for task in roles) == [
        "Vul de rol Developer in",
        "Vul de rol Ontwerper in",
    ]
    assert {task.assignee_role for task in roles} == {"planner"}

    await build.allocation(line, person, pct="100")
    await evaluate()
    by_title = {
        t.title: t for t in await tasks(db_session, key="bemensing.rol_invullen")
    }
    assert by_title["Vul de rol Developer in"].status == "done"
    assert by_title["Vul de rol Ontwerper in"].status == "todo"


async def test_a_draft_nobody_has_seen_asks_for_no_staffing(
    db_session, build, evaluate
):
    assignment = await build.assignment(status="draft")
    await build.line(assignment)
    await evaluate()
    assert await tasks(db_session, key="bemensing.rol_invullen") == []


async def test_a_deleted_role_takes_its_task_along(db_session, build, evaluate):
    assignment = await build.assignment(status="accepted")
    line = await build.line(assignment)
    await evaluate()
    await db_session.delete(line)
    await db_session.flush()
    await evaluate()
    assert (await one(db_session, "bemensing.rol_invullen")).status == "obsolete"


# --- months and money -------------------------------------------------------------


async def test_one_month_to_close_at_a_time_with_a_deadline(
    db_session, build, evaluate, create_person
):
    person = await create_person("dev@example.org")
    assignment = await build.assignment(status="in_progress")
    await build.terms(assignment, "month")
    line = await build.line(assignment)
    await build.allocation(line, person)
    await evaluate()
    months = await tasks(db_session, key="uitvoering.maand_afsluiten")
    assert [(task.title, task.status) for task in months] == [
        ("Sluit januari 2026 af", "todo")
    ]
    # Five working days after 31 January 2026, a Saturday.
    assert months[0].due_on == date(2026, 2, 6)
    assert months[0].assignee_role == "manager"

    close = await build.close(assignment, date(2026, 1, 1))
    await evaluate()
    months = await tasks(db_session, key="uitvoering.maand_afsluiten")
    assert [(task.title, task.status) for task in months] == [
        ("Sluit januari 2026 af", "done"),
        ("Sluit februari 2026 af", "todo"),
    ]
    delivery = await one(db_session, "financien.factuurgegevens_aanleveren")
    assert delivery.title == "Lever januari 2026 aan"

    export = await build.export(close)
    await evaluate()
    assert (
        await one(db_session, "financien.factuurgegevens_aanleveren")
    ).status == "done"
    assert (await one(db_session, "financien.factuur_vastleggen")).status == "todo"

    await build.invoice(export)
    await evaluate()
    assert (await one(db_session, "financien.factuur_vastleggen")).status == "done"


async def test_a_quarter_is_delivered_once_when_all_its_months_are_closed(
    db_session, build, evaluate, create_person
):
    """Closing stays monthly; delivering follows the billing period."""
    person = await create_person("dev@example.org")
    assignment = await build.assignment(status="in_progress")
    await build.terms(assignment, "quarter")
    await build.allocation(await build.line(assignment), person)
    closes = [await build.close(assignment, date(2026, 1, 1))]
    closes.append(await build.close(assignment, date(2026, 2, 1)))
    await evaluate()
    # Two of three months closed: nothing to deliver yet, no monthly nagging.
    assert await tasks(db_session, key="financien.factuurgegevens_aanleveren") == []

    closes.append(await build.close(assignment, date(2026, 3, 1)))
    await evaluate()
    delivery = await one(db_session, "financien.factuurgegevens_aanleveren")
    assert delivery.title == "Lever het eerste kwartaal van 2026 aan"
    assert delivery.repeat_key == "2026-Q1"
    assert delivery.link.endswith("/maandafsluiting?periode=2026-Q1")
    assert delivery.due_on == add_working_days(NOW.date(), 5)

    exports = [await build.export(close) for close in closes]
    await evaluate()
    assert delivery.status == "done"
    invoice = await one(db_session, "financien.factuur_vastleggen")
    assert invoice.title == "Leg de factuur over het eerste kwartaal van 2026 vast"
    assert invoice.link.endswith("?factuur=2026-01,2026-02,2026-03")
    for export in exports:
        await build.invoice(export)
    await evaluate()
    assert invoice.status == "done"


async def test_the_current_plan_takes_over_cases_of_the_version_it_replaces(
    db_session, build, evaluate, create_person
):
    """An open task the old plan made per month lapses when the period task
    takes its place; the case moves to the current plan."""
    from grip.models.task import TaskCase
    from grip.tasks.plan import current_plan

    person = await create_person("dev@example.org")
    assignment = await build.assignment(status="in_progress")
    await build.terms(assignment, "quarter")
    await build.allocation(await build.line(assignment), person)
    for month in (1, 2, 3):
        await build.close(assignment, date(2026, month, 1))
    # As plan 2026.2 left it: one delivery task per closed month.
    db_session.add(
        TaskCase(
            case_kind="assignment",
            case_id=assignment.id,
            plan_version="2026.2",
            evaluated_at=NOW,
        )
    )
    old = Task(
        case_kind="assignment",
        assignment_id=assignment.id,
        origin="plan",
        template_key="financien.factuurgegevens_aanleveren",
        plan_version="2026.2",
        repeat_key="2026-01",
        dedupe_key=(
            f"financien.factuurgegevens_aanleveren|assignment:{assignment.id}|2026-01"
        ),
        title="Lever de factuurgegevens van januari 2026 aan",
        track="financien",
        subject_kind="closed_month",
        subject_id="2026-01",
        assignee_role="manager",
        status="todo",
        closing_fact="billing_delivered",
    )
    db_session.add(old)
    await db_session.flush()

    await evaluate()
    await db_session.refresh(old)
    assert old.status == "obsolete"
    case = await db_session.get(TaskCase, ("assignment", assignment.id))
    assert case.plan_version == current_plan().version
    fresh = [
        task
        for task in await tasks(db_session, key="financien.factuurgegevens_aanleveren")
        if task.is_open
    ]
    assert [task.title for task in fresh] == ["Lever het eerste kwartaal van 2026 aan"]


async def test_a_reopened_month_reopens_its_task(
    db_session, build, evaluate, create_person
):
    person = await create_person("dev@example.org")
    assignment = await build.assignment(status="in_progress")
    await build.allocation(await build.line(assignment), person)
    close = await build.close(assignment, date(2026, 1, 1))
    await evaluate()
    close.reopened_at = NOW
    close.reopen_reason = "Correctie"
    outcome = await evaluate()
    january = [
        task
        for task in await tasks(db_session, key="uitvoering.maand_afsluiten")
        if task.repeat_key == "2026-01"
    ]
    assert january == [] or january[0].status == "todo"
    assert outcome.created + outcome.reopened >= 1
    titles = {
        task.title
        for task in await tasks(db_session, key="uitvoering.maand_afsluiten")
        if task.is_open
    }
    assert "Sluit januari 2026 af" in titles


async def test_no_month_tasks_before_an_agreement_and_no_billing_on_a_verbal_one(
    db_session, build, evaluate, create_person
):
    person = await create_person("dev@example.org")
    potential = await build.assignment("Potentieel", status="quoted")
    await build.allocation(await build.line(potential), person)
    verbal = await build.assignment("Mondeling", status="verbally_agreed")
    await build.allocation(await build.line(verbal), person)
    await build.close(verbal, date(2026, 1, 1))
    await evaluate()
    months = await tasks(db_session, key="uitvoering.maand_afsluiten")
    assert {task.assignment_id for task in months} == {verbal.id}
    assert await tasks(db_session, key="financien.factuurgegevens_aanleveren") == []


async def test_a_month_that_has_not_ended_is_no_task(
    db_session, build, evaluate, create_person
):
    person = await create_person("dev@example.org")
    assignment = await build.assignment(
        status="in_progress", start=date(2026, 10, 1), end=date(2026, 12, 31)
    )
    await build.allocation(await build.line(assignment), person)
    await evaluate(today=date(2026, 10, 31))
    assert await tasks(db_session, key="uitvoering.maand_afsluiten") == []
    await evaluate(today=date(2026, 11, 1))
    month = await one(db_session, "uitvoering.maand_afsluiten")
    assert month.title == "Sluit oktober 2026 af"
    assert month.due_on == date(2026, 11, 6)


async def test_the_final_report_closes_by_its_fact(db_session, build, evaluate):
    assignment = await build.assignment(status="completed")
    await evaluate()
    assert (await one(db_session, "uitvoering.eindrapport")).status == "todo"
    await build.final_report(assignment)
    await evaluate()
    assert (await one(db_session, "uitvoering.eindrapport")).status == "done"


# --- vacancies --------------------------------------------------------------------


async def test_a_vacancy_walks_through_its_procedure(
    db_session, build, evaluate, create_person
):
    requester = await create_person("vraag@example.org", name="Vera Vraag")
    adviser = await create_person("hr@example.org", name="Hanna HR")
    vacancy = await build.vacancy(requester=requester)
    await evaluate()
    prepare = await one(db_session, "werving.aanvraag_voorbereiden")
    assert prepare.assignee_person_id == requester.id
    assert prepare.track == "werving"

    vacancy.status = "requested"
    vacancy.requested_on = TODAY
    await build.decision(vacancy, "hr_advice", person=adviser)
    await evaluate()
    assert (await one(db_session, "werving.aanvraag_voorbereiden")).status == "done"
    hr = await one(db_session, "werving.advies_hr")
    assert hr.assignee_person_id == adviser.id
    assert hr.status == "todo"
    assert hr.due_on == add_working_days(TODAY, 5)
    # Nobody with an account is named for control: the requester waits.
    control = await one(db_session, "werving.advies_control")
    assert control.assignee_person_id == requester.id
    assert control.status == "waiting"
    assert control.waiting_on == "de controller"
    assert await tasks(db_session, key="werving.akkoord") == []

    decisions = {d.kind: d for d in vacancy.decisions}
    decisions["hr_advice"].agreed = True
    await build.decision(vacancy, "control_advice", agreed=True)
    await evaluate()
    assert (await one(db_session, "werving.advies_hr")).status == "done"
    assert (await one(db_session, "werving.advies_control")).status == "done"
    assert (await one(db_session, "werving.akkoord")).status == "waiting"

    await build.decision(vacancy, "approval", agreed=True)
    vacancy.status = "approved"
    await evaluate()
    assert (await one(db_session, "werving.akkoord")).status == "done"
    assert (await one(db_session, "werving.openstellen")).status == "todo"

    vacancy.status = "open"
    await evaluate()
    assert (await one(db_session, "werving.openstellen")).status == "done"
    assert (await one(db_session, "werving.vervullen")).status == "todo"

    hired = await create_person(None, name="Nieuwe Collega")
    await build.hire(vacancy, hired)
    await evaluate()
    assert (await one(db_session, "werving.vervullen")).status == "done"
    assert (await one(db_session, "werving.collega_voorstellen")).status == "todo"
    account = await one(db_session, "werving.account_aanvragen")
    assert account.status == "todo"
    # Class A of the case: the title never names the person.
    assert "Nieuwe Collega" not in account.title

    hired.email = "nieuwe.collega@example.org"
    hired.wies_public_id = "wies-123"
    await evaluate()
    assert (await one(db_session, "werving.account_aanvragen")).status == "done"
    assert (await one(db_session, "werving.collega_voorstellen")).status == "done"


async def test_a_named_adviser_gets_the_task_once_named(
    db_session, build, evaluate, create_person
):
    requester = await create_person("vraag@example.org")
    adviser = await create_person("hr@example.org")
    vacancy = await build.vacancy(status="requested", requester=requester)
    await evaluate()
    assert (await one(db_session, "werving.advies_hr")).status == "waiting"
    await build.decision(vacancy, "hr_advice", person=adviser)
    await evaluate()
    hr = await one(db_session, "werving.advies_hr")
    assert (hr.assignee_person_id, hr.status, hr.waiting_on) == (
        adviser.id,
        "todo",
        None,
    )


async def test_a_vacancy_for_a_ready_candidate_skips_the_opening(
    db_session, build, evaluate
):
    await build.vacancy(status="approved", vacancy_type="gerede")
    await evaluate()
    assert keys(await tasks(db_session, status="todo")) == {"werving.vervullen"}


async def test_a_withdrawn_vacancy_drops_its_tasks(db_session, build, evaluate):
    vacancy = await build.vacancy(status="requested")
    await evaluate()
    vacancy.status = "withdrawn"
    await evaluate()
    assert {task.status for task in await tasks(db_session)} == {"obsolete"}


# --- what the engine leaves alone ---------------------------------------------------


async def test_a_person_s_choices_survive_the_engine(
    db_session, build, evaluate, create_person
):
    someone = await create_person("iemand@example.org")
    await build.assignment()
    await evaluate()
    task = await one(db_session, "offerte.aanvraag_uitwerken")
    task.status = "doing"
    task.assignee_person_id = someone.id
    task.assigned_by_id = someone.id
    await db_session.flush()
    await evaluate()
    task = await one(db_session, "offerte.aanvraag_uitwerken")
    assert (task.status, task.assignee_person_id) == ("doing", someone.id)


async def test_a_manual_task_is_never_touched(
    db_session, build, evaluate, create_person
):
    someone = await create_person("iemand@example.org")
    assignment = await build.assignment(status="cancelled")
    db_session.add(
        Task(
            case_kind="assignment",
            assignment_id=assignment.id,
            origin="manual",
            title="Bel de opdrachtgever",
            track="offerte",
            assignee_person_id=someone.id,
        )
    )
    await db_session.flush()
    await evaluate()
    manual = [task for task in await tasks(db_session) if task.origin == "manual"]
    assert [task.status for task in manual] == ["todo"]


async def test_a_case_keeps_the_plan_it_started_with(db_session, build, evaluate):
    from grip.models.task import TaskCase
    from grip.tasks.plan import current_plan

    assignment = await build.assignment()
    await evaluate()
    row = await db_session.get(TaskCase, ("assignment", assignment.id))
    assert row.plan_version == current_plan().version
    task = await one(db_session, "offerte.aanvraag_uitwerken")
    assert task.plan_version == current_plan().version


def test_working_days_skip_the_weekend():
    assert add_working_days(date(2026, 10, 9), 1) == date(2026, 10, 12)
    assert add_working_days(date(2026, 10, 8), 5) == date(2026, 10, 15)
    assert add_working_days(date(2026, 10, 8), 0) == date(2026, 10, 8)


# --- internal approval of a quote ---------------------------------------------


async def test_a_request_for_approval_is_work_for_the_approver(
    db_session, build, evaluate, create_person
):
    maker = await create_person("maker@example.org")
    assignment = await build.assignment(status="quoted")
    await build.line(assignment)
    quote = await build.quote(assignment)
    quote.reference = "T-2026-0042"
    approval = await build.approval(quote, by=maker)
    await evaluate()
    review = await one(db_session, "offerte.intern_beoordelen")
    assert review.title == "Beoordeel offerte T-2026-0042"
    assert review.assignee_role == "offertegoedkeurder"
    assert review.due_on == add_working_days(TODAY, 3)

    approval.status = "sent_back"
    approval.decided_at = NOW
    await evaluate()
    assert (await one(db_session, "offerte.intern_beoordelen")).status == "done"
    again = await one(db_session, "offerte.na_terugsturen_opnieuw_maken")
    assert again.assignee_person_id == maker.id
    assert again.status == "todo"

    await build.quote(assignment, issued_at=NOW + timedelta(hours=1))
    await evaluate()
    assert (
        await one(db_session, "offerte.na_terugsturen_opnieuw_maken")
    ).status == "done"


async def test_a_withdrawn_request_takes_its_task_along(db_session, build, evaluate):
    assignment = await build.assignment(status="quoted")
    await build.line(assignment)
    approval = await build.approval(await build.quote(assignment))
    await evaluate()
    approval.status = "withdrawn"
    await evaluate()
    assert (await one(db_session, "offerte.intern_beoordelen")).status == "obsolete"


async def test_no_approval_task_without_a_request(db_session, build, evaluate):
    assignment = await build.assignment(status="quoted")
    await build.line(assignment)
    await build.quote(assignment)
    await evaluate()
    assert await tasks(db_session, key="offerte.intern_beoordelen") == []


# --- the texts of a vacancy ----------------------------------------------------


async def test_the_work_on_a_text_comes_as_tasks_closed_by_facts(
    db_session, build, evaluate, create_person
):
    from grip.models.vacancy import Vacancy
    from grip.services.vacancies import text_flow

    requester = await create_person("schrijver@example.org", name="Fictieve Schrijver")
    reviewer = await create_person("lezer2@example.org", name="Fictieve Meelezer")
    vacancy = await build.vacancy(status="draft", requester=requester)
    await evaluate()

    async def of(template: str, status: str | None = None):
        rows = [t for t in await tasks(db_session) if t.template_key == template]
        return [t for t in rows if status is None or t.status == status]

    writing = await of("teksten.schrijven", "todo")
    assert {t.title for t in writing} == {
        "Schrijf de motivatie en stel haar vast",
        "Schrijf de vacaturetekst en stel haar vast",
    }
    assert {t.assignee_person_id for t in writing} == {requester.id}

    row = await db_session.get(Vacancy, vacancy.id)
    first = await text_flow.save_version(
        db_session,
        row,
        "vacancy_text",
        actor=requester,
        body="Eerste versie.",
        based_on_id=None,
    )
    review = await text_flow.offer_for_review(
        db_session, row, "vacancy_text", actor=requester, reviewer_ids=[reviewer.id]
    )
    await evaluate()
    judging = await of("teksten.beoordelen", "todo")
    assert [(t.title, t.assignee_person_id) for t in judging] == [
        ("Beoordeel de vacaturetekst", reviewer.id)
    ]
    assert judging[0].due_on is not None
    # While it lies with the reviewer, nobody is asked to write it.
    assert [t.title for t in await of("teksten.schrijven", "todo")] == [
        "Schrijf de motivatie en stel haar vast"
    ]

    await text_flow.give_verdict(
        db_session, row, review.id, actor=reviewer, verdict="remarks", note="Concreter."
    )
    await evaluate()
    assert [t.status for t in await of("teksten.beoordelen")] == ["done"]
    back = await of("teksten.opmerkingen_verwerken", "todo")
    assert [(t.title, t.assignee_person_id) for t in back] == [
        ("Verwerk de opmerkingen op de vacaturetekst", requester.id)
    ]

    second = await text_flow.save_version(
        db_session,
        row,
        "vacancy_text",
        actor=requester,
        body="Tweede versie.",
        based_on_id=first.id,
    )
    await evaluate()
    assert [t.status for t in await of("teksten.opmerkingen_verwerken")] == ["done"]
    assert "Schrijf de vacaturetekst en stel haar vast" in {
        t.title for t in await of("teksten.schrijven", "todo")
    }

    await text_flow.settle(db_session, row, second.id, actor=requester)
    await evaluate()
    done = {t.title: t.status for t in await of("teksten.schrijven")}
    assert done["Schrijf de vacaturetekst en stel haar vast"] == "done"
    assert done["Schrijf de motivatie en stel haar vast"] == "todo"


async def test_an_open_vacancy_asks_for_its_public_address(
    db_session, build, evaluate, create_person
):
    from grip.models.vacancy import Vacancy
    from grip.services.vacancies import text_flow

    requester = await create_person("opener@example.org")
    vacancy = await build.vacancy(status="open", requester=requester)
    await evaluate()
    link = await one(db_session, "werving.link_vastleggen")
    assert (link.status, link.assignee_person_id) == ("todo", requester.id)
    row = await db_session.get(Vacancy, vacancy.id)
    await text_flow.set_publication(
        db_session,
        row,
        actor=requester,
        place="government_wide",
        url="https://vacatures.example/v/1",
    )
    await evaluate()
    assert (await one(db_session, "werving.link_vastleggen")).status == "done"
