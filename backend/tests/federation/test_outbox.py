"""The outbox: queueing, sending through the outway, retry and giving up."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from grip.core import clock
from grip.federation import registry, undelivered
from grip.federation.models import (
    FAILURE_CONFIGURATION,
    FAILURE_CONFLICT,
    FAILURE_GONE,
    FAILURE_INVALID,
    FAILURE_NO_CONNECTION,
    FAILURE_NOT_FOUND,
    FAILURE_OTHER,
    FAILURE_RECEIVER_ERROR,
    FAILURE_TIMEOUT,
    FAILURE_UNKNOWN_SENDER,
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
from grip.services.errors import DomainValidationError, NotFoundError

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


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (500, FAILURE_RECEIVER_ERROR),
        (502, FAILURE_RECEIVER_ERROR),
        (503, FAILURE_RECEIVER_ERROR),
        (429, FAILURE_OTHER),
        (401, FAILURE_UNKNOWN_SENDER),
        # The receiver does not know this instance yet; it may at the next try.
        (403, FAILURE_UNKNOWN_SENDER),
        (404, FAILURE_NOT_FOUND),
        (302, FAILURE_OTHER),
    ],
)
async def test_temporary_failure_is_retried_later(
    db_session, client_peer, fake_outway, outway, fed_settings, status, failure
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
    assert row.failure == failure
    assert row.next_attempt_at >= before + timedelta(seconds=backoff_seconds(1) - 1)
    assert row.retry_until >= before + timedelta(days=7)
    # One failure is a blip: the message does not count as not arriving yet.
    assert row.failing_since is None
    # Not due yet: nothing is sent.
    assert (await send_due(db_session, outway, fed_settings)).total == 0
    assert len(fake_outway.requests) == 1

    # Due again and the receiver is back: delivered.
    await _due(db_session, row)
    fake_outway.handler = lambda _request: httpx.Response(201, json=RECEIPT)
    await send_due(db_session, outway, fed_settings)
    assert (row.status, row.attempts, row.last_error) == (OUTBOX_SENT, 2, None)
    assert (row.failure, row.failing_since, row.retry_until) == (None, None, None)


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
    assert row.failure == FAILURE_NO_CONNECTION


async def test_no_answer_in_time_is_retried(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))

    def silent(request):
        raise httpx.ReadTimeout("no answer", request=request)

    fake_outway.handler = silent
    stats = await send_due(db_session, outway, fed_settings)
    assert stats.retried == 1
    assert (row.status, row.failure) == (OUTBOX_PENDING, FAILURE_TIMEOUT)


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (400, FAILURE_INVALID),
        (409, FAILURE_CONFLICT),
        (410, FAILURE_GONE),
        (422, FAILURE_INVALID),
    ],
)
async def test_refusal_by_the_receiver_is_final(
    db_session, client_peer, fake_outway, outway, fed_settings, status, failure
):
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(
        status, json={"title": "Geweigerd", "status": status, "detail": "nee"}
    )
    stats = await send_due(db_session, outway, fed_settings)
    assert stats.rejected == 1
    assert (row.status, row.last_status_code) == (OUTBOX_REJECTED, status)
    assert "Geweigerd" in row.last_error
    assert row.failure == failure
    # Final at once: it counts as not arriving from this answer on.
    assert row.failing_since is not None
    await _due(db_session, row)
    assert (await send_due(db_session, outway, fed_settings)).total == 0


T0 = datetime(2026, 11, 28, 9, 0, tzinfo=UTC)


async def _attempt_at(moment, db_session, outway, settings):
    with clock.at(moment):
        return await send_due(db_session, outway, settings)


async def test_a_message_counts_as_not_arriving_from_its_third_failure(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    with clock.at(T0):
        row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(503)
    seen = []
    for moment in (T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=3)):
        await _attempt_at(moment, db_session, outway, fed_settings)
        seen.append((row.attempts, row.failing_since))
    assert seen == [(1, None), (2, None), (3, T0 + timedelta(minutes=3))]


async def test_tries_again_for_seven_days_and_then_gives_up(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    assert fed_settings.FEDERATION_RETRY_DAYS == 7
    with clock.at(T0):
        row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(403)
    end = T0 + timedelta(days=7)

    stats = await _attempt_at(T0, db_session, outway, fed_settings)
    assert (stats.retried, row.retry_until) == (1, end)
    assert row.next_attempt_at == T0 + timedelta(seconds=30)
    early = T0 + timedelta(seconds=29)
    assert (await _attempt_at(early, db_session, outway, fed_settings)).total == 0

    # Days later the pause is at its longest, and never past the window.
    row.attempts = 20
    late = end - timedelta(hours=1)
    stats = await _attempt_at(late, db_session, outway, fed_settings)
    assert (stats.retried, row.status) == (1, OUTBOX_PENDING)
    assert row.next_attempt_at == end
    assert row.retry_until == end, "the window counts from the first failure"

    # The last attempt falls on the end of the window; then it is final.
    stats = await _attempt_at(end, db_session, outway, fed_settings)
    assert (stats.dead, row.status, row.failure) == (
        1,
        OUTBOX_DEAD,
        FAILURE_UNKNOWN_SENDER,
    )
    assert row.failing_since is not None
    later = end + timedelta(days=1)
    assert (await _attempt_at(later, db_session, outway, fed_settings)).total == 0
    assert len(fake_outway.requests) == 3


async def test_a_window_of_no_days_gives_up_at_the_first_failure(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    settings = fed_settings.model_copy(update={"FEDERATION_RETRY_DAYS": 0})
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(503)
    stats = await send_due(db_session, outway, settings)
    assert (stats.dead, row.status) == (1, OUTBOX_DEAD)
    assert row.failing_since is not None


async def test_missing_grant_is_a_configuration_error_that_is_retried(
    db_session, make_peer, fake_outway, outway, fed_settings
):
    peer = await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, grant_hashes={})
    row = await enqueue(db_session, peer, "sendQuote", example("quote"))
    await send_due(db_session, outway, fed_settings)
    assert row.status == OUTBOX_PENDING and "configuration" in row.last_error
    assert row.failure == FAILURE_CONFIGURATION
    assert fake_outway.requests == []


async def test_without_outway_url_nothing_leaves(
    db_session, client_peer, fake_outway, fed_settings
):
    settings = fed_settings.model_copy(update={"OUTWAY_URL": ""})
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    await send_due(db_session, fake_outway.client(settings), settings)
    assert row.status == OUTBOX_PENDING and "OUTWAY_URL" in row.last_error
    assert row.failure == FAILURE_CONFIGURATION
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


def test_backoff_doubles_and_is_capped_at_four_hours():
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]
    assert backoff_seconds(9) == 7680
    assert backoff_seconds(10) == backoff_seconds(40) == 4 * 3600


# --- sending again and telling the domain -------------------------------------


async def _refused(db_session, peer, fake_outway, outway, fed_settings):
    row = await enqueue(db_session, peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(
        409, json={"title": "Botst", "status": 409, "detail": "Bestaat al"}
    )
    await send_due(db_session, outway, fed_settings)
    assert row.status == OUTBOX_REJECTED
    return row


async def test_a_final_message_is_sent_again_as_the_same_message(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await _refused(db_session, client_peer, fake_outway, outway, fed_settings)
    since = row.failing_since
    heard = []

    async def hook(db, resent, actor):
        heard.append((resent.id, resent.status, actor))
        return True

    registry.register_resend_hook("sendQuote", hook)
    with clock.at(T0):
        again = await undelivered.resend(db_session, client_peer.id, row.id, actor=None)

    # The hook hears it before the row changes, so it can still say no.
    assert again.id == row.id and heard == [(row.id, OUTBOX_REJECTED, None)]
    assert (row.status, row.attempts, row.retry_until) == (OUTBOX_PENDING, 0, None)
    assert row.next_attempt_at == T0
    # Until it arrives it still does not arrive, since the first time.
    assert row.failing_since == since
    assert [r.id for r in await undelivered.of_peer(db_session, client_peer.id)] == [
        row.id
    ]

    fake_outway.handler = lambda _request: httpx.Response(201, json=RECEIPT)
    await send_due(db_session, outway, fed_settings)
    assert row.status == OUTBOX_SENT and row.failing_since is None
    assert json.loads(fake_outway.requests[-1].content) == example("quote")
    assert await undelivered.of_peer(db_session, client_peer.id) == []


async def test_only_a_final_message_of_that_peer_is_sent_again(
    db_session, client_peer, make_peer, fake_outway, outway, fed_settings
):
    other = await make_peer()
    row = await _refused(db_session, client_peer, fake_outway, outway, fed_settings)
    with pytest.raises(NotFoundError):
        await undelivered.resend(db_session, other.id, row.id, actor=None)
    await undelivered.resend(db_session, client_peer.id, row.id, actor=None)
    with pytest.raises(DomainValidationError, match="nog te versturen"):
        await undelivered.resend(db_session, client_peer.id, row.id, actor=None)
    with pytest.raises(DomainValidationError, match="nog te versturen"):
        await undelivered.set_aside(db_session, client_peer.id, row.id, actor=None)
    fake_outway.handler = lambda _request: httpx.Response(201, json=RECEIPT)
    await send_due(db_session, outway, fed_settings)
    with pytest.raises(DomainValidationError, match="al aangekomen"):
        await undelivered.resend(db_session, client_peer.id, row.id, actor=None)


async def test_a_failure_after_sending_again_starts_a_new_window(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await _refused(db_session, client_peer, fake_outway, outway, fed_settings)
    resent_at = T0 + timedelta(days=10)
    with clock.at(resent_at):
        await undelivered.resend(db_session, client_peer.id, row.id, actor=None)
    fake_outway.handler = lambda _request: httpx.Response(503, text="later")
    failed_at = resent_at + timedelta(hours=2)
    await _attempt_at(failed_at, db_session, outway, fed_settings)
    assert (row.status, row.attempts) == (OUTBOX_PENDING, 1)
    assert row.retry_until == failed_at + timedelta(days=7)


async def test_a_message_whose_subject_no_longer_waits_is_not_sent_again(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await _refused(db_session, client_peer, fake_outway, outway, fed_settings)

    async def gone(db, resent, actor):
        return False

    registry.register_resend_hook("sendQuote", gone)
    with pytest.raises(DomainValidationError, match="niet meer op"):
        await undelivered.resend(db_session, client_peer.id, row.id, actor=None)
    assert (row.status, row.set_aside_at) == (OUTBOX_REJECTED, None)
    assert [r.id for r in await undelivered.of_peer(db_session, client_peer.id)] == [
        row.id
    ]


async def test_a_final_message_set_aside_no_longer_counts(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    heard = []

    async def reporter(db, deliveries, peer_ids):
        heard.append(([d.peer_id for d in deliveries], peer_ids))

    registry.register_delivery_reporter(reporter)
    row = await _refused(db_session, client_peer, fake_outway, outway, fed_settings)
    # A refusal for good is refused again when it is sent again.
    await undelivered.resend(db_session, client_peer.id, row.id, actor=None)
    await send_due(db_session, outway, fed_settings)
    assert row.status == OUTBOX_REJECTED
    assert await undelivered.counts(db_session) == {client_peer.id: 1}

    with clock.at(T0):
        await undelivered.set_aside(db_session, client_peer.id, row.id, actor=None)
    assert (row.status, row.set_aside_at) == (OUTBOX_REJECTED, T0)
    assert await undelivered.of_peer(db_session, client_peer.id) == []
    assert await undelivered.counts(db_session) == {}
    assert heard[-1] == ([], {client_peer.id})
    # Sent again after all, it counts again until it arrives.
    await undelivered.resend(db_session, client_peer.id, row.id, actor=None)
    assert row.set_aside_at is None
    assert await undelivered.counts(db_session) == {client_peer.id: 1}


async def test_after_every_round_the_domain_hears_what_does_not_arrive(
    db_session, client_peer, make_peer, fake_outway, outway, fed_settings
):
    other = await make_peer()
    heard = []

    async def reporter(db, deliveries, peer_ids):
        heard.append((deliveries, peer_ids))

    registry.register_delivery_reporter(reporter)
    with clock.at(T0):
        refused = await enqueue(db_session, other, "sendVacancy", example("vacancy"))
        waiting = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda request: (
        httpx.Response(410, text="weg")
        if request.url.path.startswith("/v1/vacatures")
        else httpx.Response(503, text="later")
    )
    steps = (T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=3))
    for moment in steps:
        await _attempt_at(moment, db_session, outway, fed_settings)

    first, second, third = (deliveries for deliveries, _ in heard)
    assert all(peer_ids is None for _, peer_ids in heard)
    # The refusal counts at once; two failures of the other are a blip.
    assert [(d.peer_id, d.count, d.final) for d in first] == [(other.id, 1, True)]
    assert second == first
    by_peer = {d.peer_id: d for d in third}
    assert set(by_peer) == {other.id, client_peer.id}
    gone = by_peer[other.id]
    assert (gone.failure, gone.final, gone.retry_until) == (FAILURE_GONE, True, None)
    assert gone.peer_name == other.name and gone.since == refused.failing_since
    retried = by_peer[client_peer.id]
    assert (retried.count, retried.final, retried.failure) == (
        1,
        False,
        FAILURE_RECEIVER_ERROR,
    )
    assert retried.since == steps[2]
    assert retried.retry_until == T0 + timedelta(days=7) == waiting.retry_until


async def test_a_report_that_fails_does_not_stop_the_sending(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    async def broken(db, deliveries, peer_ids):
        raise RuntimeError("the domain is down")

    registry.register_delivery_reporter(broken)
    row = await enqueue(db_session, client_peer, "sendQuote", example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(201, json=RECEIPT)
    stats = await send_due(db_session, outway, fed_settings)
    assert stats.sent == 1 and row.status == OUTBOX_SENT


async def test_a_report_that_fails_does_not_stop_sending_again(
    db_session, client_peer, fake_outway, outway, fed_settings
):
    row = await _refused(db_session, client_peer, fake_outway, outway, fed_settings)

    async def broken(db, deliveries, peer_ids):
        raise RuntimeError("the worker reports on the same peer")

    registry.register_delivery_reporter(broken)
    await undelivered.resend(db_session, client_peer.id, row.id, actor=None)
    await db_session.flush()
    assert row.status == OUTBOX_PENDING
