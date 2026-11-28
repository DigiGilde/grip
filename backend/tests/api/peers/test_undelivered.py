"""Messages that do not arrive, on Beheer > Koppelingen (ADR 0061)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from grip.access import unclassified_fields
from grip.core.auth import DEV_PERSON_COOKIE
from grip.federation import registry, undelivered
from grip.federation.bridge import deliveries
from grip.federation.models import (
    FAILURE_CONFLICT,
    FAILURE_UNKNOWN_SENDER,
    OUTBOX_DEAD,
    OUTBOX_PENDING,
    OUTBOX_REJECTED,
    OUTBOX_SENT,
    FederationOutbox,
    Peer,
)
from grip.federation.outbox import enqueue
from grip.models.audit_log import AuditLog
from grip.models.delivery_trouble import DeliveryTrouble
from grip.schema.peers import PeerOut, UndeliveredListOut, UndeliveredMessageOut
from grip.services import events as domain_events
from grip.tasks import engine
from tests.federation.conftest import example

# What a receiver answered: it must never reach anyone.
ANSWER = "GEHEIM-ANTWOORD-VAN-DE-ONTVANGER"
SINCE = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean():
    registry.clear_registries()
    domain_events.clear_handlers()
    yield
    registry.clear_registries()
    domain_events.clear_handlers()


@pytest.fixture
def act_as(client):
    def _as(person):
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))

    return _as


@pytest.fixture
async def beheerder(create_person):
    return await create_person("beheerder@example.org", functions=["beheerder"])


async def _peer(db_session, peer_id: str, name: str) -> Peer:
    peer = Peer(
        peer_id=peer_id,
        name=name,
        base_uri=f"https://grip.{peer_id}.example",
        role="counterpart",
        grant_hashes={"grip-opdrachtverkeer": f"$1$4${peer_id}"},
    )
    db_session.add(peer)
    await db_session.flush()
    return peer


async def _message(db_session, peer, operation, payload, **state) -> FederationOutbox:
    row = await enqueue(db_session, peer, operation, payload)
    for name, value in state.items():
        setattr(row, name, value)
    await db_session.flush()
    return row


@pytest.fixture
async def gilde(db_session):
    """A peer with a final message, one that grip still tries, and two that
    do not count: one failed only once, one arrived."""
    peer = await _peer(db_session, "00000000000000000020", "Voorbeeldgilde")
    refused = await _message(
        db_session,
        peer,
        "sendQuote",
        example("quote"),
        status=OUTBOX_REJECTED,
        attempts=1,
        failure=FAILURE_CONFLICT,
        failing_since=SINCE,
        last_error=f"HTTP 409: {ANSWER}",
        last_status_code=409,
    )
    tried = await _message(
        db_session,
        peer,
        "sendVacancy",
        example("vacancy"),
        attempts=4,
        failure=FAILURE_UNKNOWN_SENDER,
        failing_since=SINCE + timedelta(hours=1),
        retry_until=SINCE + timedelta(days=7),
        last_error=f"HTTP 403: {ANSWER}",
        last_status_code=403,
    )
    vacancy = example("vacancy")
    vacancy["id"] = str(uuid.uuid4())
    await _message(
        db_session,
        peer,
        "sendVacancy",
        vacancy,
        attempts=1,
        failure=FAILURE_UNKNOWN_SENDER,
        retry_until=SINCE + timedelta(days=7),
        last_error=f"HTTP 403: {ANSWER}",
    )
    sent = example("vacancy")
    sent["id"] = str(uuid.uuid4())
    await _message(db_session, peer, "sendVacancy", sent, status=OUTBOX_SENT)
    return peer, refused, tried


async def test_the_beheerder_sees_what_does_not_arrive(
    client, beheerder, act_as, gilde
):
    peer, refused, tried = gilde
    act_as(beheerder)

    (listed,) = (await client.get("/api/peers")).json()["items"]
    assert listed["undelivered"] == 2
    assert (await client.get(f"/api/peers/{peer.id}")).json()["undelivered"] == 2

    response = await client.get(f"/api/peers/{peer.id}/undelivered")
    assert response.status_code == 200, response.text
    first, second = response.json()["items"]
    assert first == {
        "id": str(refused.id),
        "kind": "Offerte",
        "reason": "Wat grip stuurt, botst met wat de ontvanger al heeft",
        "since": "2026-11-27T09:00:00Z",
        "retry_until": None,
        "final": True,
    }
    assert second["id"] == str(tried.id)
    assert (second["kind"], second["final"]) == ("Vacature", False)
    assert second["reason"] == "De ontvanger kent deze instantie niet"
    assert second["retry_until"] == "2026-12-04T09:00:00Z"


async def test_a_peer_without_trouble_lists_nothing(
    client, db_session, beheerder, act_as
):
    peer = await _peer(db_session, "00000000000000000030", "Ander voorbeeld")
    act_as(beheerder)
    assert (await client.get("/api/peers")).json()["items"][0]["undelivered"] == 0
    listed = (await client.get(f"/api/peers/{peer.id}/undelivered")).json()
    assert listed == {"items": []}


async def test_the_beheerder_sends_a_final_message_again(
    client, db_session, beheerder, act_as, gilde
):
    peer, refused, _tried = gilde
    registry.register_delivery_reporter(deliveries.report)
    db_session.add(
        DeliveryTrouble(
            peer_id=peer.id,
            peer_name=peer.name,
            since=SINCE,
            message_count=2,
            final=True,
            reason=FAILURE_CONFLICT,
            retry_until=SINCE + timedelta(days=7),
        )
    )
    await db_session.flush()
    act_as(beheerder)

    response = await client.post(
        f"/api/peers/{peer.id}/undelivered/{refused.id}/resend"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id"], body["final"], body["retry_until"]) == (
        str(refused.id),
        False,
        None,
    )
    await db_session.refresh(refused)
    assert (refused.status, refused.attempts, refused.retry_until) == (
        OUTBOX_PENDING,
        0,
        None,
    )
    # It still does not arrive until it does; nothing is final any more.
    assert refused.failing_since == SINCE
    trouble = await db_session.get(DeliveryTrouble, peer.id)
    assert trouble is not None
    assert (trouble.message_count, trouble.final) == (2, False)

    (audit,) = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.subject_kind == "peer", AuditLog.subject_id == str(peer.id)
            )
        )
    ).all()
    assert audit.actor_person_id == beheerder.id
    assert audit.note == "Opnieuw verstuurd: Offerte"
    assert audit.new_value == {"message_id": str(refused.message_id)}


async def test_only_a_final_message_of_the_peer_is_sent_again(
    client, db_session, beheerder, act_as, gilde
):
    peer, refused, tried = gilde
    other = await _peer(db_session, "00000000000000000030", "Ander voorbeeld")
    act_as(beheerder)
    still = await client.post(f"/api/peers/{peer.id}/undelivered/{tried.id}/resend")
    assert still.status_code == 422
    assert still.json()["detail"] == "Grip probeert dit bericht nog te versturen."
    elsewhere = await client.post(
        f"/api/peers/{other.id}/undelivered/{refused.id}/resend"
    )
    assert elsewhere.status_code == 404
    unknown = await client.post(
        f"/api/peers/{peer.id}/undelivered/{uuid.uuid4()}/resend"
    )
    assert unknown.status_code == 404
    refused.status = OUTBOX_SENT
    await db_session.flush()
    arrived = await client.post(f"/api/peers/{peer.id}/undelivered/{refused.id}/resend")
    assert arrived.status_code == 422
    assert arrived.json()["detail"] == "Dit bericht is al aangekomen."


async def test_a_message_given_up_is_sent_again_too(
    client, db_session, beheerder, act_as, gilde
):
    peer, _refused, tried = gilde
    tried.status = OUTBOX_DEAD
    await db_session.flush()
    act_as(beheerder)
    listed = (await client.get(f"/api/peers/{peer.id}/undelivered")).json()["items"]
    assert [item["final"] for item in listed] == [True, True]
    response = await client.post(f"/api/peers/{peer.id}/undelivered/{tried.id}/resend")
    assert response.status_code == 200, response.text
    await db_session.refresh(tried)
    assert tried.status == OUTBOX_PENDING


@pytest.mark.parametrize("functions", [["planner"], ["lezer"], ["aanvrager"], []])
async def test_only_the_beheerder_sees_or_resends_them(
    client, db_session, create_person, act_as, gilde, functions
):
    peer, refused, _tried = gilde
    person = await create_person(
        f"{'-'.join(functions) or 'niemand'}@example.org", functions=functions
    )
    act_as(person)
    for path in ("/api/peers", f"/api/peers/{peer.id}/undelivered"):
        response = await client.get(path)
        assert response.status_code == 403, (functions, path)
        for name in ("undelivered", "reason", "retry_until", "final", "since"):
            assert name not in response.text
        assert ANSWER not in response.text
    refused_again = await client.post(
        f"/api/peers/{peer.id}/undelivered/{refused.id}/resend"
    )
    assert refused_again.status_code == 403
    await db_session.refresh(refused)
    assert refused.status == OUTBOX_REJECTED


async def test_what_the_receiver_answered_reaches_no_one(
    client, db_session, beheerder, act_as, gilde
):
    peer, refused, _tried = gilde
    act_as(beheerder)
    for path in (
        "/api/peers",
        f"/api/peers/{peer.id}",
        f"/api/peers/{peer.id}/undelivered",
    ):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert ANSWER not in response.text and "last_error" not in response.text
    resent = await client.post(f"/api/peers/{peer.id}/undelivered/{refused.id}/resend")
    assert resent.status_code == 200
    assert ANSWER not in resent.text and "last_error" not in resent.text

    # Nor through the task it gives the beheerder, or the events around it.
    registry.register_delivery_reporter(deliveries.report)
    await undelivered.report(db_session)
    await engine.evaluate_instance(db_session)
    await db_session.flush()
    trouble = await db_session.get(DeliveryTrouble, peer.id)
    assert trouble is not None and trouble.message_count == 2
    mine = await client.get("/api/tasks/mine")
    assert "Voorbeeldgilde" in mine.text
    for path, params in (
        ("/api/tasks/mine", {}),
        ("/api/tasks", {}),
        ("/api/events", {"limit": 200}),
        ("/api/events", {"subject_kind": "delivery_trouble"}),
        ("/api/events", {"subject_kind": "peer"}),
    ):
        response = await client.get(path, params=params)
        assert response.status_code == 200, (path, params)
        assert ANSWER not in response.text and "last_error" not in response.text
    (task_id,) = [
        item["id"]
        for item in (await client.get("/api/tasks/mine")).json()["items"]
        if item["case_kind"] == "instance"
    ]
    response = await client.get(f"/api/tasks/{task_id}")
    assert ANSWER not in response.text and "last_error" not in response.text


async def test_the_beheerder_sets_a_final_message_aside(
    client, db_session, beheerder, act_as, gilde
):
    peer, refused, tried = gilde
    act_as(beheerder)
    still = await client.post(f"/api/peers/{peer.id}/undelivered/{tried.id}/set-aside")
    assert still.status_code == 422
    response = await client.post(
        f"/api/peers/{peer.id}/undelivered/{refused.id}/set-aside"
    )
    assert response.status_code == 200, response.text
    assert ANSWER not in response.text
    await db_session.refresh(refused)
    assert refused.status == OUTBOX_REJECTED and refused.set_aside_at is not None
    listed = (await client.get(f"/api/peers/{peer.id}/undelivered")).json()["items"]
    assert [item["id"] for item in listed] == [str(tried.id)]
    assert (await client.get(f"/api/peers/{peer.id}")).json()["undelivered"] == 1

    (audit,) = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.subject_kind == "peer", AuditLog.subject_id == str(peer.id)
            )
        )
    ).all()
    assert audit.actor_person_id == beheerder.id
    assert audit.note == "Niet meer verstuurd: Offerte"


async def test_only_the_beheerder_sets_one_aside(
    client, db_session, create_person, act_as, gilde
):
    peer, refused, _tried = gilde
    act_as(await create_person("planner@example.org", functions=["planner"]))
    response = await client.post(
        f"/api/peers/{peer.id}/undelivered/{refused.id}/set-aside"
    )
    assert response.status_code == 403
    await db_session.refresh(refused)
    assert refused.set_aside_at is None


def test_every_field_has_one_data_class():
    for model in (PeerOut, UndeliveredMessageOut, UndeliveredListOut):
        assert unclassified_fields(model) == [], model.__name__
