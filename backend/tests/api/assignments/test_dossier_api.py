"""Closing the dossier of an assignment over the API, and who sees it (ADR 0057)."""

from datetime import timedelta

import pytest

from grip.core import clock
from grip.services import assignments, dossiers, instance_settings

from .conftest import by_id


@pytest.fixture
async def ended(db_session, world):
    for step in ("quoted", "accepted", "in_progress", "completed"):
        await assignments.transition(
            db_session, world.assignment.id, step, actor=world.owner
        )
    return world


def _url(world, action: str = "") -> str:
    base = f"/api/assignments/{world.assignment.id}"
    return f"{base}/dossier/{action}" if action else base


async def test_the_owner_closes_reopens_and_keeps_open(ended, as_person):
    world = ended
    client = as_person(world.owner)
    before = (await client.get(_url(world))).json()
    assert before["dossier_closed_on"] is None
    assert before["permissions"]["close_dossier"] is True
    assert "in_progress" in before["allowed_transitions"]

    closed = await client.post(_url(world, "close"), json={})
    assert closed.status_code == 200
    body = closed.json()
    assert body["dossier_closed_on"] == clock.today().isoformat()
    assert body["dossier_due"] is False
    # A closed dossier takes no status step: none is offered.
    assert body["allowed_transitions"] == []

    reopened = await client.post(_url(world, "reopen"))
    assert reopened.status_code == 200
    assert reopened.json()["dossier_closed_on"] is None

    kept = await client.post(_url(world, "keep-open"))
    assert kept.status_code == 200
    assert kept.json()["dossier_closed_on"] is None


async def test_closing_before_the_last_change_is_refused(ended, as_person):
    client = as_person(ended.owner)
    yesterday = clock.today() - timedelta(days=1)
    before = await client.post(
        _url(ended, "close"), json={"closed_on": yesterday.isoformat()}
    )
    assert before.status_code == 422
    assert "voor de laatste wijziging" in before.json()["detail"]
    today = await client.post(
        _url(ended, "close"), json={"closed_on": clock.today().isoformat()}
    )
    assert today.status_code == 200
    assert today.json()["dossier_closed_on"] == clock.today().isoformat()


async def test_closing_without_a_body_closes_today(ended, as_person):
    response = await as_person(ended.owner).post(_url(ended, "close"))
    assert response.status_code == 200
    assert response.json()["dossier_closed_on"] == clock.today().isoformat()


async def test_a_closed_dossier_offers_no_change(ended, as_person):
    client = as_person(ended.owner)
    before = (await client.get(_url(ended))).json()["permissions"]
    assert before["edit_basic"] and before["edit_financial"]
    closed = (await client.post(_url(ended, "close"))).json()["permissions"]
    for name in ("edit_basic", "edit_financial", "edit_staffing", "manage_roles"):
        assert closed[name] is False, name
    assert closed["read_financial"] is True
    assert closed["close_dossier"] is True


async def test_refusals_say_why(ended, as_person):
    world = ended
    client = as_person(world.owner)
    tomorrow = (clock.today() + timedelta(days=1)).isoformat()
    future = await client.post(_url(world, "close"), json={"closed_on": tomorrow})
    assert future.status_code == 422
    assert (await client.post(_url(world, "reopen"))).status_code == 422

    assert (await client.post(_url(world, "close"), json={})).status_code == 200
    edit = await client.patch(_url(world), json={"name": "Opdracht Anders"})
    assert edit.status_code == 409
    assert edit.json()["code"] == "DossierClosedError"
    assert edit.json()["detail"] == "Het dossier is gesloten. Heropen het eerst."
    step = await client.post(
        f"{_url(world)}/transition", json={"target": "in_progress"}
    )
    assert step.status_code == 409
    line = await client.post(
        f"{_url(world)}/budget-lines",
        json={
            "description": "Hosting",
            "kind": "fixed",
            "amount_cents": 100,
            "year": 2026,
        },
    )
    assert line.status_code == 409


async def test_a_running_assignment_does_not_close(world, as_person):
    response = await as_person(world.owner).post(_url(world, "close"), json={})
    assert response.status_code == 422


async def test_who_may_close(ended, as_person):
    world = ended
    for person in (world.member, world.lezer, world.planner):
        client = as_person(person)
        view = (await client.get(_url(world))).json()
        assert view["permissions"]["close_dossier"] is False
        for action in ("close", "reopen", "keep-open"):
            assert (await client.post(_url(world, action), json={})).status_code == 403
    outsider = as_person(world.outsider)
    for action in ("close", "reopen", "keep-open"):
        assert (await outsider.post(_url(world, action), json={})).status_code == 404
    # The beheerder may, also without a role on the assignment.
    beheerder = as_person(world.beheerder)
    assert (await beheerder.get(_url(world))).json()["permissions"]["close_dossier"]
    assert (await beheerder.post(_url(world, "close"), json={})).status_code == 200


async def test_the_dossier_fields_follow_class_a(db_session, ended, as_person):
    world = ended
    await instance_settings.set_values(
        db_session, {dossiers.PROPOSE_CLOSE_AFTER_DAYS.key: 0}, actor=world.beheerder
    )
    for person in (world.owner, world.member, world.lezer, world.planner):
        client = as_person(person)
        listed = by_id(
            (await client.get("/api/assignments")).json()["items"],
            "id",
            world.assignment.id,
        )
        assert listed["dossier_closed_on"] is None
        assert listed["dossier_due"] is True
        detail = (await client.get(_url(world))).json()
        assert detail["dossier_due"] is True
    outsider = as_person(world.outsider)
    items = (await outsider.get("/api/assignments")).json()["items"]
    assert str(world.assignment.id) not in {item["id"] for item in items}
    assert (await outsider.get(_url(world))).status_code == 404

    closed = (await as_person(world.owner).post(_url(world, "close"), json={})).json()
    assert closed["dossier_due"] is False
    lezer = as_person(world.lezer)
    listed = by_id(
        (await lezer.get("/api/assignments")).json()["items"],
        "id",
        world.assignment.id,
    )
    assert listed["dossier_closed_on"] == clock.today().isoformat()
    assert listed["dossier_due"] is False
