"""Taking over a step never grants a right, and a step where someone else
must decide is nobody's to take: not on the screen, not on the server, and
not in the action itself."""

from __future__ import annotations

import pytest

from grip.federation.bridge.acceptance import accept_received_quote
from grip.services import instance_settings, quote_approval
from grip.services.errors import DomainValidationError
from grip.services.vacancies import service as vacancies
from grip.tasks.plan import current_plan

from .test_course import People, _course


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


SEPARATED = {
    "offerte.intern_beoordelen",
    "offerte.beoordelen_en_tekenen",
    "werving.advies_hr",
    "werving.advies_control",
    "werving.akkoord",
    "teksten.beoordelen",
}


def test_the_plan_marks_every_step_where_someone_else_decides():
    plan = current_plan()
    marked = {
        template.key
        for templates in plan.templates.values()
        for template in templates
        if template.separation
    }
    assert marked == SEPARATED


async def _approval_asked(build, people: People, db_session):
    assignment = await build.assignment(status="quoted", owner=people.owner)
    await build.line(assignment)
    quote = await build.quote(assignment)
    quote.issued_by_id = people.owner.id
    await instance_settings.set_values(
        db_session, {quote_approval.MODE.key: quote_approval.MODE_ALWAYS}, actor=None
    )
    await build.approval(quote, by=people.owner)
    await db_session.flush()
    return assignment, quote


async def _judging_task(client) -> dict:
    theirs = (await client.get("/api/tasks/mine")).json()
    return next(t for t in theirs["items"] if t["headline"].startswith("Beoordeel"))


async def test_the_owner_cannot_take_over_the_step_of_the_internal_approver(
    as_person, build, people, db_session
):
    assignment, quote = await _approval_asked(build, people, db_session)
    task = await _judging_task(as_person(people.approver))

    # Not offered: the owner waits, and reads who is at move.
    found = (await _course(as_person(people.owner), "assignment", assignment.id))[
        "course"
    ]
    assert found["current_label"] == "Interne goedkeuring"
    assert found["next"]["mine"] is False
    assert found["next"]["may_take_over"] is False
    assert "interne goedkeurder van offertes" in found["next"]["sentence"]

    # Not accepted: neither taking it, nor handing it to herself.
    owner = as_person(people.owner)
    taken = await owner.post(f"/api/tasks/{task['id']}/takeover")
    assert taken.status_code == 403, taken.text
    handed = await owner.patch(
        f"/api/tasks/{task['id']}", json={"assignee_person_id": str(people.owner.id)}
    )
    assert handed.status_code in (403, 422), handed.text

    # The approver still has it.
    assert (await _judging_task(as_person(people.approver)))["needs_me"] is True

    # And the action itself: who asked may not approve, whatever she holds.
    with pytest.raises(DomainValidationError, match="zelf goedkeuring vroeg"):
        await quote_approval.decide(
            db_session,
            quote.id,
            approve=True,
            actor=people.owner,
            quote_hash=quote.snapshot_hash,
        )


async def test_who_made_the_quote_cannot_approve_it_even_with_the_right(
    as_person, build, people, db_session
):
    _, quote = await _approval_asked(build, people, db_session)
    # Made by the one who holds the right, asked by another.
    quote.issued_by_id = people.approver.id
    await db_session.flush()
    with pytest.raises(DomainValidationError, match="zelf maakte"):
        await quote_approval.decide(
            db_session,
            quote.id,
            approve=True,
            actor=people.approver,
            quote_hash=quote.snapshot_hash,
        )


async def test_being_allowed_to_staff_is_not_being_allowed_to_take_the_owners_step(
    as_person, build, people
):
    """A planner may staff any assignment; that is no right to make its budget."""
    assignment = await build.assignment(status="draft", owner=people.owner)
    planner = as_person(people.planner)
    found = await planner.get(f"/api/tasks/cases/assignment/{assignment.id}/course")
    if found.status_code != 200:
        return  # cannot even read it: nothing to take
    told = found.json()["course"]["next"]
    assert told["may_take_over"] is False
    taken = await planner.post(f"/api/tasks/{told['task_id']}/takeover")
    assert taken.status_code == 403, taken.text


async def test_advice_and_approval_on_a_vacancy_are_not_the_requesters(
    as_person, build, people, create_person, db_session
):
    adviser = await create_person("hr@example.org", name="Hanna HR")
    requester = await create_person(
        "aanvrager@example.org", name="Anna Aanvrager", functions=["planner"]
    )
    vacancy = await build.vacancy(status="requested", requester=requester)
    await build.decision(vacancy, "hr_advice", person=adviser)

    found = (await _course(as_person(requester), "vacancy", vacancy.id))["course"]
    # Whatever the head tells the requester, it does not offer the advice.
    assert found["next"]["may_take_over"] is False
    theirs = (await as_person(adviser).get("/api/tasks/mine")).json()["items"]
    advice = next(t for t in theirs if "advies" in t["headline"].lower())
    taken = await as_person(requester).post(f"/api/tasks/{advice['id']}/takeover")
    assert taken.status_code == 403, taken.text

    # The action: the requester is not who advises or approves.
    for kind in ("hr_advice", "approval"):
        with pytest.raises(DomainValidationError, match="aanvrager kan niet zelf"):
            await vacancies.record_decision(
                db_session,
                vacancy.id,
                kind,
                actor=requester,
                person_name=requester.name,
                person_id=requester.id,
                agreed=True,
            )


async def test_who_made_the_quote_does_not_accept_it_as_the_client(
    build, people, db_session
):
    assignment = await build.assignment(status="quoted", owner=people.owner)
    await build.line(assignment)
    quote = await build.quote(assignment, offered=True)
    quote.issued_by_id = people.owner.id
    await db_session.flush()
    with pytest.raises(DomainValidationError, match="zelf maakte"):
        await accept_received_quote(db_session, quote.id, actor=people.owner)
