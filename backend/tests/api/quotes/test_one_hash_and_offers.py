"""One quote has one canonical form and one hash; the channel is per offer.

ADR 0020: the hash on the document, in an acceptance of every form and in
the messages between instances is one value, the SHA-256 over the stored
canonical bytes. ADR 0021: issuing freezes a quote and sends nothing; a
quote is offered through a channel chosen then.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime

import pytest
import rfc8785
from sqlalchemy import select

from grip.core.config import get_settings
from grip.federation import registry, signing
from grip.federation.bridge.acceptance import accept_received_quote
from grip.federation.bridge.organisations import own_organisation
from grip.federation.events import register_event_handlers
from grip.federation.models import FederationOutbox, Peer
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation
from grip.models.quote import Quote, QuoteAcceptance, QuoteOffer
from grip.services import assignments, quote_channels, quotes, rates, terms
from grip.services import events as domain_events
from grip.services.errors import QuoteHashMismatchError
from tests.api.quotes.conftest import document_text

from .conftest import PDF_BYTES

CLIENT_INSTANCE = "https://grip.opdrachtgever.example"
CONTRACTOR_INSTANCE = "https://grip.opdrachtnemer.example"


@pytest.fixture
def identified(monkeypatch):
    """This instance has a TOOI URI, so it can name itself in a message."""
    monkeypatch.setattr(
        get_settings(),
        "INSTANCE_TOOI_URI",
        "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
    )


@pytest.fixture(autouse=True)
def _nothing_registered():
    registry.clear_registries()
    domain_events.clear_handlers()
    yield
    registry.clear_registries()
    domain_events.clear_handlers()


def _unspaced(text: str) -> str:
    """A document may print the hash in groups; the value is what counts."""
    return re.sub(r"[\s]|<br ?/?>|&nbsp;", "", text)


async def _issue(act_as, world) -> dict:
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _stored(db_session, quote_id) -> Quote:
    return (
        await db_session.execute(
            select(Quote)
            .where(Quote.id == uuid.UUID(str(quote_id)))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _connect_client(db_session, world, *, grant: bool = True) -> Peer:
    """The client organisation runs a grip instance and is connected."""
    organisation = await db_session.get(
        Organisation, world.assignment.client_organisation_id
    )
    organisation.instance_uri = CLIENT_INSTANCE
    peer = Peer(
        peer_id="00000000000000000010",
        name="Voorbeeldministerie",
        base_uri=CLIENT_INSTANCE,
        role="counterpart",
        grant_hashes={"grip-opdrachtverkeer": "$1$4$grant"} if grant else {},
    )
    db_session.add(peer)
    await db_session.flush()
    return peer


# --- one hash ----------------------------------------------------------------


async def test_the_hash_is_one_value_on_document_and_every_acceptance(
    act_as, world, db_session, monkeypatch
):
    """Document, signing link, uploaded pdf and the federated message agree."""
    quote = await _issue(act_as, world)
    stored = await _stored(db_session, quote["id"])
    quote_id, issued_at = stored.id, stored.issued_at
    canonical = bytes(stored.canonical)
    the_hash = hashlib.sha256(canonical).hexdigest()
    assert quote["snapshot_hash"] == stored.snapshot_hash == the_hash

    manager = act_as(world.manager)
    document = await manager.get(f"/api/quotes/{quote['id']}/document")
    assert the_hash in _unspaced(document_text(document))

    # Signing link: the signer is shown the same hash and cites it.
    invited = await manager.post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": world.signer.email}
    )
    assert invited.status_code == 201, invited.text
    signer = act_as(world.signer)
    shown = (await signer.get(f"/api/signing/quotes/{quote['id']}")).json()
    assert shown["snapshot_hash"] == the_hash
    signing_document = await signer.get(f"/api/signing/quotes/{quote['id']}/document")
    assert the_hash in _unspaced(document_text(signing_document))

    # Each form of acceptance in turn on this same quote; the decision is
    # undone in between, because a quote is decided once.
    async def accepted_hash(act) -> str:
        savepoint = await db_session.begin_nested()
        try:
            await act()
            acceptance = await db_session.scalar(
                select(QuoteAcceptance)
                .where(QuoteAcceptance.quote_id == quote_id)
                .execution_options(populate_existing=True)
            )
            return f"{acceptance.form}:{acceptance.quote_hash}"
        finally:
            await savepoint.rollback()
            # The rollback expired what the session holds; load the cast
            # again so the next step can use it.
            for row in (world.manager, world.signer, world.assignment):
                await db_session.refresh(row)

    async def by_signing_link():
        response = await act_as(world.signer).post(
            f"/api/signing/quotes/{quote['id']}/accept",
            json={"quote_hash": the_hash, "confirm_mandate": True},
        )
        assert response.status_code == 201, response.text

    async def by_uploaded_pdf():
        response = await act_as(world.manager).post(
            f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
            data={"signer_name": "Directeur", "signer_email": "d@klant.example"},
            files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
        )
        assert response.status_code == 201, response.text

    assert await accepted_hash(by_signing_link) == f"signing_link:{the_hash}"
    assert await accepted_hash(by_uploaded_pdf) == f"uploaded_pdf:{the_hash}"

    # Federated: the same quote as a client's instance receives it (the same
    # bytes), accepted there, gives a signed message that cites the same hash.
    monkeypatch.setattr(
        get_settings(),
        "INSTANCE_TOOI_URI",
        "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
    )
    register_event_handlers()
    own = await own_organisation(db_session)
    contractor = await assignments.upsert_organisation(
        db_session,
        name="Voorbeeldgilde",
        tooi_uri="https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
        unit_key="voorbeeldgilde",
        instance_uri=CONTRACTOR_INSTANCE,
    )
    db_session.add(
        Peer(
            peer_id="00000000000000000020",
            name="Voorbeeldgilde",
            base_uri=CONTRACTOR_INSTANCE,
            role="counterpart",
            grant_hashes={"grip-opdrachtverkeer": "$1$4$grant"},
        )
    )
    mirror = await assignments.create_assignment(
        db_session,
        name="Opdracht Alfa",
        actor=None,
        client_organisation_id=own.id,
        contractor_organisation_id=contractor.id,
        uri=f"{get_settings().INSTANCE_BASE_URI}/id/opdracht/{uuid.uuid4()}",
    )
    assignments.share_with_instance(mirror, CONTRACTOR_INSTANCE)
    received = await quotes.receive_quote(
        db_session,
        mirror.id,
        quote_id=uuid.uuid4(),
        uri=f"{CONTRACTOR_INSTANCE}/id/offerte/{uuid.uuid4()}",
        canonical=canonical,
        claimed_hash=the_hash,
        issued_at=issued_at,
    )
    assert bytes(received.canonical) == canonical
    acceptance = await accept_received_quote(
        db_session, received.id, actor=world.signer
    )
    assert acceptance.form == "own_instance" and acceptance.quote_hash == the_hash
    (message,) = (await db_session.execute(select(FederationOutbox))).scalars().all()
    assert message.operation == "sendAcceptance"
    assert message.payload["offerte_hash"] == the_hash
    signing.verify_acceptance(message.payload, signing.own_jwks(get_settings()))


async def test_bytes_and_hash_survive_a_changed_rate_card_and_term_mapping(
    act_as, world, db_session, monkeypatch
):
    quote = await _issue(act_as, world)
    before = await _stored(db_session, quote["id"])
    canonical, the_hash = bytes(before.canonical), before.snapshot_hash
    assert json.loads(canonical)["naam"] == "Opdracht Alfa"

    await rates.set_rate_band(db_session, 2026, "D", 2_000_000, actor=world.beheerder)
    # The mapping between code names and contract terms changes later.
    monkeypatch.setitem(terms.PROPERTIES, "name", "titel_van_de_opdracht")
    monkeypatch.setitem(terms._PROPERTIES_BACK, "titel_van_de_opdracht", "name")
    monkeypatch.delitem(terms._PROPERTIES_BACK, "naam")

    after = await _stored(db_session, quote["id"])
    assert bytes(after.canonical) == canonical
    assert after.snapshot_hash == the_hash == hashlib.sha256(canonical).hexdigest()
    again = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    assert again["snapshot_hash"] == the_hash
    # A quote issued now would differ; the issued one does not follow.
    fresh = await quotes.build_snapshot(db_session, world.assignment)
    assert quotes.snapshot_hash(fresh) != the_hash


async def test_the_database_refuses_a_hash_that_is_not_of_the_bytes(
    act_as, world, db_session
):
    from sqlalchemy.exc import IntegrityError

    quote = await _issue(act_as, world)
    stored = await _stored(db_session, quote["id"])
    savepoint = await db_session.begin_nested()
    stored.canonical = bytes(stored.canonical) + b" "
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await savepoint.rollback()


async def test_received_quote_is_kept_as_received_or_refused(db_session, world):
    contract = {
        "naam": "Opdracht Gamma",
        "context_uris": [],
        "regels": [
            {
                "positie": 1,
                "omschrijving": "Hosting",
                "soort": "vast",
                "jaar": 2026,
                "bedrag": {"bedrag_centen": 150000, "valuta": "EUR"},
                # A field this version does not know stays in the bytes.
                "toelichting_leverancier": "Fictief",
            }
        ],
        "totaal": {"bedrag_centen": 150000, "valuta": "EUR"},
    }
    canonical = rfc8785.dumps(contract)
    stated = hashlib.sha256(canonical).hexdigest()
    arguments = {
        "uri": "https://grip.opdrachtnemer.example/id/offerte/1",
        "issued_at": datetime.now(UTC),
    }
    with pytest.raises(QuoteHashMismatchError):
        await quotes.receive_quote(
            db_session,
            world.assignment.id,
            quote_id=uuid.uuid4(),
            canonical=canonical + b" ",
            claimed_hash=stated,
            **arguments,
        )
    quote = await quotes.receive_quote(
        db_session,
        world.assignment.id,
        quote_id=uuid.uuid4(),
        canonical=canonical,
        claimed_hash=stated,
        **arguments,
    )
    assert bytes(quote.canonical) == canonical and quote.snapshot_hash == stated
    assert quote.total_cents == 150000
    line = quote.snapshot["lines"][0]
    assert line["kind"] == "fixed" and line["toelichting_leverancier"] == "Fictief"


# --- offers ------------------------------------------------------------------


async def test_assignment_is_created_without_a_channel(act_as, world, db_session):
    planner = act_as(world.beheerder)
    plain = await planner.post("/api/assignments", json={"name": "Zonder kanaal"})
    assert plain.status_code == 201, plain.text
    assert "traffic_form" not in plain.json()
    # A caller that still sends the old field is not refused; it is ignored.
    legacy = await planner.post(
        "/api/assignments", json={"name": "Met oud veld", "traffic_form": "federated"}
    )
    assert legacy.status_code == 201, legacy.text
    row = await db_session.get(Assignment, uuid.UUID(legacy.json()["id"]))
    assert row.shared_with_instance_uri is None
    changed = await planner.patch(
        f"/api/assignments/{row.id}", json={"traffic_form": "document"}
    )
    assert changed.status_code == 200, changed.text


async def test_issuing_alone_sends_nothing_and_offers_nothing(
    act_as, world, db_session, identified
):
    register_event_handlers()
    await _connect_client(db_session, world)
    quote = await _issue(act_as, world)
    assert (await db_session.execute(select(FederationOutbox))).scalars().all() == []
    assert quote["offers"] == []
    channels = {c["channel"]: c for c in quote["channels"]}
    assert set(channels) == {"client_instance", "signing_link", "document"}
    assert all(c["available"] for c in channels.values())
    # Nothing was exchanged with the client's instance yet: no suggestion
    # for it, the document is the plain default.
    assert channels["client_instance"]["suggested"] is False
    assert channels["document"]["suggested"] is True


async def test_offered_through_the_clients_grip_then_as_document_then_signed_pdf(
    act_as, world, db_session, identified
):
    register_event_handlers()
    await _connect_client(db_session, world)
    quote = await _issue(act_as, world)
    manager = act_as(world.manager)
    path = f"/api/quotes/{quote['id']}/offers"

    first = await manager.post(path, json={"channel": "client_instance"})
    assert first.status_code == 201, first.text
    (offer,) = first.json()["offers"]
    assert offer["channel"] == "client_instance"
    assert offer["recipient"] == CLIENT_INSTANCE and offer["delivery"] == "pending"
    assert offer["offered_by_name"] == world.manager.name
    (out,) = (await db_session.execute(select(FederationOutbox))).scalars().all()
    assert out.operation == "sendQuote"
    assert out.payload["momentopname_hash"] == quote["snapshot_hash"]
    stored = await _stored(db_session, quote["id"])
    assert rfc8785.dumps(out.payload["momentopname"]) == bytes(stored.canonical)
    shared = await db_session.get(Assignment, world.assignment.id)
    assert shared.shared_with_instance_uri == CLIENT_INSTANCE

    # The client's grip stalls; the same quote goes out as a document too.
    second = await manager.post(path, json={"channel": "document"})
    assert second.status_code == 201, second.text
    assert [o["channel"] for o in second.json()["offers"]] == [
        "client_instance",
        "document",
    ]
    # Offering through the client's grip again is the same message, not a new one.
    await manager.post(path, json={"channel": "client_instance"})
    assert (
        len((await db_session.execute(select(FederationOutbox))).scalars().all()) == 1
    )

    signed = await manager.post(
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        data={"signer_name": "Directeur", "signer_email": "d@klant.example"},
        files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
    )
    assert signed.status_code == 201, signed.text
    final = (await manager.get(f"/api/quotes/{quote['id']}")).json()
    assert final["status"] == "accepted"
    assert final["acceptance"]["form"] == "uploaded_pdf"
    acceptances = (
        (
            await db_session.execute(
                select(QuoteAcceptance).where(QuoteAcceptance.quote_id == stored.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(acceptances) == 1
    assert acceptances[0].quote_hash == quote["snapshot_hash"]
    offers = (
        (
            await db_session.execute(
                select(QuoteOffer).where(QuoteOffer.quote_id == stored.id)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(o.channel for o in offers) == [
        "client_instance",
        "client_instance",
        "document",
    ]
    # A decided quote cannot be offered again, through any channel.
    assert all(not c["available"] for c in final["channels"])
    late = await manager.post(path, json={"channel": "document"})
    assert late.status_code in (400, 409, 422)


@pytest.mark.parametrize(
    "setup,expected",
    [
        ("no_identity", "TOOI-URI is niet ingesteld"),
        ("no_instance", "gebruikt grip nog niet"),
        ("no_peer", "niet gekoppeld"),
        ("no_grant", "geen contract"),
        ("exchange_off", "staat uit"),
    ],
)
async def test_clients_grip_is_refused_with_a_reason_when_not_connected(
    act_as, world, db_session, monkeypatch, setup, expected
):
    if setup != "exchange_off":
        register_event_handlers()
    if setup != "no_identity":
        monkeypatch.setattr(
            get_settings(),
            "INSTANCE_TOOI_URI",
            "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
        )
    organisation = await db_session.get(
        Organisation, world.assignment.client_organisation_id
    )
    if setup == "no_peer":
        organisation.instance_uri = CLIENT_INSTANCE
    elif setup == "no_grant":
        await _connect_client(db_session, world, grant=False)
    elif setup == "no_identity":
        await _connect_client(db_session, world)
    elif setup == "exchange_off":
        organisation.instance_uri = CLIENT_INSTANCE
    await db_session.flush()

    quote = await _issue(act_as, world)
    channel = {c["channel"]: c for c in quote["channels"]}["client_instance"]
    assert channel["available"] is False and expected in channel["reason"]

    response = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/offers", json={"channel": "client_instance"}
    )
    assert response.status_code in (400, 409, 422), response.text
    assert expected in response.json()["detail"]
    assert (await db_session.execute(select(QuoteOffer))).scalars().all() == []
    assert (await db_session.execute(select(FederationOutbox))).scalars().all() == []


async def test_signing_link_is_a_channel_and_an_invitation_is_an_offer(
    act_as, world, db_session
):
    quote = await _issue(act_as, world)
    manager = act_as(world.manager)
    missing = await manager.post(
        f"/api/quotes/{quote['id']}/offers", json={"channel": "signing_link"}
    )
    assert missing.status_code in (400, 422), "needs the address of the signer"
    offered = await manager.post(
        f"/api/quotes/{quote['id']}/offers",
        json={"channel": "signing_link", "email": world.signer.email},
    )
    assert offered.status_code == 201, offered.text
    (offer,) = offered.json()["offers"]
    assert (
        offer["channel"] == "signing_link" and offer["recipient"] == world.signer.email
    )
    # The invited person can sign, as with an invitation made the old way.
    assert (
        await act_as(world.signer).get(f"/api/signing/quotes/{quote['id']}")
    ).status_code == 200
    # And an invitation through the existing route is recorded as an offer.
    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": "tweede@klant.example"}
    )
    detail = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    assert [o["recipient"] for o in detail["offers"]] == [
        world.signer.email,
        "tweede@klant.example",
    ]


async def test_only_who_may_issue_may_offer_and_a_reader_sees_no_offers(act_as, world):
    quote = await _issue(act_as, world)
    refused = await act_as(world.planner).post(
        f"/api/quotes/{quote['id']}/offers", json={"channel": "document"}
    )
    assert refused.status_code in (403, 404)
    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/offers", json={"channel": "document"}
    )
    for reader in (world.planner, world.outsider):
        response = await act_as(reader).get(f"/api/quotes/{quote['id']}")
        if response.status_code == 200:
            assert not response.json().get("offers")


def test_channel_port_is_closed_until_someone_answers():
    quote_channels.clear()
    assert quote_channels._connection_check is None
