"""The outbox: queueing, sending through the outway, retry and giving up."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from grip.federation.models import (
    OUTBOX_DEAD,
    OUTBOX_PENDING,
    OUTBOX_REJECTED,
    OUTBOX_SENT,
    FederationOutbox,
)
from grip.federation.outbox import (
    OutboundMessageConflictError,
    OutboundMessageInvalidError,
    backoff_seconds,
    enqueue,
    send_due,
)

from .conftest import CLIENT_BASE, CLIENT_PEER_ID, example, t

QUOTE_ID = "9d3b6c0e-2f41-4c8a-b0d2-6a1f5e7c8b90"
RECEIPT = {
    "message_id": QUOTE_ID,
    "received_at": "2026-06-01T10:00:01+02:00",
    "outcome": "accepted",
}


@pytest.fixture
async def client_peer(make_peer):
    return await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)


async def _due(db_session, row) -> None:
    """Make a row due again, as if the backoff had passed."""
    row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()


# --- queueing --------------------------------------------------------------


async def test_enqueue_stores_method_and_path_from_the_contract(
    db_session, client_peer
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    assert (row.method, row.path, row.service) == (
        "POST",
        "/v1/offertes",
        "grip-opdrachtverkeer",
    )
    assert (row.status, row.attempts) == (OUTBOX_PENDING, 0)

    acceptance = await enqueue(
        db_session,
        client_peer,
        "sendAcceptance",
        example("acceptance"),
        quoteId=QUOTE_ID,
    )
    assert acceptance.path == f"/v1/offertes/{QUOTE_ID}/akkoorden"
    report = await enqueue(
        db_session,
        client_peer,
        "sendFinalReport",
        example("final-report"),
        assignmentId="3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60",
    )
    assert report.method == "PUT"


@pytest.mark.parametrize("name", ["quote.ongeldige-hash", "quote.zonder-regels"])
async def test_invalid_message_never_enters_the_outbox(db_session, client_peer, name):
    with pytest.raises(OutboundMessageInvalidError) as raised:
        await enqueue(db_session, client_peer, "sendQuote", example(name, "invalid"))
    assert raised.value.errors
    assert (await db_session.execute(select(FederationOutbox))).first() is None


async def test_pull_operation_cannot_be_queued(db_session, client_peer):
    with pytest.raises(ValueError):
        await enqueue(db_session, client_peer, "getProgress", {})


async def test_queueing_twice_gives_the_same_row(db_session, client_peer):
    first = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    second = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    assert first.id == second.id
    changed = example("quote")
    changed[t("issued_at")] = "2026-06-02T10:00:00+02:00"
    with pytest.raises(OutboundMessageConflictError):
        await enqueue(db_session, client_peer, "sendQuote", changed)


# --- sending ---------------------------------------------------------------


async def test_message_goes_through_the_outway_with_the_grant_hash(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(201, json=RECEIPT)

    stats = await send_due(db_session, outway, fed_settings)

    assert (stats.sent, stats.total) == (1, 1)
    (request,) = fake_outway.requests
    assert request.method == "POST"
    assert str(request.url) == "http://outway.test/v1/offertes"
    assert (
        request.headers["Fsc-Grant-Hash"]
        == client_peer.grant_hashes["grip-opdrachtverkeer"]
    )
    assert "Fsc-Authorization" not in request.headers, "the outway sets that header"
    assert json.loads(request.content) == example("quote")
    assert row.status == OUTBOX_SENT and row.sent_at is not None
    assert (row.attempts, row.last_status_code, row.last_error) == (1, 201, None)


async def test_duplicate_answer_also_counts_as_sent(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(
        200, json={**RECEIPT, "outcome": "duplicate"}
    )
    await send_due(db_session, outway, fed_settings)
    assert row.status == OUTBOX_SENT


async def test_sent_message_is_not_sent_again(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(201, json=RECEIPT)
    await send_due(db_session, outway, fed_settings)
    stats = await send_due(db_session, outway, fed_settings)
    assert stats.total == 0 and len(fake_outway.requests) == 1


@pytest.mark.parametrize("status", [500, 502, 503, 429, 401])
async def test_temporary_failure_is_retried_later(
    db_session, client_peer, fake_outway, outway, fed_settings, status
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(status, text="later")
    before = datetime.now(UTC)

    stats = await send_due(db_session, outway, fed_settings)

    assert stats.retried == 1
    assert (row.status, row.attempts, row.last_status_code) == (
        OUTBOX_PENDING,
        1,
        status,
    )
    assert f"HTTP {status}" in row.last_error
    assert row.next_attempt_at >= before + timedelta(seconds=backoff_seconds(1) - 1)
    # Not due yet: nothing is sent.
    assert (await send_due(db_session, outway, fed_settings)).total == 0
    assert len(fake_outway.requests) == 1

    # Due again and the receiver is back: delivered.
    await _due(db_session, row)
    fake_outway.handler = lambda _request: httpx.Response(201, json=RECEIPT)
    await send_due(db_session, outway, fed_settings)
    assert (row.status, row.attempts, row.last_error) == (OUTBOX_SENT, 2, None)


async def test_network_error_is_retried(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))

    def unreachable(request):
        raise httpx.ConnectError("outway unreachable", request=request)

    fake_outway.handler = unreachable
    stats = await send_due(db_session, outway, fed_settings)
    assert stats.retried == 1
    assert row.status == OUTBOX_PENDING and "ConnectError" in row.last_error
    assert row.last_status_code is None


@pytest.mark.parametrize("status", [400, 403, 404, 409])
async def test_refusal_by_the_receiver_is_final(
    db_session, client_peer, fake_outway, outway, fed_settings, status
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(
        status, json={"title": "Geweigerd", "status": status, "detail": "nee"}
    )
    stats = await send_due(db_session, outway, fed_settings)
    assert stats.rejected == 1
    assert (row.status, row.last_status_code) == (OUTBOX_REJECTED, status)
    assert "Geweigerd" in row.last_error
    await _due(db_session, row)
    assert (await send_due(db_session, outway, fed_settings)).total == 0


async def test_gives_up_after_the_maximum_number_of_attempts(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    assert fed_settings.FEDERATION_MAX_ATTEMPTS == 3
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(503)
    outcomes = []
    for _ in range(4):
        await _due(db_session, row)
        stats = await send_due(db_session, outway, fed_settings)
        outcomes.append((stats.retried, stats.dead, row.status, row.attempts))
    assert outcomes == [
        (1, 0, OUTBOX_PENDING, 1),
        (1, 0, OUTBOX_PENDING, 2),
        (0, 1, OUTBOX_DEAD, 3),
        (0, 0, OUTBOX_DEAD, 3),
    ]
    assert len(fake_outway.requests) == 3


async def test_missing_grant_is_a_configuration_error_that_is_retried(
    db_session, make_peer, fake_outway, outway, fed_settings
):
    peer = await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, grant_hashes={})
    row = await enqueue(db_session, peer, "sendQuote", example("quote"))
    await send_due(db_session, outway, fed_settings)
    assert row.status == OUTBOX_PENDING and "configuration" in row.last_error
    assert fake_outway.requests == []


async def test_without_outway_url_nothing_leaves(
    db_session, client_peer, fake_outway, fed_settings
):
    settings = fed_settings.model_copy(update={"OUTWAY_URL": ""})
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    await send_due(db_session, fake_outway.client(settings), settings)
    assert row.status == OUTBOX_PENDING and "OUTWAY_URL" in row.last_error
    assert fake_outway.requests == []


async def test_one_failing_peer_does_not_hold_up_another(
    db_session, client_peer, make_peer, fake_outway, outway, fed_settings
):
    other = await make_peer()
    failing = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    working = await enqueue(db_session, other, "sendVacancy", example("vacancy"))

    def handler(request):
        if request.url.path == "/v1/offertes":
            return httpx.Response(503)
        return httpx.Response(201, json=RECEIPT)

    fake_outway.handler = handler
    stats = await send_due(db_session, outway, fed_settings)
    assert (stats.sent, stats.retried) == (1, 1)
    assert (failing.status, working.status) == (OUTBOX_PENDING, OUTBOX_SENT)


def test_backoff_doubles_and_is_capped():
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]
    assert backoff_seconds(20) == 3600
