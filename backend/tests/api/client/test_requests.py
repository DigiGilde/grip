"""Asking a contractor for a quote, and the lists on both sides."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from grip.federation.bridge.organisations import from_reference
from grip.federation.events import register_event_handlers
from grip.federation.models import FederationOutbox, Peer
from grip.models.assignment import Assignment, AssignmentRole
from grip.services import assignments

from .conftest import CONTRACTOR, NODE_URI, OTHER_NODE_URI


def _request(cast, **overrides):
    body = {
        "contractor_peer_id": str(cast.contractor_peer.id),
        "name": "Opdracht Alfa",
        "description": "Fictieve aanvraag.",
        "start_date": "2026-07-01",
        "end_date": "2027-06-30",
        "context_uris": [NODE_URI, OTHER_NODE_URI],
    }
    body.update(overrides)
    return body


async def test_options_tell_who_may_ask_and_whom(client, cast, act_as):
    act_as(cast.requester)
    options = (await client.get("/api/client/options")).json()
    assert options["may_request"] is True and options["problem"] is None
    (contractor,) = options["contractors"]
    assert contractor["name"] == "Voorbeeldgilde" and contractor["reachable"] is True
    assert contractor["peer_id"] == str(cast.contractor_peer.id)

    act_as(cast.beheerder)
    assert (await client.get("/api/client/options")).json()["may_request"] is True

    # Someone without the function learns nothing about who is connected.
    for person in (cast.planner, cast.lezer, cast.signer, cast.outsider):
        act_as(person)
        options = (await client.get("/api/client/options")).json()
        assert options["may_request"] is False and options["problem"] is None
        assert options.get("contractors", []) == []


async def test_options_say_why_a_request_would_not_be_sent(
    client, cast, act_as, federated, monkeypatch
):
    act_as(cast.requester)
    monkeypatch.setattr(federated, "FEDERATION_OUTBOUND_ENABLED", False)
    assert "staat uit" in (await client.get("/api/client/options")).json()["problem"]
    monkeypatch.setattr(federated, "FEDERATION_OUTBOUND_ENABLED", True)
    monkeypatch.setattr(federated, "INSTANCE_TOOI_URI", "")
    assert "TOOI-URI" in (await client.get("/api/client/options")).json()["problem"]


async def test_requester_asks_for_a_quote_and_it_is_queued(
    client, db_session, cast, act_as
):
    register_event_handlers()
    act_as(cast.requester)
    response = await client.post("/api/client/requests", json=_request(cast))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "requested" and body["name"] == "Opdracht Alfa"
    assert body["contractor_name"] == "Voorbeeldgilde"
    # Nodes of several corpora on one request, kept as bare URIs.
    assert body["context_refs"] == [NODE_URI, OTHER_NODE_URI]
    assert body["request_delivery"]["status"] == "pending"
    assert body["contractor_reachable"] is True

    assignment = await db_session.get(Assignment, body["id"])
    # Asking a contractor is an exchange: shared with its instance from then on.
    assert assignment is not None and assignment.shared_with_instance_uri
    assert assignment.start_date == date(2026, 7, 1)
    # This instance is the client, and the requester owns the assignment here.
    role = await db_session.scalar(
        select(AssignmentRole).where(AssignmentRole.assignment_id == assignment.id)
    )
    assert role.person_id == cast.requester.id and role.role == "owner"
    (queued,) = (await db_session.execute(select(FederationOutbox))).scalars().all()
    assert queued.operation == "sendAssignmentRequest"
    assert queued.payload["opdracht_uri"] == assignment.uri
    assert queued.payload["context_uris"] == [NODE_URI, OTHER_NODE_URI]
    assert queued.payload["opdrachtgever"]["naam"]


async def test_a_request_without_context_is_fine(client, cast, act_as):
    act_as(cast.beheerder)
    response = await client.post(
        "/api/client/requests",
        json=_request(cast, context_uris=[], description=None),
    )
    assert response.status_code == 201, response.text
    assert response.json()["context_refs"] == []


async def test_who_may_not_ask(client, db_session, cast, act_as):
    for person in (cast.planner, cast.lezer, cast.signer, cast.outsider):
        act_as(person)
        response = await client.post("/api/client/requests", json=_request(cast))
        assert response.status_code == 403, person.email
    assert (await db_session.execute(select(Assignment))).scalars().all() == []


async def test_a_request_needs_a_connected_contractor(client, db_session, cast, act_as):
    act_as(cast.requester)
    unknown = await client.post(
        "/api/client/requests",
        json=_request(cast, contractor_peer_id="00000000-0000-4000-8000-000000000000"),
    )
    assert unknown.status_code == 422
    # A corpus is not a contractor.
    corpus = await client.post(
        "/api/client/requests",
        json=_request(cast, contractor_peer_id=str(cast.corpus_peer.id)),
    )
    assert corpus.status_code == 422
    bad_uri = await client.post(
        "/api/client/requests", json=_request(cast, context_uris=["geen uri"])
    )
    assert bad_uri.status_code == 422
    backwards = await client.post(
        "/api/client/requests",
        json=_request(cast, start_date="2027-01-01", end_date="2026-01-01"),
    )
    assert backwards.status_code == 422

    peer = await db_session.get(Peer, cast.contractor_peer.id)
    peer.organisation_tooi_uri = ""
    await db_session.flush()
    unnamed = await client.post("/api/client/requests", json=_request(cast))
    assert unnamed.status_code == 422 and "TOOI-URI" in unnamed.text


async def test_client_assignments_are_listed_for_who_may_read_them(
    client, cast, act_as, received
):
    act_as(cast.requester)
    listed = (await client.get("/api/client/assignments")).json()
    assert listed["may_request"] is True
    (row,) = listed["items"]
    assert row["id"] == str(received.assignment.id) and row["status"] == "quoted"
    assert row["latest_quote"]["total_cents"] == received.quote.total_cents
    assert row["context_count"] == 1

    # A planner reads the basics, never the amount.
    act_as(cast.planner)
    (row,) = (await client.get("/api/client/assignments")).json()["items"]
    assert "total_cents" not in row["latest_quote"]
    detail = (
        await client.get(f"/api/client/assignments/{received.assignment.id}")
    ).json()
    assert detail["may_request_usage"] is False
    assert all("total_cents" not in quote for quote in detail["quotes"])

    act_as(cast.outsider)
    assert (await client.get("/api/client/assignments")).json()["items"] == []
    hidden = await client.get(f"/api/client/assignments/{received.assignment.id}")
    assert hidden.status_code == 404


async def test_an_assignment_of_this_instance_as_contractor_is_not_a_client_one(
    client, db_session, cast, act_as
):
    own_work = await assignments.create_assignment(
        db_session, name="Eigen werk", actor=cast.beheerder
    )
    act_as(cast.beheerder)
    assert (await client.get("/api/client/assignments")).json()["items"] == []
    response = await client.get(f"/api/client/assignments/{own_work.id}")
    assert response.status_code == 404


async def test_received_requests_show_what_clients_asked(
    client, db_session, cast, act_as, received
):
    client_org = await from_reference(
        db_session,
        {
            "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre1111",
            "name": "Andere Voorbeelddirectie",
            "instance_uri": "https://grip.anderedirectie.example",
        },
    )
    incoming = await assignments.receive_assignment_request(
        db_session,
        uri="https://grip.anderedirectie.example/id/opdracht/3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60",
        name="Opdracht Beta",
        client_organisation_id=client_org.id,
        description="Fictieve aanvraag van een ander.",
        context_refs=[NODE_URI],
    )
    act_as(cast.planner)
    (row,) = (await client.get("/api/received-requests")).json()["items"]
    # Only what came in: the assignment this instance asked for itself is not here.
    assert row["id"] == str(incoming.id) and row["status"] == "requested"
    assert row["client_name"] == "Andere Voorbeelddirectie"
    assert row["context_count"] == 1 and row["quote_count"] == 0

    act_as(cast.outsider)
    assert (await client.get("/api/received-requests")).json()["items"] == []
    assert CONTRACTOR["name"] not in (await client.get("/api/received-requests")).text
