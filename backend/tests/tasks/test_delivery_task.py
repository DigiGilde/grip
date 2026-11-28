"""Messages that do not arrive, as a task for the beheerder (ADR 0061).

The facts come from what grip keeps about the trouble per peer
(``delivery_trouble``); the task layer knows nothing of how messages travel.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from grip.models.task import Task
from grip.services import delivery_trouble
from grip.services.delivery_trouble import Trouble
from grip.tasks import engine
from grip.tasks.cases import INSTANCE_CASE_ID, PeerTrouble, instance_snapshot
from grip.tasks.plan import current_plan

from .test_engine import tasks

KEY = "beheer.berichten_laten_aankomen"
SINCE = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
GILDE = uuid.UUID("00000000-0000-4000-8000-000000000020")


def _trouble(peer_id=GILDE, **changes) -> Trouble:
    values = {
        "peer_id": peer_id,
        "peer_name": "Voorbeeldgilde",
        "since": SINCE,
        "message_count": 2,
        "final": False,
        "reason": "unknown_sender",
        "retry_until": SINCE + timedelta(days=7),
        **changes,
    }
    return Trouble(**values)


async def _report(db, *troubles: Trouble) -> None:
    await delivery_trouble.report(db, list(troubles))
    await db.flush()


@pytest.fixture
async def beheerder(create_person):
    return await create_person(
        "beheerder@example.org", name="Voorbeeld Beheerder", functions=["beheerder"]
    )


# --- the facts, without a database ---------------------------------------------


def _peer_trouble(final: bool, reason: str) -> PeerTrouble:
    return PeerTrouble(
        peer_id=GILDE, peer_name="Voorbeeldgilde", final=final, reason=reason
    )


def test_a_peer_is_a_subject_while_messages_to_it_do_not_arrive():
    case = instance_snapshot([_peer_trouble(True, "conflict")], [])
    assert (case.case_kind, case.case_id) == ("instance", INSTANCE_CASE_ID)
    assert case.assignment_id is None and case.vacancy_id is None
    (peer,) = case.subjects_of("peer")
    assert (peer.repeat_key, peer.subject_id) == (str(GILDE), str(GILDE))
    assert peer.facts == {
        "messages_arrive": False,
        "message_refused": True,
        "message_given_up": False,
    }
    assert peer.variables == {"koppeling": "Voorbeeldgilde"}


@pytest.mark.parametrize(
    ("final", "reason", "refused", "given_up"),
    [
        (False, "unknown_sender", False, False),
        (True, "invalid", True, False),
        (True, "gone", True, False),
        (True, "timeout", False, True),
        (True, "unknown_sender", False, True),
    ],
)
def test_a_final_message_is_refused_or_given_up_by_its_reason(
    final, reason, refused, given_up
):
    (peer,) = instance_snapshot([_peer_trouble(final, reason)], []).subjects_of("peer")
    assert (peer.facts["message_refused"], peer.facts["message_given_up"]) == (
        refused,
        given_up,
    )


def test_a_peer_whose_task_is_open_stays_a_subject_once_everything_arrived():
    case = instance_snapshot([], [str(GILDE)])
    (peer,) = case.subjects_of("peer")
    assert peer.facts["messages_arrive"] is True


def test_the_plan_gives_the_beheerder_one_task_per_peer():
    template = current_plan().template(KEY)
    assert template is not None
    assert (template.case_kind, template.subject) == ("instance", "peer")
    assert (template.assignee, template.done_when) == ("beheerder", "messages_arrive")
    assert template.link == "/beheer/koppelingen/{subject_id}"


# --- the engine -----------------------------------------------------------------


async def test_nothing_is_asked_while_every_message_arrives(db_session, evaluate):
    await evaluate()
    assert await tasks(db_session, key=KEY) == []


async def test_a_task_per_peer_while_messages_do_not_arrive(db_session, evaluate):
    other = uuid.uuid4()
    await _report(db_session, _trouble(), _trouble(other, peer_name="Ander voorbeeld"))
    await evaluate()
    found = await tasks(db_session, key=KEY)
    assert sorted(task.repeat_key for task in found) == sorted([str(GILDE), str(other)])
    task = next(task for task in found if task.repeat_key == str(GILDE))
    assert (task.case_kind, task.assignment_id, task.vacancy_id) == (
        "instance",
        None,
        None,
    )
    assert (task.assignee_role, task.assignee_person_id) == ("beheerder", None)
    assert task.title == "Kijk waarom berichten aan Voorbeeldgilde niet aankomen"
    assert task.link == f"/beheer/koppelingen/{GILDE}"
    assert task.situation is None

    # Running again changes nothing.
    outcome = await evaluate()
    assert outcome.changes == 0
    assert len(await tasks(db_session, key=KEY)) == 2


async def test_a_final_message_changes_the_words_not_the_task(db_session, evaluate):
    await _report(db_session, _trouble())
    await evaluate()
    (before,) = await tasks(db_session, key=KEY)
    await _report(db_session, _trouble(final=True, reason="conflict"))
    await evaluate()
    (after,) = await tasks(db_session, key=KEY)
    assert after.id == before.id
    assert (after.status, after.situation) == ("todo", "message_refused")
    await _report(db_session, _trouble(final=True, reason="timeout"))
    await evaluate()
    (given_up,) = await tasks(db_session, key=KEY)
    assert (given_up.id, given_up.situation) == (before.id, "message_given_up")


async def test_the_task_is_done_when_everything_to_the_peer_arrived(
    db_session, evaluate
):
    await _report(db_session, _trouble(final=True))
    await evaluate()
    # Sent again: grip tries once more; nothing is final now.
    await _report(db_session, _trouble(retry_until=None))
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    assert (task.status, task.situation) == ("todo", None)

    await _report(db_session)
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    assert task.status == "done", "done, not lapsed"
    assert task.completed_by_fact == "messages_arrive"
    # Afterwards the instance is not looked at again for it.
    assert await engine.evaluate_instance(db_session) is not None
    assert [t.status for t in await tasks(db_session, key=KEY)] == ["done"]


async def test_trouble_again_opens_the_task_again(db_session, evaluate):
    await _report(db_session, _trouble())
    await evaluate()
    await _report(db_session)
    await evaluate()
    await _report(db_session, _trouble(since=SINCE + timedelta(days=3)))
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    assert task.status == "todo" and task.completed_by_fact is None


async def test_a_task_of_the_instance_names_no_assignment(db_session, build):
    from sqlalchemy.exc import IntegrityError

    def task(**ids) -> Task:
        return Task(
            case_kind="instance", origin="manual", title="Taak", track="beheer", **ids
        )

    db_session.add(task())
    await db_session.flush()
    assignment = await build.assignment()
    db_session.add(task(assignment_id=assignment.id))
    with pytest.raises(IntegrityError, match="ck_task_case_matches_kind"):
        async with db_session.begin_nested():
            await db_session.flush()


# --- who reads it, and how it is told -------------------------------------------


async def test_only_the_beheerder_gets_the_task(
    db_session, evaluate, as_person, beheerder, create_person
):
    await _report(db_session, _trouble())
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)

    body = (await as_person(beheerder).get("/api/tasks/mine")).json()
    (item,) = [item for item in body["items"] if item["id"] == str(task.id)]
    assert item["case_kind"] == "instance"
    assert item["case_label"] == "Koppelingen"
    assert item["needs_me"] is True
    assert item["closes_by_fact"] is True and item["can_complete"] is False
    counts = (await as_person(beheerder).get("/api/tasks/count")).json()
    assert counts["to_do"] >= 1
    # What the beheerder does on the task is as closed as the task.
    keeper = as_person(beheerder)
    noted = await keeper.post(
        f"/api/tasks/{task.id}/notes", json={"body": "Gebeld met Voorbeeldgilde."}
    )
    assert noted.status_code == 201, noted.text
    assigned = await keeper.patch(
        f"/api/tasks/{task.id}", json={"assignee_person_id": str(beheerder.id)}
    )
    assert assigned.status_code == 200, assigned.text
    events = (await keeper.get("/api/events", params={"limit": 200})).json()
    assert str(task.id) in str(events)

    for functions in (["planner"], ["lezer"], ["aanvrager"], []):
        person = await create_person(
            f"{'-'.join(functions) or 'niemand'}@example.org", functions=functions
        )
        client = as_person(person)
        mine = (await client.get("/api/tasks/mine")).json()
        assert str(task.id) not in str(mine), functions
        board = (await client.get("/api/tasks")).json()
        assert str(task.id) not in str(board), functions
        response = await client.get(f"/api/tasks/{task.id}")
        assert response.status_code == 404, functions
        assert "Voorbeeldgilde" not in response.text
        for params in ({"limit": 200}, {"subject_kind": "task"}):
            seen = (await client.get("/api/events", params=params)).json()
            assert str(task.id) not in str(seen), (functions, params)
            assert "Gebeld met Voorbeeldgilde" not in str(seen), functions


async def test_the_beheerder_is_told_why_and_until_when(
    db_session, evaluate, as_person, beheerder
):
    await _report(db_session, _trouble())
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    item = (await as_person(beheerder).get(f"/api/tasks/{task.id}")).json()
    assert item["headline"] == "Kijk waarom berichten aan Voorbeeldgilde niet aankomen"
    assert item["why"] == (
        "Sinds 6 okt 2026 komen 2 berichten aan Voorbeeldgilde niet aan: de "
        "ontvanger kent deze instantie niet. Grip probeert ze tot 13 okt 2026."
    )
    assert item["action_text"] == "Test de verbinding"
    # The peer has no page of its own besides its address on Koppelingen.
    assert item["work_href"] == f"/beheer/koppelingen/{GILDE}"
    assert item["step_href"] == f"/beheer/koppelingen/{GILDE}"
    # Never what the receiver answered: only words grip has for the reason.
    assert "403" not in str(item)


async def test_a_message_given_up_asks_to_send_it_again(
    db_session, evaluate, as_person, beheerder
):
    await _report(
        db_session,
        _trouble(message_count=1, final=True, reason="timeout", retry_until=None),
    )
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    item = (await as_person(beheerder).get(f"/api/tasks/{task.id}")).json()
    assert item["headline"] == "Verstuur berichten aan Voorbeeldgilde opnieuw"
    assert item["action_text"] == "Opnieuw versturen"
    assert item["why"] == (
        "Sinds 6 okt 2026 komt 1 bericht aan Voorbeeldgilde niet aan: de "
        "ontvanger antwoordt niet op tijd. Grip probeert het niet meer vanzelf."
    )


async def test_a_refused_message_does_not_ask_to_send_it_again(
    db_session, evaluate, as_person, beheerder
):
    await _report(
        db_session,
        _trouble(message_count=3, final=True, reason="invalid"),
    )
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    item = (await as_person(beheerder).get(f"/api/tasks/{task.id}")).json()
    assert item["headline"] == "Kijk welk bericht Voorbeeldgilde weigert"
    assert item["action_text"] == "Niet meer versturen"
    assert item["why"] == (
        "Sinds 6 okt 2026 komen 3 berichten aan Voorbeeldgilde niet aan: de "
        "ontvanger weigert wat grip stuurt, omdat het niet klopt. Een of meer "
        "ervan probeert grip niet meer vanzelf, de rest tot 13 okt 2026."
    )


async def test_opening_the_task_shows_it_closed_once_everything_arrived(
    db_session, evaluate, as_person, beheerder
):
    await _report(db_session, _trouble())
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    await _report(db_session)
    item = (await as_person(beheerder).get(f"/api/tasks/{task.id}")).json()
    assert item["status"] == "done"
    assert item["headline"] == "Kijk waarom berichten aan Voorbeeldgilde niet aankomen"


async def test_start_leads_the_beheerder_to_the_peer(
    db_session, evaluate, as_person, beheerder
):
    await _report(db_session, _trouble())
    await evaluate()
    (task,) = await tasks(db_session, key=KEY)
    response = await as_person(beheerder).get("/api/start")
    assert response.status_code == 200, response.text
    groups = response.json()["to_do"]["groups"]
    (group,) = [group for group in groups if group["task_id"] == str(task.id)]
    assert (group["case_kind"], group["case_label"]) == ("instance", "Koppelingen")
    assert group["href"] == f"/beheer/koppelingen/{GILDE}"
