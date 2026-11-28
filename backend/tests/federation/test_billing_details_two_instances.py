"""Billing details from the client's grip to the contractor's billing terms.

Two instances in this process, as in ``test_two_instances``: the client
accepts a quote in its own grip and says where the invoice goes; the
contractor takes that into the billing terms of the assignment. A new
billing address later travels the same way, as a change of its own.

All names and addresses are fictional.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from grip.access import AANVRAGER, TEKENBEVOEGDE
from grip.federation import signing
from grip.federation.bridge.acceptance import accept_received_quote
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.models import FederationInbox
from grip.models.billing_delivery import BillingTerms, ClientBillingDetails
from grip.models.quote import Quote
from grip.repositories.domain import AssignmentRepository
from grip.services import (
    assignments,
    billing_deliveries,
    billing_details,
    quotes,
    rates,
)
from tests.federation import test_two_instances
from tests.federation.test_two_instances import RATE_D, _deliver, _know, _person

instances = test_two_instances.instances

GIVEN = {
    "organisation": "Voorbeelddirectie",
    "attention_of": "Afdeling Financiën Voorbeeld",
    "address": "Postbus 00000",
    "postcode_city": "0000 AA Den Haag",
    "reference": "VPL-2026-0042",
    "contact_name": "Crediteuren Voorbeeld",
    "contact_email": "crediteuren@opdrachtgever.example",
}


async def test_billing_details_reach_the_contractors_billing_terms(instances):
    client, contractor = instances

    async with client.session() as db:
        requester = await _person(
            db, "aanvrager@opdrachtgever.example", "Aanvrager Voorbeeld", AANVRAGER
        )
        signer = await _person(
            db,
            "tekenbevoegde@opdrachtgever.example",
            "Tekenbevoegde Voorbeeld",
            TEKENBEVOEGDE,
        )
        await _know(db, contractor)
    async with contractor.session() as db:
        manager = await _person(db, "manager@opdrachtnemer.example", "Opdrachtmanager")
        await _know(db, client)
        for year, cents in RATE_D.items():
            await rates.create_rate_card(db, year, actor=None)
            await rates.set_rate_band(db, year, "D", cents, actor=None)
            await rates.set_rate_card_status(db, year, "active", actor=None)

    async with client.session() as db:
        assignment, request_id = await assignments.create_assignment_request(
            db,
            name="Opdracht Alfa",
            contractor_organisation_id=(
                await from_reference(db, contractor.reference())
            ).id,
            client_organisation_id=(await own_organisation(db)).id,
            actor=requester,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
        )
        assignment_id, assignment_uri = assignment.id, assignment.uri
    await _deliver(client)

    async with contractor.session() as db:
        received = await AssignmentRepository(db).get_by_uri(assignment_uri)
        assert received is not None
        contractor_assignment_id = received.id
        await assignments.add_budget_line(
            db,
            received.id,
            description="Productmanager",
            kind="personnel",
            role="Productmanager",
            fte=Decimal("0.8"),
            rate_category="D",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            actor=manager,
        )
        quote = await quotes.issue_quote(
            db, received.id, actor=manager, request_id=request_id
        )
        quote_id = quote.id
        await quotes.offer_quote(db, quote_id, "client_instance", actor=manager)
        # The manager typed something in before the acceptance.
        await billing_deliveries.set_terms(
            db, received.id, actor=manager, details={"organisation": "Overgetypt"}
        )
    await _deliver(contractor)

    # --- the client accepts and says where the invoice goes ----------------
    async with client.session() as db:
        seen = await db.get(Quote, quote_id)
        acceptance = await accept_received_quote(
            db, seen.id, actor=signer, billing_details=GIVEN
        )
        acceptance_id, signed_at = acceptance.id, acceptance.signed_at
    await _deliver(client)

    async with contractor.session() as db:
        terms = await db.get(BillingTerms, contractor_assignment_id)
        assert terms is not None
        # What the client gave at the acceptance wins over what was typed in.
        assert terms.details == GIVEN
        assert terms.details_given_at == signed_at
        wire = await db.scalar(
            select(FederationInbox).where(FederationInbox.message_id == acceptance_id)
        )
        assert wire.result["billing_details_applied"] is True
        # The signature still covers only the acceptance itself.
        signing.verify_acceptance(wire.payload, signing.own_jwks(client.settings()))

    # --- later, a new billing address ---------------------------------------
    async with client.session() as db:
        await billing_details.change(
            db, assignment_id, {**GIVEN, "address": "Postbus 00001"}, actor=requester
        )
        kept = await db.get(ClientBillingDetails, assignment_id)
        given_at = kept.given_at
    await _deliver(client)

    async with contractor.session() as db:
        terms = await db.get(BillingTerms, contractor_assignment_id)
        assert terms.details["address"] == "Postbus 00001"
        assert terms.details_given_at == given_at
        # Applies from the next delivery: nothing was delivered yet.
        view = await billing_deliveries.terms_of(db, contractor_assignment_id)
        assert view.missing_details == ()
