"""Catching up on messages that were stored before a handler existed."""

from sqlalchemy import select

from grip.federation.inbox import process_pending
from grip.federation.models import FederationInbox
from grip.federation.problems import FederationProblem
from grip.federation.registry import register_inbound_handler

from .conftest import CONTRACTOR_PEER_ID, as_peer, example


async def test_stored_message_is_processed_once_a_handler_exists(
    fed_client, db_session, make_peer
):
    peer = await make_peer()
    await fed_client.post(
        "/v1/quotes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert await process_pending(db_session) == 0, "no handler yet"

    seen = []

    async def handler(db, caller, message):
        seen.append((caller.id, message.operation, message.payload["id"]))
        return {"ok": True}

    register_inbound_handler("sendQuote", handler)
    assert await process_pending(db_session) == 1
    assert seen == [(peer.id, "sendQuote", example("quote")["id"])]
    row = (await db_session.execute(select(FederationInbox))).scalar_one()
    assert row.processed_at is not None and row.result == {"ok": True}
    assert await process_pending(db_session) == 0, "not processed twice"


async def test_refusal_afterwards_is_recorded_with_the_message(
    fed_client, db_session, make_peer
):
    await make_peer()
    await fed_client.post(
        "/v1/quotes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )

    async def handler(db, caller, message):
        raise FederationProblem(409, "Past niet", "Onbekende opdracht.")

    register_inbound_handler("sendQuote", handler)
    assert await process_pending(db_session) == 1
    row = (await db_session.execute(select(FederationInbox))).scalar_one()
    assert row.processed_at is not None
    assert row.result["refused"]["status"] == 409
