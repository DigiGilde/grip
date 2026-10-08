"""Quotes: frozen snapshot, stable hash, acceptance in three forms."""

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from grip.models.quote import Quote
from grip.services import assignments, events, quotes, rates
from grip.services.canonical import canonical_json, snapshot_hash
from grip.services.errors import (
    DomainValidationError,
    QuoteAlreadyDecidedError,
    QuoteHashMismatchError,
)

ORG = {
    "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
    "name": "Voorbeeldministerie",
}


@pytest.fixture
async def quoted(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    await add_personnel_line(assignment)
    await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Hosting",
        kind="fixed",
        amount_cents=15_000_00,
        year=2026,
        actor=beheerder,
    )
    quote = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    return assignment, quote


async def test_quote_adds_up_to_the_budget(db_session, quoted):
    assignment, quote = quoted
    snapshot = quote.snapshot

    assert quote.total_cents == 172_800_00 + 15_000_00
    assert snapshot["total"] == {"amount_cents": 187_800_00, "currency": "EUR"}
    assert (
        sum(line["amount"]["amount_cents"] for line in snapshot["lines"])
        == quote.total_cents
    )
    assert snapshot["subtotals_per_year"] == [
        {"year": 2026, "amount": {"amount_cents": 187_800_00, "currency": "EUR"}}
    ]
    personnel = snapshot["lines"][0]
    assert personnel["fte"] == "0.8"
    assert personnel["monthly_rate"] == {"amount_cents": 18_000_00, "currency": "EUR"}
    assert assignment.status == "quoted"


