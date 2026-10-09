"""The lifecycle of an assignment is an explicit state machine."""

import pytest

from grip.models.assignment import ASSIGNMENT_STATUSES
from grip.services import assignments, events
from grip.services.errors import DomainValidationError, IllegalTransitionError


def test_every_status_has_transitions_defined():
    assert set(assignments.TRANSITIONS) == set(ASSIGNMENT_STATUSES)
    for targets in assignments.TRANSITIONS.values():
        assert targets <= set(ASSIGNMENT_STATUSES)
    assert assignments.TRANSITIONS["accounted"] == frozenset()
    assert assignments.TRANSITIONS["cancelled"] == frozenset()


async def test_happy_path_emits_status_events(db_session, beheerder, make_assignment):
    seen = []

    async def handler(session, event_type, payload):
        seen.append((payload["old_status"], payload["new_status"]))

    events.register_handler(events.ASSIGNMENT_STATUS_CHANGED, handler)
    assignment = await make_assignment()
    path = ["quoted", "accepted", "in_progress", "completed", "accounted"]
    for target in path:
        await assignments.transition(db_session, assignment.id, target, actor=beheerder)

    assert assignment.status == "accounted"
    assert seen == list(zip(["draft", *path[:-1]], path, strict=True))


@pytest.mark.parametrize(
    ("start_path", "target"),
    [
        ([], "accepted"),  # an external assignment needs a quote first
        ([], "in_progress"),
        ([], "completed"),
        (["quoted"], "in_progress"),
        (["quoted", "accepted"], "completed"),
        (["quoted", "accepted"], "quoted"),
        (
            ["quoted", "accepted", "in_progress", "completed", "accounted"],
            "in_progress",
        ),
        (["cancelled"], "draft"),
    ],
)
async def test_illegal_transitions_are_refused(
    db_session, beheerder, make_assignment, start_path, target
):
    assignment = await make_assignment()
    for step in start_path:
        await assignments.transition(db_session, assignment.id, step, actor=beheerder)
    before = assignment.status

    with pytest.raises(IllegalTransitionError):
        await assignments.transition(db_session, assignment.id, target, actor=beheerder)
    assert assignment.status == before


async def test_internal_assignment_skips_the_quote(
    db_session, beheerder, make_assignment
):
    assignment = await make_assignment(kind="internal", client_organisation_id=None)
    await assignments.transition(db_session, assignment.id, "accepted", actor=beheerder)
    assert assignment.status == "accepted"


async def test_unknown_status_is_refused(db_session, beheerder, make_assignment):
    assignment = await make_assignment()
    with pytest.raises(DomainValidationError):
        await assignments.transition(
            db_session, assignment.id, "klaar", actor=beheerder
        )


async def test_creator_becomes_owner_and_new_owner_demotes_the_old(
    db_session, beheerder, create_person, make_assignment
):
    assignment = await make_assignment()
    other = await create_person("manager@example.org")
    from grip.repositories.domain import AssignmentRepository

    roles = await AssignmentRepository(db_session).roles(assignment.id)
    assert [(r.person_id, r.role) for r in roles] == [(beheerder.id, "owner")]

    await assignments.set_assignment_role(
        db_session, assignment.id, other.id, "owner", actor=beheerder
    )
    roles = await AssignmentRepository(db_session).roles(assignment.id)
    assert {(r.person_id, r.role) for r in roles} == {
        (beheerder.id, "manager"),
        (other.id, "owner"),
    }


async def test_request_from_client_and_receipt_at_contractor(
    db_session, beheerder, client_org
):
    seen = []

    async def handler(session, event_type, payload):
        seen.append(payload)

    events.register_handler(events.ASSIGNMENT_REQUEST_CREATED, handler)
    node = "https://corpus.voorbeeldministerie.example/id/node/0b6f1c1e"

    assignment, request_id = await assignments.create_assignment_request(
        db_session,
        name="Opdracht Alfa",
        contractor_organisation_id=client_org.id,
        context_refs=[node],
        actor=beheerder,
    )
    assert assignment.status == "requested"
    assert assignment.uri.endswith(f"/id/opdracht/{assignment.id}")
    assert seen[0]["request_id"] == str(request_id)
    assert seen[0]["context_refs"] == [node]

    # The other side records it under the client's URI, once.
    seen.clear()
    uri = "https://grip.opdrachtgever.example/id/opdracht/3f2a8c54"
    received = await assignments.receive_assignment_request(
        db_session, uri=uri, name="Opdracht Beta", client_organisation_id=client_org.id
    )
    again = await assignments.receive_assignment_request(
        db_session, uri=uri, name="Opdracht Beta", client_organisation_id=client_org.id
    )
    assert received.id == again.id
    assert received.status == "requested"
    assert received.context_refs == []  # context may be empty
    assert seen == []


async def test_final_report_needs_a_completed_assignment(
    db_session, beheerder, make_assignment
):
    seen = []

    async def handler(session, event_type, payload):
        seen.append(payload)

    events.register_handler(events.FINAL_REPORT_ISSUED, handler)
    assignment = await make_assignment()
    report = {"delivered": ["Product A"], "not_delivered": []}

    with pytest.raises(DomainValidationError):
        await assignments.issue_final_report(
            db_session, assignment.id, report, actor=beheerder
        )
    for step in ["quoted", "accepted", "in_progress", "completed"]:
        await assignments.transition(db_session, assignment.id, step, actor=beheerder)
    await assignments.issue_final_report(
        db_session, assignment.id, report, actor=beheerder
    )

    assert seen[0]["report"] == report


def test_unknown_event_type_is_refused():
    async def handler(session, event_type, payload):
        return None

    with pytest.raises(ValueError):
        events.register_handler("quote.unknown", handler)


async def test_an_internal_assignment_is_offered_no_step_towards_a_client(
    make_assignment,
) -> None:
    assignment = await make_assignment(kind="internal", client_organisation_id=None)
    assert assignments.allowed_transitions(assignment) == {"accepted", "cancelled"}
