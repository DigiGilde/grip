"""The course of a case: where it stands, whose move it is, what is next.

The steps, the sentence about what is next and the tasks are read from the
same facts. These tests walk a case through its whole course and look at all
three at every step, and check the plan data both ways: no step where
someone must act without a task, no task that no step shows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from grip.models.person import Person
from grip.models.quote import QuoteRejection
from grip.models.vacancy import VacancyText
from grip.services import instance_settings, quote_approval
from grip.services.canonical import canonical_form, hash_of
from grip.tasks import catalogue, course
from grip.tasks.cases import CaseSnapshot, Subject
from grip.tasks.plan import PlanError, current_plan, parse_plan
from tests.tasks.conftest import NOW, TODAY

# --- the plan data ----------------------------------------------------------------

# Steps that need nobody to act: they are behind us by the nature of the
# case, or the instance only waits for the other side.
_NO_ACTOR = {
    ("ontvangen", "aanvraag"),
    ("ontvangen", "offerte"),
    ("uitvoering", "akkoord"),
    ("intern", "begroting"),
    ("intern", "starten"),
    # Settling a text is the last act of the task of writing it.
}


def _courses():
    plan = current_plan()
    return [c for kind in catalogue.CASE_KINDS for c in plan.courses.get(kind, ())]


def test_every_course_is_short_and_named_in_words_of_the_work():
    for found in _courses():
        assert 1 <= len(found.steps) <= 5, found.key
        for step in found.steps:
            # A step is a noun or a short phrase, never the machinery.
            assert len(step.label) <= 24, step.label
            for word in ("stap", "werkstroom", "feit", "sjabloon", "taak"):
                assert word not in step.label.lower(), step.label


def test_every_task_belongs_to_a_step_of_a_course():
    plan = current_plan()
    shown = {key for found in _courses() for step in found.steps for key in step.tasks}
    for kind in catalogue.CASE_KINDS:
        for template in plan.templates.get(kind, ()):
            assert template.key in shown, f"{template.key} staat in geen verloop"


def test_every_step_where_someone_must_act_has_a_task_or_says_what_to_wait_for():
    for found in _courses():
        for step in found.steps:
            if (found.key, step.key) in _NO_ACTOR:
                continue
            assert step.tasks or step.idle, (
                f"{found.key}.{step.key} vertelt niemand iets"
            )


def test_a_course_cannot_name_a_fact_nobody_computes():
    data = {
        "version": "test",
        "case_kinds": {
            "vacancy": {
                "tracks": [],
                "templates": [],
                "courses": [
                    {
                        "key": "x",
                        "label": "X",
                        "steps": [
                            {"key": "a", "label": "A", "done_when": ["bestaat_niet"]}
                        ],
                    }
                ],
            }
        },
    }
    with pytest.raises(PlanError):
        parse_plan(data)


def _snapshot(kind: str, facts: set[str], subjects=None) -> CaseSnapshot:
    import uuid

    known = catalogue.CASE_FACTS[kind]
    return CaseSnapshot(
        case_kind=kind,
        case_id=uuid.uuid4(),
        assignment_id=None,
        vacancy_id=None,
        facts={name: name in facts for name in known},
        subjects=subjects or {"case": [Subject(kind="case")]},
    )


def test_work_done_out_of_order_shows_as_done():
    """Hiring starts before the signature, a text is settled before the
    approval: a step that is behind us is done wherever it stands."""
    plan = current_plan()
    werving = next(c for c in plan.courses["vacancy"] if c.key == "werving")
    # Opened although the approval was never recorded in grip.
    case = _snapshot("vacancy", {"requested", "needs_opening", "opened"})
    states = {step.key: state for step, state in course.steps_of(werving, case)}
    assert states == {
        "aanvraag": "done",
        "advies": "current",
        "openstellen": "done",
        "vervullen": "future",
    }


def test_a_step_that_does_not_apply_is_absent():
    plan = current_plan()
    werving = next(c for c in plan.courses["vacancy"] if c.key == "werving")
    # A vacancy for a known candidate is not opened.
    case = _snapshot("vacancy", {"requested", "approval_passed"})
    assert [step.key for step, _ in course.steps_of(werving, case)] == [
        "aanvraag",
        "advies",
        "vervullen",
    ]


def test_no_state_of_any_course_is_a_dead_end():
    """Walk every combination of the facts a course looks at: there is always
    a current step that tells someone something, or the course is behind us."""
    from itertools import product

    plan = current_plan()
    for kind in catalogue.CASE_KINDS:
        for found in plan.courses.get(kind, ()):
            names = sorted(
                {
                    condition.removeprefix("not ")
                    for step in found.steps
                    for condition in (*step.done_when, *step.when)
                }
            )
            for values in product((False, True), repeat=len(names)):
                held = {
                    name for name, value in zip(names, values, strict=True) if value
                }
                case_facts = {name for name in held if "." not in name}
                by_kind: dict[str, dict[str, bool]] = {}
                for name in held:
                    if "." in name:
                        subject_kind, fact = name.split(".", 1)
                        by_kind.setdefault(subject_kind, {})[fact] = True
                subject = None
                subjects = {"case": [Subject(kind="case")]}
                if found.subject != "case":
                    subject = Subject(
                        kind=found.subject,
                        repeat_key="x",
                        facts={n: True for n in case_facts},
                    )
                for subject_kind, facts in by_kind.items():
                    subjects[subject_kind] = [Subject(kind=subject_kind, facts=facts)]
                case = _snapshot(kind, case_facts, subjects)
                states = course.steps_of(found, case, subject)
                current = [step for step, state in states if state == "current"]
                if not current:
                    # Every step that applies is behind us: a clear end.
                    assert all(state == "done" for _, state in states)
                    continue
                assert len(current) == 1
                step = current[0]
                assert step.tasks or step.idle or (found.key, step.key) in _NO_ACTOR, (
                    f"{found.key}.{step.key} is een doodlopend punt"
                )


# --- a case walked through its course ---------------------------------------------


@dataclass
class People:
    owner: Person
    approver: Person
    planner: Person
    reader: Person


@pytest.fixture
async def people(create_person) -> People:
    return People(
        owner=await create_person("eigenaar@example.org", name="Eva Eigenaar"),
        approver=await create_person(
            "akkoord@example.org",
            name="Guus Goedkeurder",
            functions=["offertegoedkeurder"],
        ),
        planner=await create_person("planner@example.org", functions=["planner"]),
        reader=await create_person("lezer@example.org", functions=["lezer"]),
    )


async def _course(client, kind: str, case_id) -> dict:
    response = await client.get(f"/api/tasks/cases/{kind}/{case_id}/course")
    assert response.status_code == 200, response.text
    return response.json()


def _states(found: dict) -> dict[str, str]:
    return {step["label"]: step["state"] for step in found["steps"]}


async def _task_headlines(client, kind: str, case_id) -> set[str]:
    body = (await client.get(f"/api/tasks/cases/{kind}/{case_id}")).json()
    return {
        task["headline"]
        for track in body["tracks"]
        for task in track["tasks"]
        if task["status"] in ("todo", "doing", "waiting")
    }


async def test_a_potential_assignment_walks_to_an_agreement(
    as_person, build, people, db_session
):
    client_org = await build.organisation("Voorbeeldministerie")
    assignment = await build.assignment(
        status="draft", owner=people.owner, client=client_org
    )
    owner = as_person(people.owner)

    # Nothing yet: the budget is the step, and it is the owner's move.
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert found["key"] == "akkoord"
    assert list(_states(found)) == ["Begroting", "Offerte", "Aanbieden", "Akkoord"]
    assert found["current_label"] == "Begroting"
    assert found["position"] == "1 van 4"
    assert found["next"]["mine"] is True
    assert found["next"]["action_text"] == "Maak de begroting"
    assert found["next"]["action_href"].endswith("/begroting")
    # The task says the same, in the same words.
    assert found["next"]["headline"] in await _task_headlines(
        owner, "assignment", assignment.id
    )

    await build.line(assignment)
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert _states(found)["Begroting"] == "done"
    assert found["current_label"] == "Offerte"
    assert found["next"]["action_text"] == "Maak offerte"

    quote = await build.quote(assignment)
    assignment.status = "quoted"
    await db_session.flush()
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert found["current_label"] == "Aanbieden"
    assert found["next"]["mine"] is True
    assert found["next"]["headline"] == "Bied de offerte aan"

    await build.offer(quote)
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert found["current_label"] == "Akkoord"
    # Now the client is waited on: no action for anybody here.
    assert found["next"]["mine"] is False
    assert found["next"]["action_text"] is None
    assert found["next"]["who"] == "Voorbeeldministerie"

    quote.status = "accepted"
    assignment.status = "accepted"
    await db_session.flush()
    found = (await _course(owner, "assignment", assignment.id))["course"]
    # Agreed: the course of the execution takes over, starting is next.
    assert found["key"] == "uitvoering"
    assert _states(found)["Akkoord"] == "done"
    assert found["current_label"] == "Starten"
    assert found["next"]["action_text"] == "Zet in uitvoering"


async def test_the_sentence_fits_how_the_reader_stands_to_the_step(
    as_person, build, people
):
    """Who acts is told what to do, who runs the case with them waits, and
    who only looks on is told where it stands: no "je wacht", no deadline."""
    assignment = await build.assignment(
        status="draft", owner=people.owner, managers=(people.planner,)
    )

    acts = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]["next"]
    assert acts["part"] == "acts"
    assert acts["mine"] is True
    assert acts["action_text"] == "Maak de begroting"

    waits = (await _course(as_person(people.planner), "assignment", assignment.id))[
        "course"
    ]["next"]
    # A manager may do it too, or waits for the owner: never a bystander.
    assert waits["part"] in ("acts", "waits")
    if waits["part"] == "waits":
        assert waits["sentence"].startswith("Je wacht op")

    found = (await _course(as_person(people.reader), "assignment", assignment.id))[
        "course"
    ]
    watches = found["next"]
    assert found["current_label"] == "Begroting"
    assert watches["part"] == "watches"
    assert watches["mine"] is False
    assert watches["action_text"] is None
    assert watches["sentence"] == "Eva Eigenaar is aan zet: de begroting."
    assert "wacht" not in watches["sentence"].lower()
    assert "jij" not in watches["sentence"].lower()
    assert watches["due_on"] is None
    assert watches["overdue"] is False
    assert watches["missing"] == []


async def test_who_waits_for_a_step_of_their_own_case_is_told_so(
    as_person, build, people, db_session
):
    client_org = await build.organisation("Voorbeeldministerie")
    assignment = await build.assignment(
        status="quoted", owner=people.owner, client=client_org
    )
    await build.line(assignment)
    quote = await build.quote(assignment)
    await build.offer(quote)
    waits = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]["next"]
    assert waits["part"] == "waits"
    assert waits["sentence"].startswith("Je wacht op het akkoord van Voorbeeld")


async def test_a_rejected_quote_is_a_step_back_with_its_reason(
    as_person, build, people, db_session
):
    client_org = await build.organisation("Voorbeeldministerie")
    assignment = await build.assignment(
        status="quoted", owner=people.owner, client=client_org
    )
    await build.line(assignment)
    quote = await build.quote(assignment)
    await build.offer(quote)
    quote.status = "rejected"
    assignment.status = "rejected"
    db_session.add(
        QuoteRejection(
            quote_id=quote.id,
            quote_hash=quote.snapshot_hash,
            reason="Het budget is lager vastgesteld.",
            rejected_at=NOW,
        )
    )
    await db_session.flush()

    found = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]
    # Not an end for who made the quote: back at the quote, with a way on.
    assert found["ended"] is None
    assert found["current_label"] == "Offerte"
    assert found["next"]["part"] == "acts"
    assert found["next"]["action_text"] == "Maak een nieuwe offerte"
    sentence = found["next"]["sentence"]
    assert sentence.startswith("Voorbeeldministerie heeft offerte")
    assert 'De reden: "Het budget is lager vastgesteld".' in sentence

    # Who only looks on hears where it stands, not why the client said no.
    watches = (await _course(as_person(people.reader), "assignment", assignment.id))[
        "course"
    ]["next"]
    assert watches["part"] == "watches"
    assert "reden" not in watches["sentence"].lower()


async def test_internal_approval_is_a_step_only_where_it_is_required(
    as_person, build, people, db_session
):
    assignment = await build.assignment(status="quoted", owner=people.owner)
    await build.line(assignment)
    quote = await build.quote(assignment)
    owner = as_person(people.owner)

    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert "Interne goedkeuring" not in _states(found)

    await instance_settings.set_values(
        db_session, {quote_approval.MODE.key: quote_approval.MODE_ALWAYS}, actor=None
    )
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert found["current_label"] == "Interne goedkeuring"
    # The owner is told to ask; offering is not offered as if it could.
    assert found["next"]["mine"] is True
    assert found["next"]["action_text"] == "Vraag goedkeuring"
    headlines = await _task_headlines(owner, "assignment", assignment.id)
    assert "Bied de offerte aan" not in headlines

    asked = await build.approval(quote, by=people.owner)
    found = (await _course(owner, "assignment", assignment.id))["course"]
    # Asked: now the owner waits and the approver has the move.
    assert found["current_label"] == "Interne goedkeuring"
    assert found["next"]["mine"] is False
    # The approver does not run the assignment; the move reaches them as a
    # task that leads to the page where a quote is judged.
    theirs = (await as_person(people.approver).get("/api/tasks/mine")).json()
    judging = [t for t in theirs["items"] if t["headline"].startswith("Beoordeel")]
    assert judging and judging[0]["needs_me"] is True
    assert judging[0]["work_href"].startswith("/goedkeuren/")

    asked.status = "approved"
    asked.decided_at = NOW
    await db_session.flush()
    found = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]
    assert _states(found)["Interne goedkeuring"] == "done"
    assert found["current_label"] == "Aanbieden"
    assert found["next"]["headline"] == "Bied de offerte aan"


async def test_a_quote_sent_back_internally_puts_the_course_back_at_the_quote(
    as_person, build, people, db_session
):
    assignment = await build.assignment(status="quoted", owner=people.owner)
    await build.line(assignment)
    quote = await build.quote(assignment)
    await instance_settings.set_values(
        db_session, {quote_approval.MODE.key: quote_approval.MODE_ALWAYS}, actor=None
    )
    asked = await build.approval(quote, by=people.owner)
    asked.status = "sent_back"
    asked.decided_at = NOW
    asked.decision_note = "De inleiding noemt het verkeerde jaar."
    await db_session.flush()

    found = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]
    # Not "vraag goedkeuring" again on a quote that was sent back.
    assert found["current_label"] == "Offerte"
    assert found["next"]["task_key"] == "offerte.na_terugsturen_opnieuw_maken"
    assert "teruggestuurd" in found["next"]["sentence"]
    # What the reviewer wrote is what the maker must act on.
    assert (
        'De reden: "De inleiding noemt het verkeerde jaar".'
        in found["next"]["sentence"]
    )
    headlines = await _task_headlines(
        as_person(people.owner), "assignment", assignment.id
    )
    assert "Vraag interne goedkeuring" not in headlines


async def test_when_nobody_can_approve_the_head_says_who_grants_the_right(
    as_person, build, create_person, db_session
):
    """No approver among the people: asking is not the step, getting the
    right granted is. The right is named as the interface names it."""
    owner_person = await create_person("eigenaar2@example.org", name="Eva Eigenaar")
    assignment = await build.assignment(status="quoted", owner=owner_person)
    await build.line(assignment)
    await build.quote(assignment)
    await instance_settings.set_values(
        db_session, {quote_approval.MODE.key: quote_approval.MODE_ALWAYS}, actor=None
    )
    found = (await _course(as_person(owner_person), "assignment", assignment.id))[
        "course"
    ]
    sentence = found["next"]["sentence"]
    assert found["current_label"] == "Interne goedkeuring"
    assert "Interne goedkeurder van offertes" in sentence
    assert "Een beheerder geeft dat recht bij Team" in sentence
    assert "offertegoedkeurder" not in sentence
    assert found["next"]["action_text"] != "Vraag goedkeuring"


async def test_a_quote_that_expired_puts_the_course_back_at_the_quote(
    as_person, build, people, db_session
):
    assignment = await build.assignment(status="quoted", owner=people.owner)
    await build.line(assignment)
    quote = await build.quote(assignment, offered=True)
    quote.canonical = canonical_form(
        {"valid_until": (date.today() - timedelta(days=1)).isoformat()}
    )
    quote.snapshot_hash = hash_of(quote.canonical)
    await db_session.flush()
    found = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]
    # Going back is a named thing: a new quote, and the task says why.
    assert found["current_label"] == "Offerte"
    assert found["next"]["headline"] == "Maak een nieuwe offerte"
    assert "verlopen" in found["next"]["sentence"]


async def test_who_runs_the_case_can_do_a_step_for_the_one_at_move(
    as_person, build, people, create_person, db_session
):
    """Visibly: the task becomes theirs, and a note says from whom."""
    manager = await create_person("manager@example.org", name="Mila Manager")
    assignment = await build.assignment(
        status="draft", owner=people.owner, managers=(manager,)
    )
    waits = (await _course(as_person(manager), "assignment", assignment.id))["course"][
        "next"
    ]
    assert waits["part"] == "waits"
    assert waits["may_take_over"] is True

    # A bystander is offered nothing, and is refused when trying.
    watches = (await _course(as_person(people.reader), "assignment", assignment.id))[
        "course"
    ]["next"]
    assert watches["may_take_over"] is False
    refused = await as_person(people.reader).post(
        f"/api/tasks/{waits['task_id']}/takeover"
    )
    assert refused.status_code in (403, 404)

    taken = await as_person(manager).post(f"/api/tasks/{waits['task_id']}/takeover")
    assert taken.status_code == 200, taken.text
    assert [note["body"] for note in taken.json()["notes"]] == [
        "Overgenomen van de eigenaar van de opdracht."
    ]
    mine = (await _course(as_person(manager), "assignment", assignment.id))["course"][
        "next"
    ]
    assert mine["part"] == "acts"
    assert mine["action_text"] == "Maak de begroting"
    # The owner now sees who has it.
    owner = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]["next"]
    assert owner["mine"] is False
    assert owner["who"] == "Mila Manager"


async def test_an_internal_assignment_has_a_short_course_of_its_own(
    as_person, build, people, db_session
):
    """No quote and no agreement: budget, start, execute, each with its step."""
    assignment = await build.assignment(
        status="draft", kind="internal", owner=people.owner
    )
    owner = as_person(people.owner)
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert found["key"] == "intern"
    assert list(_states(found)) == ["Begroting", "Starten", "Uitvoeren"]
    assert found["next"]["action_text"] == "Maak de begroting"

    await build.line(assignment)
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert found["current_label"] == "Starten"
    assert found["next"]["mine"] is True
    assert found["next"]["task_key"] == "intern.starten"
    assert found["next"]["action_text"] == "Start de opdracht"
    assert "offerte" in found["next"]["sentence"]

    # Halfway the two status steps the same task still stands.
    assignment.status = "accepted"
    await db_session.flush()
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert found["key"] == "intern"
    assert found["next"]["task_key"] == "intern.starten"

    assignment.status = "in_progress"
    await db_session.flush()
    found = (await _course(owner, "assignment", assignment.id))["course"]
    assert _states(found) == {
        "Begroting": "done",
        "Starten": "done",
        "Uitvoeren": "current",
    }
    # From here the work of the execution: filling roles, closing months.
    assert found["next"]["task_key"] != "intern.starten"


async def test_an_assignment_that_ended_says_how_and_asks_nothing(
    as_person, build, people
):
    assignment = await build.assignment(status="cancelled", owner=people.owner)
    found = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]
    # Ended before there was an agreement: it did not come to an assignment.
    assert found["ended"] == "Niet doorgegaan"
    assert found["steps"] == []
    assert found["next"] is None


async def test_a_vacancy_walks_from_request_to_filled(
    as_person, build, people, create_person, db_session
):
    requester = await create_person(
        "vraag@example.org", name="Vera Vraag", functions=["planner"]
    )
    vacancy = await build.vacancy(status="draft", requester=requester)
    client = as_person(requester)

    found = (await _course(client, "vacancy", vacancy.id))["course"]
    assert list(_states(found)) == [
        "Aanvraag",
        "Advies en akkoord",
        "Openstellen",
        "Vervullen",
    ]
    assert found["current_label"] == "Aanvraag"
    # Something is missing: the reader hears what, and the step is to fill it.
    assert found["next"]["mine"] is True
    assert found["next"]["action_text"] == "Bereid aanvraag voor"
    assert "schaal" in found["next"]["missing"]

    vacancy.fgr_function_name = "Senior Medewerker ICT (fictief)"
    vacancy.scale = 11
    vacancy.contract_type = "temporary_before_permanent"
    vacancy.addressee_name = "Fictieve Directeur"
    await db_session.flush()
    found = (await _course(client, "vacancy", vacancy.id))["course"]
    # The form is filled in; the motivation printed on it is not settled yet.
    assert found["next"]["action_text"] == "Bereid aanvraag voor"
    assert found["next"]["missing"] == ["een vastgestelde aanleiding en motivatie"]

    db_session.add(
        VacancyText(
            vacancy_id=vacancy.id,
            kind="motivation",
            body="Fictieve motivatie.",
            source="human",
            established_at=NOW,
            established_by_id=requester.id,
        )
    )
    await db_session.flush()
    found = (await _course(client, "vacancy", vacancy.id))["course"]
    assert found["next"]["action_text"] == "Vraag aan"
    assert found["next"]["missing"] == []

    vacancy.status = "requested"
    vacancy.requested_on = TODAY
    await db_session.flush()
    found = (await _course(client, "vacancy", vacancy.id))["course"]
    assert _states(found)["Aanvraag"] == "done"
    assert found["current_label"] == "Advies en akkoord"
    assert found["next"] is not None

    for kind in ("hr_advice", "control_advice", "approval"):
        await build.decision(vacancy, kind, agreed=True)
    vacancy.status = "approved"
    await db_session.flush()
    found = (await _course(client, "vacancy", vacancy.id))["course"]
    assert found["current_label"] == "Openstellen"
    assert found["next"]["mine"] is True

    vacancy.status = "open"
    await db_session.flush()
    found = (await _course(client, "vacancy", vacancy.id))["course"]
    assert found["current_label"] == "Vervullen"

    hired = await create_person("nieuw@example.org", name="Nina Nieuw")
    await build.hire(vacancy, hired)
    found = (await _course(client, "vacancy", vacancy.id))["course"]
    assert all(state == "done" for state in _states(found).values())
    assert found["ended"] == "Vervuld"
    assert found["next"] is None


async def test_a_vacancy_for_a_known_candidate_has_no_opening_step(
    as_person, build, create_person
):
    requester = await create_person("vraag@example.org", functions=["planner"])
    vacancy = await build.vacancy(
        status="approved", vacancy_type="gerede", requester=requester
    )
    found = (await _course(as_person(requester), "vacancy", vacancy.id))["course"]
    assert "Openstellen" not in _states(found)
    assert found["current_label"] == "Vervullen"


async def test_a_withdrawn_vacancy_says_so_and_asks_nothing(
    as_person, build, create_person
):
    requester = await create_person("vraag@example.org", functions=["planner"])
    vacancy = await build.vacancy(status="withdrawn", requester=requester)
    found = (await _course(as_person(requester), "vacancy", vacancy.id))["course"]
    assert found["ended"] == "Ingetrokken"
    assert found["next"] is None


async def test_a_list_says_the_same_as_the_page(as_person, build, people):
    first = await build.assignment(status="draft", owner=people.owner)
    second = await build.assignment(
        "Opdracht Beta 2026", status="accepted", owner=people.owner
    )
    client = as_person(people.owner)
    body = (
        await client.get(
            f"/api/tasks/courses?case_kind=assignment&ids={first.id},{second.id}"
        )
    ).json()
    by_id = {item["case_id"]: item["course"] for item in body["items"]}
    for case in (first, second):
        page = (await _course(client, "assignment", case.id))["course"]
        assert by_id[str(case.id)]["current_label"] == page["current_label"]
        assert by_id[str(case.id)]["next"]["headline"] == page["next"]["headline"]


async def test_a_case_the_reader_may_not_read_is_left_out_of_a_list(
    as_person, build, people, create_person
):
    assignment = await build.assignment(status="draft", owner=people.owner)
    stranger = await create_person("vreemd@example.org", name="Vik Vreemd")
    client = as_person(stranger)
    body = (
        await client.get(f"/api/tasks/courses?case_kind=assignment&ids={assignment.id}")
    ).json()
    assert body["items"] == []
    response = await client.get(f"/api/tasks/cases/assignment/{assignment.id}/course")
    assert response.status_code == 404


async def test_the_person_whose_move_it_is_can_be_notified_of_the_same_thing(
    as_person, build, people, db_session
):
    """Push and the task list follow from the same facts: what the course
    says is the reader's move is in what a notification reads."""
    from grip.access import Subject as Reader
    from grip.access.deps import get_decider, get_relation_source
    from grip.core.config import get_settings
    from grip.tasks import service
    from grip.tasks.access import TaskAccess

    assignment = await build.assignment(status="accepted", owner=people.owner)
    found = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]
    decider = get_decider(get_relation_source(db_session, get_settings()))
    access = TaskAccess(
        db_session, decider, Reader.for_person(people.owner.id, frozenset())
    )
    to_do = await service.to_do_of(db_session, access, today=date.today())
    assert found["next"]["headline"] in {item.headline for item in to_do}
    assert NOW is not None


