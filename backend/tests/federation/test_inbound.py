"""Pushed messages: the peer check, validation, idempotency and handlers."""

import copy
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from grip.core.config import get_settings
from grip.federation import signing
from grip.federation.contract_loader import api_version, validation_errors
from grip.federation.models import (
    PEER_ROLE_CHILD,
    PEER_ROLE_CORPUS,
    PEER_ROLE_PARENT,
    FederationInbox,
)
from grip.federation.problems import PROBLEM_MEDIA_TYPE, FederationProblem
from grip.federation.registry import register_inbound_handler

from .conftest import (
    CLIENT_BASE,
    CLIENT_PEER_ID,
    CONTRACTOR_PEER_ID,
    as_peer,
    code_example,
    example,
    t,
)

QUOTE_ID = "9d3b6c0e-2f41-4c8a-b0d2-6a1f5e7c8b90"


async def _inbox_count(db_session) -> int:
    return (
        await db_session.execute(select(func.count()).select_from(FederationInbox))
    ).scalar_one()


def _assert_problem(response: httpx.Response, status: int) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert validation_errors("problem", body) == []
    assert body["status"] == status
    return body


# --- who may call ----------------------------------------------------------


async def test_first_receipt_is_201_with_a_receipt(fed_client, db_session, make_peer):
    await make_peer()
    response = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201, response.text
    assert response.headers["API-Version"] == api_version()
    receipt = response.json()
    assert validation_errors("ontvangstbevestiging", receipt) == []
    assert receipt[t("message_id")] == QUOTE_ID
    assert receipt[t("outcome")] == "aanvaard"

    row = (await db_session.execute(select(FederationInbox))).scalar_one()
    assert row.operation == "sendQuote"
    assert row.payload == example("quote")
    assert row.payload_hash == signing.payload_hash(example("quote"))
    # No handler registered: stored, not yet processed.
    assert row.processed_at is None and row.result is None


async def test_missing_peer_header_is_refused(fed_client, db_session, make_peer):
    await make_peer()
    response = await fed_client.post("/v1/offertes", json=example("quote"))
    _assert_problem(response, 403)
    assert await _inbox_count(db_session) == 0


async def test_unknown_peer_is_refused(fed_client, db_session, make_peer):
    await make_peer()
    response = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer("99999999999999999999")
    )
    _assert_problem(response, 403)
    assert await _inbox_count(db_session) == 0


async def test_inactive_peer_is_refused_like_an_unknown_one(
    fed_client, db_session, make_peer
):
    await make_peer(is_active=False)
    inactive = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    unknown = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer("99999999999999999999")
    )
    assert _assert_problem(inactive, 403) == _assert_problem(unknown, 403)
    assert await _inbox_count(db_session) == 0


async def test_federation_disabled_refuses_everything(
    fed_client, fed_app, db_session, make_peer
):
    await make_peer()
    off = get_settings().model_copy(update={"FEDERATION_INBOUND_ENABLED": False})
    fed_app.dependency_overrides[get_settings] = lambda: off
    for method, path in [
        ("POST", "/v1/offertes"),
        ("GET", "/v1/jwks"),
        ("GET", "/v1/openapi.json"),
        ("GET", "/v1/doorgifte/opdrachten"),
    ]:
        response = await fed_client.request(
            method, path, json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
        )
        _assert_problem(response, 503)
    assert await _inbox_count(db_session) == 0


async def test_other_header_name_is_configurable(
    fed_client, fed_app, fed_settings, make_peer
):
    await make_peer()
    renamed = fed_settings.model_copy(update={"FSC_PEER_ID_HEADER": "X-Peer"})
    fed_app.dependency_overrides[get_settings] = lambda: renamed
    old = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    new = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers={"X-Peer": CONTRACTOR_PEER_ID}
    )
    assert (old.status_code, new.status_code) == (403, 201)


async def test_corpus_peer_cannot_push_messages(fed_client, db_session, make_peer):
    await make_peer(role=PEER_ROLE_CORPUS)
    response = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _assert_problem(response, 403)
    assert await _inbox_count(db_session) == 0


