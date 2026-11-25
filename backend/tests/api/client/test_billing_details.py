"""The client gives its billing details: with the acceptance, and later.

This instance is the client. What it gives is kept here, shown back on the
assignment, and goes to the contractor: with the acceptance (outside its
signature) or as a change of its own (sendBillingDetails).

All names and addresses are fictional.
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from grip.federation import signing, terms
from grip.federation.contract_loader import validation_errors
from grip.federation.events import register_event_handlers
from grip.federation.models import FederationOutbox
from grip.models.billing_delivery import BillingTerms, ClientBillingDetails
from grip.models.quote import Quote
from grip.services import quotes

DETAILS = {
    "organisation": "Voorbeelddirectie",
    "attention_of": "Afdeling Financiën Voorbeeld",
    "address": "Postbus 00000",
    "postcode_city": "0000 AA Den Haag",
    "reference": "VPL-2026-0042",
    "contact_name": "Crediteuren Voorbeeld",
    "contact_phone": "070 000 0000",
    "contact_email": "crediteuren@opdrachtgever.example",
}
SIGNED = {"id", "quote_id", "quote_hash", "signer", "organisation", "signed_at", "form"}


async def _accept(client, quote, **extra):
    created = await client.post(
        "/api/proof/intents",
        json={
            "kind": "accept_received",
            "quote_id": str(quote.id),
            "quote_hash": quote.snapshot_hash,
            **extra,
        },
    )
    if created.status_code != 201:
        return created
    back = await client.get(created.json()["authorize_url"])
    assert back.status_code == 302, back.text
    assert "bewijs" in parse_qs(urlsplit(back.headers["location"]).query)
    return back


async def _queued(db_session, operation: str) -> list[FederationOutbox]:
    return list(
        (
            await db_session.execute(
                select(FederationOutbox).where(FederationOutbox.operation == operation)
            )
        ).scalars()
    )


@pytest.fixture
async def with_annex(db_session, received):
    """The received quote has the annex Factuurinformatie."""
    snapshot = {**received.quote.snapshot, "letter": {"billing_annex": True}}
    quote = await quotes.receive_quote(
        db_session,
        received.assignment.id,
        quote_id=uuid.uuid4(),
        uri="https://grip.opdrachtnemer.example/id/offerte/met-bijlage",
        snapshot=snapshot,
        claimed_hash=quotes.snapshot_hash(snapshot),
        issued_at=received.quote.issued_at,
    )
    await db_session.flush()
    return quote


async def test_details_go_with_the_acceptance_outside_its_signature(
    client, db_session, cast, act_as, received, federated
):
    register_event_handlers()
    act_as(cast.signer)
    back = await _accept(client, received.quote, billing_details=DETAILS)
    assert back.status_code == 302

    kept = await db_session.get(ClientBillingDetails, received.assignment.id)
    assert kept is not None and kept.details == DETAILS
    (queued,) = await _queued(db_session, "sendAcceptance")
    message = queued.payload
    assert validation_errors("akkoord", message) == []
    assert message[terms.term("billing_details")] == {
        "organisatie": "Voorbeelddirectie",
        "ten_name_van": "Afdeling Financiën Voorbeeld",
        "adres": "Postbus 00000",
        "postcode_plaats": "0000 AA Den Haag",
        "kenmerk": "VPL-2026-0042",
        "contactpersoon": {
            "naam": "Crediteuren Voorbeeld",
            "telefoon": "070 000 0000",
            "email": "crediteuren@opdrachtgever.example",
        },
    }
    # The signature covers exactly what it covered before.
    signing.verify_acceptance(message, signing.own_jwks(federated))
    assert set(signing.signed_fields(message)) == {terms.term(n) for n in SIGNED}
    assert kept.given_at.isoformat() == terms.from_contract(message)["signed_at"]
    # This instance is not the contractor: it keeps no billing terms.
    assert await db_session.get(BillingTerms, received.assignment.id) is None


async def test_the_annex_asks_for_the_details_at_signing(
    client, cast, act_as, received, with_annex
):
    act_as(cast.signer)
    shown = await client.get(f"/api/received-quotes/{with_annex.id}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["quote"]["content"]["billing_annex"] is True
    refused = await _accept(client, with_annex)
    assert refused.status_code == 422, refused.text
    assert refused.json()["missing_details"] == [
        "organisation",
        "address",
        "postcode_city",
    ]
    back = await _accept(client, with_annex, billing_details=DETAILS)
    assert back.status_code == 302


async def test_the_assignment_shows_what_was_given_to_who_reads_money(
    client, db_session, cast, act_as, received, federated
):
    register_event_handlers()
    act_as(cast.signer)
    await _accept(client, received.quote, billing_details=DETAILS)
    path = f"/api/client/assignments/{received.assignment.id}"

    owner = (await act_as(cast.requester).get(path)).json()
    assert {k: owner["billing_details"][k] for k in DETAILS} == DETAILS
    assert owner["billing_details"]["given_at"]
    assert owner["may_give_billing_details"] is True
    lezer = (await act_as(cast.lezer).get(path)).json()
    assert lezer["billing_details"]["address"] == "Postbus 00000"
    assert lezer["may_give_billing_details"] is False
    # Class B: a reader of class A only does not learn they exist.
    planner = await act_as(cast.planner).get(path)
    assert planner.status_code == 200, planner.text
    assert "billing_details" not in planner.json()
    assert "Postbus" not in planner.text
    assert planner.json()["may_give_billing_details"] is False


async def test_a_new_billing_address_goes_to_the_contractor(
    client, db_session, cast, act_as, received, federated
):
    register_event_handlers()
    path = f"/api/client/assignments/{received.assignment.id}/billing-details"
    changed = {**DETAILS, "address": "Postbus 00001", "contact_phone": None}
    response = await act_as(cast.requester).put(path, json=changed)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["billing_details"]["address"] == "Postbus 00001"
    assert "contact_phone" not in body["billing_details"] or (
        body["billing_details"]["contact_phone"] is None
    )

    (queued,) = await _queued(db_session, "sendBillingDetails")
    uri_id = received.assignment.uri.rsplit("/", 1)[-1]
    assert queued.path == f"/v1/opdrachten/{uri_id}/factuurinformatie"
    assert queued.method == "PUT"
    assert validation_errors("factuurinformatie-wijziging", queued.payload) == []
    message = terms.from_contract(queued.payload)
    assert message["billing_details"]["address"] == "Postbus 00001"
    assert "phone" not in message["billing_details"]["contact"]
    kept = await db_session.get(ClientBillingDetails, received.assignment.id)
    await db_session.refresh(kept)
    assert message["given_at"] == kept.given_at.isoformat()
    assert kept.given_by_id == cast.requester.id

    # A tekenbevoegde may as well; each change is a message of its own.
    again = await act_as(cast.signer).put(path, json=DETAILS)
    assert again.status_code == 200, again.text
    assert len(await _queued(db_session, "sendBillingDetails")) == 2


async def test_a_new_billing_address_needs_the_address_and_the_right(
    client, db_session, cast, act_as, received, federated
):
    register_event_handlers()
    path = f"/api/client/assignments/{received.assignment.id}/billing-details"
    incomplete = await act_as(cast.requester).put(
        path, json={"organisation": "Voorbeelddirectie", "reference": "X-1"}
    )
    assert incomplete.status_code == 422, incomplete.text
    assert incomplete.json()["missing_details"] == ["address", "postcode_city"]
    for person in (cast.planner, cast.lezer, cast.beheerder):
        response = await act_as(person).put(path, json=DETAILS)
        assert response.status_code == 403, person.name
    outsider = await act_as(cast.outsider).put(path, json=DETAILS)
    assert outsider.status_code == 404
    unknown = await act_as(cast.requester).put(
        f"/api/client/assignments/{uuid.uuid4()}/billing-details", json=DETAILS
    )
    assert unknown.status_code == 404
    too_long = await act_as(cast.requester).put(
        path, json={**DETAILS, "address": "x" * 201}
    )
    assert too_long.status_code == 422
    assert await _queued(db_session, "sendBillingDetails") == []
    assert await db_session.get(ClientBillingDetails, received.assignment.id) is None
    assert (await db_session.get(Quote, received.quote.id)).status == "issued"


async def test_a_contractor_in_this_same_instance_takes_them_right_away(
    db_session, cast
):
    """Both sides in one instance: no message, the billing terms change here."""
    from grip.federation.bridge.organisations import own_organisation
    from grip.services import assignments, billing_details

    register_event_handlers()
    own = await own_organisation(db_session)
    assignment = await assignments.create_assignment(
        db_session,
        name="Opdracht Intern",
        actor=None,
        client_organisation_id=own.id,
        contractor_organisation_id=own.id,
    )
    await billing_details.change(db_session, assignment.id, DETAILS, actor=cast.signer)
    await db_session.flush()
    terms = await db_session.get(BillingTerms, assignment.id)
    assert terms is not None and terms.details == DETAILS
    assert await _queued(db_session, "sendBillingDetails") == []