async def test_on_a_vacancy_who_may_change_it_is_not_who_runs_it(
    as_person, build, people, create_person
):
    """A beheerder may change every vacancy and a reviewer may read the text
    she judges; neither runs the vacancy. They are told who is at move, and
    the reviewer acts only on her own review."""
    requester = await create_person(
        "vraag@example.org", name="Vera Vraag", functions=["planner"]
    )
    # A reviewer who can open the vacancy by a function of her own.
    reviewer = await create_person(
        "oordeel@example.org", name="Olga Oordeel", functions=["planner"]
    )
    onlooker = await create_person(
        "beheer@example.org", name="Bas Beheer", functions=["beheerder"]
    )
    vacancy = await build.vacancy(status="draft", requester=requester)

    acts = (await _course(as_person(requester), "vacancy", vacancy.id))["course"]
    assert acts["next"]["part"] == "acts"

    watches = (await _course(as_person(onlooker), "vacancy", vacancy.id))["course"]
    assert watches["next"]["part"] == "watches"
    assert watches["next"]["sentence"].startswith("Vera Vraag is aan zet")
    assert "wacht" not in watches["next"]["sentence"].lower()
    assert watches["next"]["due_on"] is None

    client = as_person(requester)
    saved = await client.post(
        f"/api/vacancies/{vacancy.id}/text-work/versions",
        json={"kind": "vacancy_text", "body": "## Dit ga je doen\n\nBouwen."},
    )
    assert saved.status_code == 201, saved.text
    asked = await client.post(
        f"/api/vacancies/{vacancy.id}/text-work/reviews",
        json={"kind": "vacancy_text", "reviewer_ids": [str(reviewer.id)]},
    )
    assert asked.status_code == 201, asked.text

    def text_part(found: dict, part: str) -> list[dict]:
        return [
            view["next"]
            for view in found["parts"]
            if view["next"] and view["next"]["part"] == part
        ]

    seen = await _course(as_person(reviewer), "vacancy", vacancy.id)
    # Her verdict is asked: that is hers to do. The rest she looks on at.
    assert text_part(seen, "acts"), seen["parts"]
    assert not text_part(seen, "waits")
    assert seen["course"]["next"]["part"] == "watches"
    assert "wacht" not in seen["course"]["next"]["sentence"].lower()

    waiting = await _course(as_person(requester), "vacancy", vacancy.id)
    # The writer waits for the verdict she asked for: her own text.
    assert [told["sentence"] for told in text_part(waiting, "waits")] != []
    assert all(
        told["sentence"].startswith("Je wacht op")
        for told in text_part(waiting, "waits")
    )
    looking = await _course(as_person(onlooker), "vacancy", vacancy.id)
    assert not text_part(looking, "waits")
    assert not text_part(looking, "acts")