@pytest.mark.parametrize("role", [PEER_ROLE_PARENT, PEER_ROLE_CHILD])
async def test_parent_and_child_are_also_counterparts(fed_client, make_peer, role):
    await make_peer(role=role)
    response = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201


# --- idempotency -----------------------------------------------------------


async def test_same_id_same_content_is_200_duplicate(fed_client, db_session, make_peer):
    await make_peer()
    calls = []

    async def handler(db, peer, message):
        calls.append(message.message_id)

    register_inbound_handler("sendQuote", handler)
    first = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    # Key order must not matter: content is compared in canonical form.
    reordered = dict(reversed(list(example("quote").items())))
    second = await fed_client.post(
        "/v1/offertes", json=reordered, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == {**first.json(), t("outcome"): "duplicaat"}
    assert second.headers["API-Version"] == api_version()
    assert len(calls) == 1, "a duplicate must not be processed again"
    assert await _inbox_count(db_session) == 1


async def test_same_id_other_content_is_409(fed_client, db_session, make_peer):
    await make_peer()
    await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    changed = example("quote")
    changed[t("issued_at")] = "2026-06-02T10:00:00+02:00"
    response = await fed_client.post(
        "/v1/offertes", json=changed, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _assert_problem(response, 409)
    row = (await db_session.execute(select(FederationInbox))).scalar_one()
    assert row.payload == example("quote"), "the first message stays as it was"


async def test_same_id_from_another_peer_is_a_new_message(
    fed_client, db_session, make_peer
):
    await make_peer()
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    vacancy = example("vacancy")
    del vacancy[t("organisation")][t("instance_uri")]
    first = await fed_client.post(
        "/v1/vacatures", json=vacancy, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    second = await fed_client.post(
        "/v1/vacatures", json=vacancy, headers=as_peer(CLIENT_PEER_ID)
    )
    assert (first.status_code, second.status_code) == (201, 201)
    assert await _inbox_count(db_session) == 2


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "path,name",
    [
        ("/v1/offertes", "quote.ongeldige-hash"),
        ("/v1/offertes", "quote.zonder-regels"),
        ("/v1/opdrachtaanvragen", "assignment-request.zonder-context-refs"),
        (
            f"/v1/offertes/{QUOTE_ID}/akkoorden",
            "acceptance.eigen-instantie-zonder-jws",
        ),
    ],
)
async def test_invalid_contract_examples_are_refused_with_400(
    fed_client, db_session, make_peer, path, name
):
    await make_peer()
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    for peer_id in (CONTRACTOR_PEER_ID, CLIENT_PEER_ID):
        response = await fed_client.post(
            path, json=example(name, "invalid"), headers=as_peer(peer_id)
        )
        body = _assert_problem(response, 400)
        assert body["errors"]
    assert await _inbox_count(db_session) == 0


async def test_body_that_is_not_json_is_400(fed_client, make_peer):
    await make_peer()
    response = await fed_client.post(
        "/v1/offertes", content=b"{geen json", headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _assert_problem(response, 400)


async def test_quote_hash_that_does_not_match_the_snapshot_is_400(
    fed_client, db_session, make_peer
):
    await make_peer()
    quote = example("quote")
    quote[t("snapshot_hash")] = "0" * 64
    assert validation_errors("offerte", quote) == [], (
        "valid by schema, wrong by content"
    )
    response = await fed_client.post(
        "/v1/offertes", json=quote, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _assert_problem(response, 400)
    assert await _inbox_count(db_session) == 0


async def test_quote_without_request_is_accepted(fed_client, make_peer):
    await make_peer()
    response = await fed_client.post(
        "/v1/offertes",
        json=example("quote.eigen-initiatief"),
        headers=as_peer(CONTRACTOR_PEER_ID),
    )
    assert response.status_code == 201, response.text


async def test_peer_cannot_send_in_the_name_of_another_instance(
    fed_client, db_session, make_peer
):
    # The quote names grip.opdrachtnemer.example as contractor; this peer is
    # another instance.
    await make_peer(base_uri="https://grip.iemand-anders.example")
    response = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    _assert_problem(response, 403)
    assert await _inbox_count(db_session) == 0


async def test_path_and_body_must_name_the_same_quote(fed_client, make_peer):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    response = await fed_client.post(
        f"/v1/offertes/{uuid.uuid4()}/afwijzingen",
        json=example("rejection"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    _assert_problem(response, 400)


async def test_path_that_is_not_a_uuid_is_400(fed_client, make_peer):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    response = await fed_client.post(
        "/v1/offertes/geen-uuid/afwijzingen",
        json=example("rejection"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    _assert_problem(response, 400)


async def test_unknown_path_is_a_problem_too(fed_client):
    _assert_problem(await fed_client.get("/v1/bestaat-niet"), 404)


# --- every pushed operation ------------------------------------------------


@pytest.mark.parametrize(
    "method,path,name,operation",
    [
        (
            "POST",
            "/v1/opdrachtaanvragen",
            "assignment-request",
            "sendAssignmentRequest",
        ),
        (
            "POST",
            "/v1/opdrachtaanvragen",
            "assignment-request.zonder-context",
            "sendAssignmentRequest",
        ),
        ("POST", f"/v1/offertes/{QUOTE_ID}/afwijzingen", "rejection", "sendRejection"),
        (
            "POST",
            f"/v1/offertes/{QUOTE_ID}/akkoorden",
            "acceptance.pdf",
            "sendAcceptance",
        ),
        (
            "PUT",
            "/v1/opdrachten/3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60/eindrapport",
            "final-report",
            "sendFinalReport",
        ),
        ("POST", "/v1/vacatures", "vacancy", "sendVacancy"),
        (
            "POST",
            "/v1/vacatures/7b8c9d0e-0000-4000-8000-000000000006/aanbiedingen",
            "vacancy-offer",
            "sendVacancyOffer",
        ),
    ],
)
async def test_valid_contract_examples_are_accepted(
    fed_client, db_session, make_peer, method, path, name, operation
):
    # One peer whose base matches whichever side the example names as sender.
    body = example(name)
    sender = body.get(t("client")) if operation == "sendAssignmentRequest" else None
    base = (sender or {}).get(t("instance_uri")) or "https://grip.opdrachtnemer.example"
    await make_peer(base_uri=base)
    response = await fed_client.request(
        method, path, json=body, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201, response.text
    row = (await db_session.execute(select(FederationInbox))).scalar_one()
    assert row.operation == operation


async def test_final_report_must_belong_to_the_assignment_in_the_path(
    fed_client, make_peer
):
    await make_peer()
    response = await fed_client.put(
        f"/v1/opdrachten/{uuid.uuid4()}/eindrapport",
        json=example("final-report"),
        headers=as_peer(CONTRACTOR_PEER_ID),
    )
    _assert_problem(response, 400)


# --- the acceptance and its signature --------------------------------------


async def test_signed_acceptance_verifies_with_cached_keys(
    fed_client, fake_outway, make_peer
):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, jwks=example("jwks"))
    response = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/akkoorden",
        json=example("acceptance"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 201, response.text
    assert fake_outway.requests == [], "keys entered by hand are not fetched"


async def test_keys_are_fetched_through_the_outway_when_unknown(
    fed_client, fake_outway, db_session, make_peer
):
    peer = await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    fake_outway.handler = lambda _request: httpx.Response(200, json=example("jwks"))
    response = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/akkoorden",
        json=example("acceptance"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 201, response.text
    (request,) = fake_outway.requests
    assert str(request.url) == "http://outway.test/v1/jwks"
    assert (
        request.headers["Fsc-Grant-Hash"] == peer.grant_hashes["grip-opdrachtverkeer"]
    )
    assert peer.jwks == example("jwks") and peer.jwks_fetched_at is not None


async def test_rotated_key_triggers_a_refetch(fed_client, fake_outway, make_peer):
    stale = copy.deepcopy(example("jwks"))
    stale["keys"][0]["kid"] = "oud"
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, jwks=stale)
    fake_outway.handler = lambda _request: httpx.Response(200, json=example("jwks"))
    response = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/akkoorden",
        json=example("acceptance"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 201, response.text
    assert len(fake_outway.requests) == 1


async def test_tampered_acceptance_is_400(fed_client, db_session, make_peer):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, jwks=example("jwks"))
    acceptance = example("acceptance")
    acceptance[t("signer")][t("name")] = "Iemand Anders"
    response = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/akkoorden",
        json=acceptance,
        headers=as_peer(CLIENT_PEER_ID),
    )
    _assert_problem(response, 400)
    assert await _inbox_count(db_session) == 0


async def test_acceptance_signed_with_an_unpublished_key_is_400(
    fed_client, fake_outway, db_session, make_peer
):
    other = {"keys": [{**example("jwks")["keys"][0], "kid": "ander"}]}
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE, jwks=other)
    fake_outway.handler = lambda _request: httpx.Response(200, json=other)
    response = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/akkoorden",
        json=example("acceptance"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    _assert_problem(response, 400)
    assert await _inbox_count(db_session) == 0


async def test_keys_unavailable_is_503_so_the_sender_retries(
    fed_client, fake_outway, db_session, make_peer
):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    fake_outway.handler = lambda _request: httpx.Response(502, text="bad gateway")
    response = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/akkoorden",
        json=example("acceptance"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    _assert_problem(response, 503)
    assert await _inbox_count(db_session) == 0


# --- the domain handler ----------------------------------------------------


async def test_handler_runs_and_its_result_is_stored(fed_client, db_session, make_peer):
    peer = await make_peer()
    seen = {}

    async def handler(db, caller, message):
        seen.update(peer=caller.id, operation=message.operation, id=message.message_id)
        assert message.payload == code_example("quote")
        return {"quote_id": "lokaal-1"}

    register_inbound_handler("sendQuote", handler)
    response = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201
    assert seen == {
        "peer": peer.id,
        "operation": "sendQuote",
        "id": uuid.UUID(QUOTE_ID),
    }
    row = (await db_session.execute(select(FederationInbox))).scalar_one()
    assert row.processed_at is not None and row.result == {"quote_id": "lokaal-1"}


async def test_handler_gets_the_path_parameters(fed_client, make_peer):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)
    seen = []

    async def handler(db, caller, message):
        seen.append(message.path_parameters)

    register_inbound_handler("sendRejection", handler)
    await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/afwijzingen",
        json=example("rejection"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert seen == [{"quoteId": QUOTE_ID}]


@pytest.mark.parametrize("status", [403, 404, 409])
async def test_handler_can_refuse_and_nothing_is_stored(
    fed_client, db_session, make_peer, status
):
    await make_peer(CLIENT_PEER_ID, base_uri=CLIENT_BASE)

    async def handler(db, caller, message):
        raise FederationProblem(status, "Geweigerd", "Past niet bij de offerte.")

    register_inbound_handler("sendRejection", handler)
    response = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/afwijzingen",
        json=example("rejection"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    body = _assert_problem(response, status)
    assert body["detail"] == "Past niet bij de offerte."
    assert body["instance"] == f"/v1/offertes/{QUOTE_ID}/afwijzingen"
    assert await _inbox_count(db_session) == 0

    # After a refusal the sender may send the same id again; it is new.
    register_inbound_handler("sendRejection", _accept)
    again = await fed_client.post(
        f"/v1/offertes/{QUOTE_ID}/afwijzingen",
        json=example("rejection"),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert again.status_code == 201


async def _accept(db, caller, message):
    return None


async def test_handler_that_crashes_is_a_500_problem_and_stores_nothing(
    fed_client, db_session, make_peer
):
    await make_peer()

    async def handler(db, caller, message):
        raise RuntimeError("kapot")

    register_inbound_handler("sendQuote", handler)
    response = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=as_peer(CONTRACTOR_PEER_ID)
    )
    body = _assert_problem(response, 500)
    assert "kapot" not in response.text and body["title"] == "Interne fout"
    assert await _inbox_count(db_session) == 0
