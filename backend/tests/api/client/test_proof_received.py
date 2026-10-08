"""A tekenbevoegde accepts a received quote, with proof, in the own instance.

The statement stays in this instance. What goes to the contractor is the
message of the contract, signed as before, and nothing more.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from grip.federation import signing, terms
from grip.federation.events import register_event_handlers
from grip.federation.models import FederationOutbox
from grip.models.decision_proof import DecisionEvidence
from grip.models.quote import QuoteAcceptance, QuoteRejection
from grip.proof.statement import columns, parse_statement
from grip.proof.verify import verify_bundle
from grip.services import events as domain_events


def _evidence_id(response) -> str:
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert "bewijs" in query, query
    return query["bewijs"][0]


async def _decide(client, quote, kind: str, **extra) -> str:
    created = await client.post(
        "/api/proof/intents",
        json={
            "kind": kind,
            "quote_id": str(quote.id),
            "quote_hash": quote.snapshot_hash,
            **extra,
        },
    )
    assert created.status_code == 201, created.text
    return _evidence_id(await client.get(created.json()["authorize_url"]))


async def test_acceptance_in_the_own_instance_is_one_statement(
    client, db_session, cast, act_as, received, federated
):
    register_event_handlers()
    seen: list[dict] = []

    async def remember(_db, _name, payload):
        seen.append(payload)

    domain_events.register_handler(domain_events.QUOTE_ACCEPTED, remember)

    act_as(cast.signer)
    evidence_id = await _decide(
        client, received.quote, "accept_received", signer_function="Directeur"
    )

    acceptance = (
        await db_session.execute(
            select(QuoteAcceptance).where(QuoteAcceptance.quote_id == received.quote.id)
        )
    ).scalar_one()
    evidence = await db_session.get(DecisionEvidence, acceptance.evidence_id)
    assert str(evidence.id) == evidence_id
    statement = parse_statement(bytes(evidence.statement))
    values = columns(statement)
    # One representation: the record, and the message that was signed for
    # the contractor, carry the time and the signer of the statement.
    assert acceptance.signed_at == values["decided_at"]
    assert acceptance.signer_name == values["signer_name"] == cast.signer.name
    assert acceptance.signer_function == "Directeur"
    assert acceptance.form == "own_instance" == values["channel"]
    assert acceptance.organisation == values["organisation"]

    authority = statement["bevoegdheid"]
    assert authority["grondslag"] == "recht" and authority["recht"] == "tekenbevoegde"
    assert authority["sinds"] is not None

    # The event refers to the statement by hash.
    assert seen[-1]["statement_hash"] == evidence.statement_hash

    # What goes to the contractor is the contract's message, signed as
    # before and still verifiable, with nothing of the proof in it.
    queued = await db_session.scalar(
        select(FederationOutbox).where(FederationOutbox.operation == "sendAcceptance")
    )
    assert queued is not None
    message = queued.payload
    signing.verify_acceptance(message, signing.own_jwks(federated))
    assert set(message) == {
        terms.term(name)
        for name in (
            "id",
            "quote_id",
            "quote_hash",
            "signer",
            "organisation",
            "signed_at",
            "form",
            "jws",
        )
    }
    sent = json.dumps(message)
    for private in (
        evidence.statement_hash,
        "verklaring",
        "id_token",
        "bevoegdheid",
        "grondslag",
        "nonce",
    ):
        assert private not in sent, private

    bundle = (await client.get(f"/api/proof/evidence/{evidence_id}/bundle")).json()
    assert verify_bundle(bundle).sound


async def test_rejection_in_the_own_instance(
    client, db_session, cast, act_as, received
):
    register_event_handlers()
    act_as(cast.signer)
    evidence_id = await _decide(
        client, received.quote, "reject_received", note="Het past niet in de begroting."
    )
    rejection = (
        await db_session.execute(
            select(QuoteRejection).where(QuoteRejection.quote_id == received.quote.id)
        )
    ).scalar_one()
    assert str(rejection.evidence_id) == evidence_id
    assert rejection.reason == "Het past niet in de begroting."
    queued = await db_session.scalar(
        select(FederationOutbox).where(FederationOutbox.operation == "sendRejection")
    )
    assert queued is not None
    sent = json.dumps(queued.payload)
    assert "verklaring" not in sent and "bevoegdheid" not in sent


async def test_only_a_tekenbevoegde_starts_the_decision(client, cast, act_as, received):
    body = {
        "kind": "accept_received",
        "quote_id": str(received.quote.id),
        "quote_hash": received.quote.snapshot_hash,
    }
    for person in (cast.requester, cast.lezer, cast.planner, cast.outsider):
        act_as(person)
        response = await client.post("/api/proof/intents", json=body)
        assert response.status_code == 404, person.name
    act_as(cast.signer)
    assert (await client.post("/api/proof/intents", json=body)).status_code == 201