async def test_hash_is_sha256_over_the_stored_canonical_form(quoted):
    _, quote = quoted
    # The hash is over the stored bytes, nothing else.
    assert quote.snapshot_hash == hashlib.sha256(quote.canonical).hexdigest()
    # The bytes are the content in contract terms as canonical JSON.
    # Independent of rfc8785: for this content (ASCII keys, integers and
    # strings only) canonical JSON equals sorted keys without whitespace.
    contract = json.loads(quote.canonical)
    assert contract["naam"] == quote.snapshot["name"] and "name" not in contract
    assert contract["regels"][0]["soort"] == "personeel"
    assert (
        quote.canonical
        == json.dumps(
            contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )
    # What a screen reads is derived from those bytes, in code names.
    assert quote.snapshot["lines"][0]["kind"] == "personnel"
    assert canonical_json({"b": 1, "a": "x"}) == b'{"a":"x","b":1}'


async def test_issued_quote_does_not_change_when_rates_change(
    db_session, quoted, beheerder
):
    assignment, quote = quoted
    before = json.dumps(quote.snapshot, sort_keys=True)
    before_bytes = bytes(quote.canonical)
    before_hash = quote.snapshot_hash

    await rates.set_rate_band(db_session, 2026, "D", 20_000_00, actor=beheerder)
    stored = (
        await db_session.execute(
            select(Quote)
            .where(Quote.id == quote.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert json.dumps(stored.snapshot, sort_keys=True) == before
    assert bytes(stored.canonical) == before_bytes
    assert stored.snapshot_hash == before_hash
    # A new quote does see the new rate.
    fresh = await quotes.build_snapshot(db_session, assignment)
    assert fresh["lines"][0]["monthly_rate"]["amount_cents"] == 20_000_00
    assert snapshot_hash(fresh) != before_hash


async def test_new_quote_supersedes_the_open_one(db_session, quoted, beheerder):
    assignment, first = quoted
    second = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)

    assert first.status == "superseded"
    assert second.status == "issued"


async def test_accept_with_uploaded_pdf(db_session, quoted, beheerder):
    assignment, quote = quoted
    seen = []

    async def handler(session, event_type, payload):
        seen.append((event_type, payload))

    events.register_handler(events.QUOTE_ACCEPTED, handler)

    acceptance = await quotes.accept_quote(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name="Tekenbevoegde",
        signer_email="Teken@Example.org",
        organisation=ORG,
        form="uploaded_pdf",
        document_sha256="a" * 64,
        actor=beheerder,
    )

    assert acceptance.quote_hash == quote.snapshot_hash
    assert acceptance.signer_email == "teken@example.org"
    assert quote.status == "accepted"
    assert assignment.status == "accepted"
    assert assignment.quoted_amount_cents == quote.total_cents
    assert [e for e, _ in seen] == [events.QUOTE_ACCEPTED]
    assert seen[0][1]["quote_hash"] == quote.snapshot_hash
    assert seen[0][1]["origin"] == "local"


async def test_accept_with_wrong_hash_is_refused(db_session, quoted, beheerder):
    _, quote = quoted
    with pytest.raises(QuoteHashMismatchError):
        await quotes.accept_quote(
            db_session,
            quote.id,
            quote_hash="0" * 64,
            signer_name="Tekenbevoegde",
            signer_email="teken@example.org",
            organisation=ORG,
            form="uploaded_pdf",
            document_sha256="a" * 64,
            actor=beheerder,
        )
    assert quote.status == "issued"


async def test_own_instance_needs_a_signature(db_session, quoted):
    _, quote = quoted
    with pytest.raises(DomainValidationError):
        await quotes.accept_quote(
            db_session,
            quote.id,
            quote_hash=quote.snapshot_hash,
            signer_name="Tekenbevoegde",
            signer_email="teken@example.org",
            organisation=ORG,
            form="own_instance",
        )


async def test_own_instance_is_idempotent_on_the_message_id(db_session, quoted):
    _, quote = quoted
    message_id = uuid.uuid4()
    kwargs = dict(
        quote_hash=quote.snapshot_hash,
        signer_name="Tekenbevoegde",
        signer_email="teken@example.org",
        organisation=ORG,
        form="own_instance",
        jws="aaa.bbb.ccc",
        acceptance_id=message_id,
        origin="remote",
    )
    first = await quotes.accept_quote(db_session, quote.id, **kwargs)
    again = await quotes.accept_quote(db_session, quote.id, **kwargs)

    assert again.id == first.id == message_id


async def test_signing_link_needs_an_invitation(db_session, quoted, beheerder):
    _, quote = quoted
    kwargs = dict(
        quote_hash=quote.snapshot_hash,
        signer_name="Gast",
        signer_email="gast@example.org",
        organisation=ORG,
        form="signing_link",
    )
    with pytest.raises(DomainValidationError):
        await quotes.accept_quote(db_session, quote.id, **kwargs)

    invitation = await quotes.invite_signer(
        db_session, quote.id, "Gast@Example.org", actor=beheerder
    )
    await quotes.accept_quote(db_session, quote.id, **kwargs)

    assert invitation.used_at is not None


async def test_reject_and_decide_only_once(db_session, quoted, beheerder):
    assignment, quote = quoted
    await quotes.reject_quote(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        reason="Te duur",
        actor=beheerder,
    )
    assert quote.status == "rejected"
    assert assignment.status == "rejected"

    with pytest.raises(QuoteAlreadyDecidedError):
        await quotes.accept_quote(
            db_session,
            quote.id,
            quote_hash=quote.snapshot_hash,
            signer_name="Tekenbevoegde",
            signer_email="teken@example.org",
            organisation=ORG,
            form="uploaded_pdf",
            document_sha256="a" * 64,
            actor=beheerder,
        )


async def test_quote_over_two_years_lists_rates_per_year(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    await add_personnel_line(
        assignment, fte="1", start=date(2026, 7, 1), end=date(2027, 6, 30)
    )
    quote = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    line = quote.snapshot["lines"][0]

    assert "monthly_rate" not in line
    assert [r["year"] for r in line["monthly_rates_per_year"]] == [2026, 2027]
    assert [s["year"] for s in quote.snapshot["subtotals_per_year"]] == [2026, 2027]
    assert quote.total_cents == 6 * 18_000_00 + 6 * 18_900_00


async def test_received_quote_with_wrong_hash_is_refused(db_session, make_assignment):
    assignment = await make_assignment()
    snapshot = {
        "name": "Opdracht Alfa",
        "context_refs": [],
        "lines": [
            {
                "position": 1,
                "description": "Hosting",
                "kind": "fixed",
                "amount": {"amount_cents": 100, "currency": "EUR"},
            }
        ],
        "total": {"amount_cents": 100, "currency": "EUR"},
    }
    from datetime import UTC, datetime

    with pytest.raises(QuoteHashMismatchError):
        await quotes.receive_quote(
            db_session,
            assignment.id,
            quote_id=uuid.uuid4(),
            uri="https://grip.opdrachtnemer.example/id/offerte/1",
            snapshot=snapshot,
            claimed_hash="0" * 64,
            issued_at=datetime.now(UTC),
        )
    quote = await quotes.receive_quote(
        db_session,
        assignment.id,
        quote_id=uuid.uuid4(),
        uri="https://grip.opdrachtnemer.example/id/offerte/2",
        snapshot=snapshot,
        claimed_hash=snapshot_hash(snapshot),
        issued_at=datetime.now(UTC),
    )
    assert quote.total_cents == 100
    assert assignment.status == "quoted"


async def test_fte_is_exact_text():
    assert quotes._decimal_text(Decimal("0.800")) == "0.8"
    assert quotes._decimal_text(Decimal("1.000")) == "1"
    assert quotes._decimal_text(Decimal("10")) == "10"
