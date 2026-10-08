"""From a domain event to a queued message for the right peer."""

import pytest
from sqlalchemy import select

from grip.federation import events
from grip.federation.models import PEER_ROLE_CORPUS, PEER_ROLE_PARENT, FederationOutbox
from grip.federation.outbox import OutboundMessageInvalidError
from grip.federation.registry import register_message_builder
from grip.services import events as domain_events

from .conftest import CLIENT_BASE, CLIENT_PEER_ID, example

QUOTE_ID = "9d3b6c0e-2f41-4c8a-b0d2-6a1f5e7c8b90"


def _builder(built):
    async def build(db, payload):
        return built

    return build


async def _outbox(db_session):
    return (await db_session.execute(select(FederationOutbox))).scalars().all()


async def test_quote_issued_goes_to_the_client_instance(db_session, make_peer):
    client = await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    await make_peer()
    register_message_builder("quote.issued", _builder({"message": example("quote")}))

    rows = await events.dispatch(db_session, "quote.issued", {"quote_id": QUOTE_ID})

    (row,) = rows
    assert (row.peer_id, row.operation, row.path) == (
        client.id,
        "sendQuote",
        "/v1/quotes",
    )
    assert row.payload == example("quote")


async def test_builder_receives_the_domain_payload(db_session, make_peer):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    seen = []

    async def build(db, payload):
        seen.append(payload)
        return {"message": example("quote")}

    register_message_builder("quote.issued", build)
    await events.dispatch(db_session, "quote.issued", {"quote_id": QUOTE_ID})
    assert seen == [{"quote_id": QUOTE_ID}]


async def test_request_goes_to_the_contractor_instance(db_session, make_peer):
    contractor = await make_peer()
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    register_message_builder(
        "assignment_request.created",
        _builder({"message": example("assignment-request")}),
    )
    (row,) = await events.dispatch(db_session, "assignment_request.created", {})
    assert (row.peer_id, row.operation) == (contractor.id, "sendAssignmentRequest")


@pytest.mark.parametrize(
    "event,name,operation,path",
    [
        (
            "quote.accepted",
            "acceptance",
            "sendAcceptance",
            f"/v1/quotes/{QUOTE_ID}/acceptances",
        ),
        (
            "quote.rejected",
            "rejection",
            "sendRejection",
            f"/v1/quotes/{QUOTE_ID}/rejections",
        ),
        (
            "final_report.issued",
            "final-report",
            "sendFinalReport",
            "/v1/assignments/3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60/final-report",
        ),
    ],
)
async def test_messages_that_need_an_explicit_recipient(
    db_session, make_peer, event, name, operation, path
):
    contractor = await make_peer()
    recipient = {"tooi_uri": "x", "name": "x", "instance_uri": contractor.base_uri}
    register_message_builder(
        event, _builder({"message": example(name), "recipient": recipient})
    )
    (row,) = await events.dispatch(db_session, event, {})
    assert (row.peer_id, row.operation, row.path) == (contractor.id, operation, path)


async def test_without_recipient_an_acceptance_is_not_sent(db_session, make_peer):
    await make_peer()
    register_message_builder(
        "quote.accepted", _builder({"message": example("acceptance.pdf")})
    )
    assert await events.dispatch(db_session, "quote.accepted", {}) == []


async def test_counterpart_without_grip_gets_nothing(db_session, make_peer):
    # Only the contractor runs an instance; the client of the quote does not.
    await make_peer()
    register_message_builder("quote.issued", _builder({"message": example("quote")}))
    assert await events.dispatch(db_session, "quote.issued", {}) == []
    assert await _outbox(db_session) == []


async def test_builder_returning_none_means_nothing_to_send(db_session, make_peer):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    register_message_builder("quote.issued", _builder(None))
    assert await events.dispatch(db_session, "quote.issued", {}) == []


async def test_without_builder_an_event_leads_to_no_message(db_session, make_peer):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    assert await events.dispatch(db_session, "quote.issued", {}) == []
    assert await events.dispatch(db_session, "assignment.status_changed", {}) == []


async def test_recipient_by_tooi_uri_only_when_unambiguous(db_session, make_peer):
    tooi = "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000"
    first = await make_peer(
        CLIENT_PEER_ID, base_uri=CLIENT_BASE, organisation_tooi_uri=tooi
    )
    quote = example("quote")
    del quote["client"]["instance_uri"]
    register_message_builder("quote.issued", _builder({"message": quote}))
    (row,) = await events.dispatch(db_session, "quote.issued", {})
    assert row.peer_id == first.id

    # A second instance of the same organisation: no longer clear who is meant.
    await make_peer(
        "00000000000000000005",
        base_uri="https://grip.directie.example",
        organisation_tooi_uri=tooi,
    )
    other = {**quote, "id": "9d3b6c0e-2f41-4c8a-b0d2-6a1f5e7c8b91"}
    register_message_builder("quote.issued", _builder({"message": other}))
    assert await events.dispatch(db_session, "quote.issued", {}) == []


async def test_vacancy_goes_to_every_instance_peer_but_not_to_a_corpus(
    db_session, make_peer
):
    one = await make_peer()
    two = await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, role=PEER_ROLE_PARENT)
    await make_peer(
        "00000000000000000007", base_uri="https://c.example", role=PEER_ROLE_CORPUS
    )
    await make_peer(
        "00000000000000000008", base_uri="https://uit.example", is_active=False
    )
    register_message_builder(
        "vacancy.published", _builder({"message": example("vacancy")})
    )
    rows = await events.dispatch(db_session, "vacancy.published", {})
    assert {row.peer_id for row in rows} == {one.id, two.id}
    assert {row.operation for row in rows} == {"sendVacancy"}


async def test_vacancy_to_named_recipients_only(db_session, make_peer):
    await make_peer()
    two = await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    recipients = [
        {"tooi_uri": "x", "name": "x", "instance_uri": CLIENT_BASE},
        {"tooi_uri": "y", "name": "y", "instance_uri": "https://geen-grip.example"},
    ]
    register_message_builder(
        "vacancy.published",
        _builder({"message": example("vacancy"), "recipients": recipients}),
    )
    rows = await events.dispatch(db_session, "vacancy.published", {})
    assert [row.peer_id for row in rows] == [two.id]


async def test_message_outside_the_contract_aborts_the_domain_change(
    db_session, make_peer
):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    broken = example("quote")
    broken["snapshot_hash"] = "geen hash"
    register_message_builder("quote.issued", _builder({"message": broken}))
    with pytest.raises(OutboundMessageInvalidError):
        await events.dispatch(db_session, "quote.issued", {})


async def test_handlers_subscribe_to_the_domain_events(db_session, make_peer):
    client = await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    domain_events.clear_handlers()
    try:
        subscribed = events.register_event_handlers()
        assert set(subscribed) <= set(events.EVENT_HANDLERS)
        assert {"quote.issued", "quote.accepted", "assignment_request.created"} <= set(
            subscribed
        )
        # Registering twice must not send a message twice.
        events.register_event_handlers()

        register_message_builder(
            "quote.issued", _builder({"message": example("quote")})
        )
        await domain_events.emit(
            db_session, domain_events.QUOTE_ISSUED, {"quote_id": QUOTE_ID}
        )
        (row,) = await _outbox(db_session)
        assert row.peer_id == client.id
    finally:
        domain_events.clear_handlers()
