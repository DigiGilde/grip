"""Billing details given with an acceptance land in the billing terms.

The client says where the invoice goes when it accepts: through the signing
link, or on the signed pdf someone here records. The details go into the
billing terms of the assignment, outside the statement of the decision.
When the quote has the annex Factuurinformatie, signing asks for them.

All names and addresses are fictional.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from grip.core import clock
from grip.models.billing_delivery import BillingTerms
from grip.models.decision_proof import DecisionEvidence
from grip.models.quote import QuoteAcceptance
from grip.services import billing_deliveries, instance_settings, quote_sender

from .conftest import PDF_BYTES
from .test_quote_letter import BLOCKS, SENDER

DETAILS = {
    "organisation": "Voorbeeldministerie",
    "attention_of": "Directie Voorbeeld",
    "address": "Postbus 00000",
    "postcode_city": "0000 AA Den Haag",
    "reference": "VPL-2026-0042",
    "contact_name": "Crediteuren Voorbeeld",
    "contact_phone": "070 000 0000",
    "contact_email": "crediteuren@opdrachtgever.example",
}


@pytest.fixture
async def with_annex(db_session, world):
    """Quotes of this instance carry the annex Factuurinformatie."""
    await instance_settings.set_values(
        db_session,
        {
            quote_sender.SENDER.key: SENDER,
            quote_sender.TEXT_BLOCKS.key: BLOCKS,
            quote_sender.LETTER.key: {
                "opening": "Hierbij de offerte.",
                "closing": "Met vriendelijke groet.",
                "billing_annex": True,
            },
        },
        actor=world.beheerder,
    )
    return world


async def _invited(act_as, world, *, annex: bool = False, reference=None) -> dict:
    client = act_as(world.manager)
    if annex:
        response = await client.put(
            f"/api/assignments/{world.assignment.id}/quote-draft/sections/inleiding",
            json={"body": "De opgave is groot."},
        )
        assert response.status_code == 200, response.text
    body = {"client_reference": reference} if reference else {}
    response = await client.post(
        f"/api/assignments/{world.assignment.id}/quotes", json=body
    )
    assert response.status_code == 201, response.text
    quote = response.json()
    response = await client.post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": world.signer.email}
    )
    assert response.status_code == 201, response.text
    return quote


async def _intent(client, quote, **extra):
    return await client.post(
        f"/api/signing/quotes/{quote['id']}/intents",
        json={
            "decision": "accept",
            "quote_hash": quote["snapshot_hash"],
            "confirm_mandate": True,
            **extra,
        },
    )


async def _sign(client, quote, **extra) -> str:
    created = await _intent(client, quote, **extra)
    assert created.status_code == 201, created.text
    back = await client.get(created.json()["authorize_url"])
    assert back.status_code == 302, back.text
    return parse_qs(urlsplit(back.headers["location"]).query)["bewijs"][0]


async def _terms(db_session, world) -> BillingTerms | None:
    await db_session.flush()
    row = await db_session.get(BillingTerms, world.assignment.id)
    if row is not None:
        await db_session.refresh(row)
    return row


# --- the signing link ----------------------------------------------------------


async def test_details_given_at_signing_go_into_the_billing_terms(
    act_as, world, db_session
):
    # Typed in by the manager before the acceptance: the client's word wins.
    await billing_deliveries.set_terms(
        db_session,
        world.assignment.id,
        actor=world.manager,
        details={"organisation": "Eerder ingevuld", "contact_name": "Iemand"},
    )
    quote = await _invited(act_as, world)
    evidence_id = await _sign(
        act_as(world.signer), quote, billing_details={**DETAILS, "attention_of": None}
    )

    terms = await _terms(db_session, world)
    assert terms is not None
    expected = {k: v for k, v in DETAILS.items() if k != "attention_of"}
    assert terms.details == expected
    acceptance = await db_session.scalar(
        select(QuoteAcceptance).where(
            QuoteAcceptance.quote_id == uuid.UUID(quote["id"])
        )
    )
    assert terms.details_given_at == acceptance.signed_at
    # Not part of the proof: the statement says nothing about the invoice.
    evidence = await db_session.get(DecisionEvidence, uuid.UUID(evidence_id))
    statement = bytes(evidence.statement).decode()
    for value in ("Postbus 00000", "VPL-2026-0042", "crediteuren@"):
        assert value not in statement

    # The manager sees them as the terms of the assignment.
    overview = await act_as(world.manager).get(
        f"/api/assignments/{world.assignment.id}/billing"
    )
    assert overview.status_code == 200, overview.text
    assert overview.json()["terms"]["details"] == expected
    assert overview.json()["terms"]["missing_details"] == []


async def test_without_the_annex_nothing_is_asked(act_as, world, db_session):
    quote = await _invited(act_as, world)
    await _sign(act_as(world.signer), quote)
    assert await _terms(db_session, world) is None


async def test_a_reference_alone_gives_nothing(act_as, world, db_session):
    """A form that carries only the reference it was filled in with."""
    quote = await _invited(act_as, world, reference="ORDER-7")
    await _sign(act_as(world.signer), quote, billing_details={"reference": "ORDER-7"})
    assert await _terms(db_session, world) is None


async def test_part_of_an_address_is_refused(act_as, world, db_session):
    quote = await _invited(act_as, world)
    response = await _intent(
        act_as(world.signer),
        quote,
        billing_details={"organisation": "Voorbeeldministerie"},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["missing_details"] == ["address", "postcode_city"]
    assert body["detail"] == (
        "Het factuuradres en postcode en plaats ontbreken. "
        "Vul de factuurgegevens van de opdrachtgever in."
    )


async def test_with_the_annex_signing_asks_for_the_details(
    act_as, with_annex, db_session
):
    world = with_annex
    quote = await _invited(act_as, world, annex=True, reference="ORDER-7")
    # The signer reads that the annex is there, and the reference to prefill.
    shown = (
        await act_as(world.signer).get(f"/api/signing/quotes/{quote['id']}")
    ).json()
    assert shown["content"]["billing_annex"] is True
    assert shown["content"]["client_reference"] == "ORDER-7"
    managed = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    assert managed["content"]["billing_annex"] is True

    signer = act_as(world.signer)
    for given in (None, {"reference": "ORDER-7"}):
        response = await _intent(signer, quote, billing_details=given)
        assert response.status_code == 422, response.text
        assert response.json()["missing_details"] == [
            "organisation",
            "address",
            "postcode_city",
        ]
        assert response.json()["detail"] == (
            "De organisatie waaraan wordt gefactureerd, het factuuradres en "
            "postcode en plaats ontbreken. Vul de factuurgegevens van de "
            "opdrachtgever in."
        )
    response = await _intent(
        signer, quote, billing_details={**DETAILS, "address": "  "}
    )
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Het factuuradres ontbreekt.")

    await _sign(signer, quote, billing_details=DETAILS)
    terms = await _terms(db_session, world)
    assert terms is not None and terms.details == DETAILS


async def test_rejecting_ignores_billing_details(act_as, with_annex, db_session):
    world = with_annex
    quote = await _invited(act_as, world, annex=True)
    created = await act_as(world.signer).post(
        f"/api/signing/quotes/{quote['id']}/intents",
        json={
            "decision": "reject",
            "quote_hash": quote["snapshot_hash"],
            "billing_details": DETAILS,
        },
    )
    assert created.status_code == 201, created.text
    assert await _terms(db_session, world) is None


async def test_who_cannot_accept_cannot_give_details(act_as, world):
    quote = await _invited(act_as, world)
    response = await _intent(act_as(world.outsider), quote, billing_details=DETAILS)
    assert response.status_code in (403, 404)


async def test_without_money_no_annex_flag(act_as, with_annex):
    """``billing_annex`` is content of the quote: class B, like the rest."""
    world = with_annex
    quote = await _invited(act_as, world, annex=True)
    for person in (world.planner, world.member):
        response = await act_as(person).get(f"/api/quotes/{quote['id']}")
        if response.status_code == 200:
            assert "billing_annex" not in response.text, person.name
            assert "content" not in response.json(), person.name


# --- a signed pdf --------------------------------------------------------------


async def _upload(client, quote, **data):
    return await client.post(
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        data={
            "signer_name": "Directeur Voorbeeld",
            "signer_email": "directeur@opdrachtgever.example",
            **data,
        },
        files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
    )


async def test_a_signed_pdf_carries_the_annex_as_typed_over(act_as, world, db_session):
    # The day of signing lies between the day of the quote and today.
    with clock.at(datetime(2026, 6, 1, 10, 0, tzinfo=UTC)):
        quote = await _invited(act_as, world)
    with clock.at(datetime(2026, 6, 15, 10, 0, tzinfo=UTC)):
        response = await _upload(
            act_as(world.manager),
            quote,
            signed_at="2026-06-10T14:30:00+02:00",
            billing_details=json.dumps(DETAILS),
        )
    assert response.status_code == 201, response.text
    terms = await _terms(db_session, world)
    assert terms is not None and terms.details == DETAILS
    assert terms.details_given_at.isoformat() == "2026-06-10T12:30:00+00:00"


async def test_a_signed_pdf_needs_no_details_even_with_the_annex(
    act_as, with_annex, db_session
):
    world = with_annex
    quote = await _invited(act_as, world, annex=True)
    response = await _upload(act_as(world.manager), quote)
    assert response.status_code == 201, response.text
    assert await _terms(db_session, world) is None


async def test_a_signed_pdf_with_details_that_are_no_object_is_refused(
    act_as, world, db_session
):
    quote = await _invited(act_as, world)
    for raw in ("geen json", "[1, 2]", json.dumps({"organisation": 7})):
        response = await _upload(act_as(world.manager), quote, billing_details=raw)
        assert response.status_code == 422, raw
    response = await _upload(
        act_as(world.manager),
        quote,
        billing_details=json.dumps({"organisation": "Alleen dit"}),
    )
    assert response.status_code == 422
    assert response.json()["missing_details"] == ["address", "postcode_city"]
    assert await _terms(db_session, world) is None
