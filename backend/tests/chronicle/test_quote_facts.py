"""Every write to a quote and what hangs from it is a fact.

All names and amounts are fictional.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from grip import calc
from grip.chronicle import guard, words
from grip.chronicle.facts import FACTS, title_of
from grip.chronicle.ledger import Gram
from grip.chronicle.rates import FACT as RATES_FACT
from grip.chronicle.verify import differences
from grip.chronicle.writer import RATE_BOOK, SUBJECT_KIND, event_type
from grip.core import clock
from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.config import get_settings
from grip.events import context as event_context
from grip.federation import signing
from grip.federation.bridge import register_bridge
from grip.federation.bridge.acceptance import reject_received_quote
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.bridge.settings import get_bridge_settings
from grip.federation.inbox import process_pending
from grip.federation.models import FederationInbox
from grip.federation.registry import clear_registries
from grip.models.assignment import Assignment
from grip.models.quote import (
    Quote,
    QuoteAcceptance,
    QuoteApproval,
    QuoteInvitation,
    QuoteOffer,
    QuoteRejection,
)
from grip.models.role import PersonRole
from grip.models.stored_document import StoredDocument
from grip.models.stream_event import StreamEvent
from grip.repositories.chronicle import ChronicleRepository
from grip.repositories.domain import AssignmentRepository
from grip.services import (
    assignments,
    instance_settings,
    pricing,
    quote_approval,
    quote_budget,
    quote_channels,
    quote_files,
    quote_views,
    quotes,
    rates,
    stored_documents,
)
from grip.services.canonical import hash_of
from grip.services.errors import (
    DomainValidationError,
    IllegalTransitionError,
    QuoteAlreadyDecidedError,
    QuoteHashMismatchError,
)
from grip.services.quote_content import line_source
from grip.services.stale import StaleWriteError
from tests.chronicle.test_two_at_once import _while_it_waits
from tests.federation.conftest import (
    CLIENT_BASE,
    CLIENT_PEER_ID,
    CONTRACTOR_PEER_ID,
    as_peer,
    example,
    t,
)

INSTANCE = "https://grip.voorbeeld.example"
SIGNER = "tekenaar@voorbeeld.example"
ORGANISATION = {"name": "Voorbeeldorganisatie"}
PDF = b"%PDF-1.4\n%voorbeeld\n"
FEDERATED_ASSIGNMENT_ID = "3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60"


async def _grams(session, assignment_id: UUID) -> list[Gram]:
    return await ChronicleRepository(session).grams(assignment_id)


async def _facts(session, assignment_id: UUID) -> list[str]:
    return [gram.fact for gram in await _grams(session, assignment_id)]


async def _last(session, assignment_id: UUID) -> Gram:
    return (await _grams(session, assignment_id))[-1]


async def _same(session, assignment_id: UUID) -> None:
    await session.flush()
    report = await differences(session, assignment_id)
    assert report.checked, report.reason
    assert report.differences == [], [str(item) for item in report.differences]


async def _types(session, assignment_id: UUID) -> list[str]:
    """Audit rows and domain events of a case, oldest first."""
    rows = await session.scalars(
        select(StreamEvent)
        .where(StreamEvent.subject_kind != SUBJECT_KIND)
        .order_by(StreamEvent.seq)
    )
    return [
        row.type
        for row in rows
        if row.case_id == assignment_id
        or (row.payload or {}).get("assignment_id") == str(assignment_id)
    ]


async def _active_card(session, year: int = 2026, cents: int = 1800000) -> None:
    await rates.create_rate_card(session, year, actor=None)
    await rates.set_rate_band(session, year, "D", cents, actor=None)
    await rates.set_scale_band(session, year, 14, "D", actor=None)
    await rates.set_rate_card_status(session, year, "active", actor=None)


@pytest.fixture
async def owner(create_person):
    return await create_person("eigenaar@example.org", name="Priya Voorbeeld")


@pytest.fixture
async def approver(create_person):
    return await create_person(
        "goedkeurder@example.org",
        name="Wim Voorbeeld",
        functions=[quote_approval.APPROVER_FUNCTION],
    )


@pytest.fixture
async def case(db_session, owner):
    """A draft with a client and one priced line."""
    await _active_card(db_session)
    client = await assignments.upsert_organisation(
        db_session,
        name="Voorbeeldorganisatie",
        tooi_uri="https://identifier.overheid.nl/tooi/id/voorbeeld/1",
        instance_uri=f"{INSTANCE}/",
    )
    assignment = await assignments.create_assignment(
        db_session,
        name="Voorbeeldopdracht",
        actor=owner,
        client_organisation_id=client.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Voorbeeldregel",
        kind="personnel",
        fte=Decimal("0.8"),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        actor=owner,
    )
    return assignment


@pytest.fixture
async def quote(db_session, case, owner):
    return await quotes.issue_quote(db_session, case.id, actor=owner)


@pytest.fixture
async def other_request(db_session):
    """A second request on the connection of the test: it reads what the first
    flushed without a commit, so it shows the stale read and not the wait."""
    session = AsyncSession(bind=db_session.bind, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
def connected():
    async def check(_db, _uri):
        return None

    quote_channels.register_connection_check(check)
    yield
    quote_channels.clear()


async def _accept_pdf(session, quote, actor, **values) -> QuoteAcceptance:
    return await quote_views.accept_with_uploaded_pdf(
        session,
        quote.id,
        actor=actor,
        content=PDF,
        filename="getekend.pdf",
        content_type="application/pdf",
        signer_name="Directeur Voorbeeld",
        signer_email="directeur@voorbeeld.example",
        **values,
    )


# -- making a quote -----------------------------------------------------------


async def test_issuing_is_one_fact_with_everything_that_arose(db_session, case, owner):
    before = await _facts(db_session, case.id)
    quote = await quotes.issue_quote(db_session, case.id, actor=owner)
    assert await _facts(db_session, case.id) == [*before, "quote_issued"]

    gram = await _last(db_session, case.id)
    assert gram.fields["supersedes"] == []
    assert gram.fields["assignment"] == {
        "quote_date": clock.local_date(quote.issued_at).isoformat(),
        "status": "quoted",
    }
    row = gram.fields["quote"]
    assert base64.b64decode(row["canonical"]) == quote.canonical
    assert row["document_origin"] == "issue"
    assert row["document_sha256"] == quote.document_sha256
    assert gram.basis == {
        "rate_cards": [
            {
                "id": str((await rates.get_card(db_session, 2026)).id),
                "name": "Tarieven 2026",
            }
        ]
    }
    assert gram.refs == {
        "quote_hash": quote.snapshot_hash,
        "document_sha256": quote.document_sha256,
    }
    assert gram.effective_on == clock.local_date(quote.issued_at).isoformat()
    assert case.status == "quoted"
    assert quote.document_fixed_at == quote.issued_at
    await _same(db_session, case.id)


async def test_issuing_writes_the_same_audit_rows_in_the_same_order(
    db_session, case, owner
):
    before = len(await _types(db_session, case.id))
    await quotes.issue_quote(db_session, case.id, actor=owner)
    assert (await _types(db_session, case.id))[before:] == [
        "assignment.updated",
        "quote.created",
        "assignment.status_changed",
        "quote.issued",
    ]


async def test_a_new_quote_replaces_the_open_one_inside_its_fact(
    db_session, case, owner, quote
):
    second = await quotes.issue_quote(db_session, case.id, actor=owner)
    gram = await _last(db_session, case.id)
    assert gram.fact == "quote_issued"
    assert gram.fields["supersedes"] == [str(quote.id)]
    assert "status" not in gram.fields["assignment"], "it stays quoted"
    assert quote.status == "superseded" and second.status == "issued"
    await _same(db_session, case.id)


async def test_a_quote_that_cannot_be_laid_out_leaves_no_fact(
    db_session, case, owner, monkeypatch
):
    def broken(*_args):
        raise RuntimeError("geen lettertype")

    monkeypatch.setattr(quote_files, "render_quote_pdf", broken)
    before = await _facts(db_session, case.id)
    with pytest.raises(quote_files.QuoteDocumentError):
        await quotes.issue_quote(db_session, case.id, actor=owner)
    assert await _facts(db_session, case.id) == before
    assert case.status == "draft"


async def test_the_budget_part_is_what_a_quote_holds(db_session, case):
    snapshot = await quotes.build_snapshot(db_session, case)
    lines = await AssignmentRepository(db_session).budget_lines([case.id])
    part = quotes.budget_part(
        [line_source(line) for line in lines],
        await pricing.load_rate_book(db_session),
        pricing.DEFAULT_OPTIONS,
    )
    assert set(part) == {"lines", "subtotals_per_year", "total"}
    assert quote_budget.budget_fingerprint(part) == quote_budget.budget_fingerprint(
        snapshot
    )


async def test_a_budget_change_is_still_seen_against_the_quote(
    db_session, case, owner, quote
):
    assert (await quote_budget.budget_moved(db_session, case))[0] is False
    await assignments.add_budget_line(
        db_session,
        case.id,
        description="Nog een regel",
        kind="fixed",
        amount_cents=150000,
        year=2026,
        actor=owner,
    )
    assert (await quote_budget.budget_moved(db_session, case))[0] is True
    await _same(db_session, case.id)


# -- a quote from elsewhere, by hand ------------------------------------------


async def _content(session, case) -> tuple[dict, str]:
    snapshot = await quotes.build_snapshot(session, case)
    return snapshot, hash_of(quotes.canonical_form(snapshot))


async def test_receiving_is_one_fact_and_no_audit_row_of_a_quote(db_session, case):
    snapshot, claimed = await _content(db_session, case)
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    quote_id = uuid.uuid4()
    issued = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
    quote = await quotes.receive_quote(
        db_session,
        case.id,
        quote_id=quote_id,
        uri=f"https://grip.ander.example/id/offerte/{quote_id}",
        claimed_hash=claimed,
        issued_at=issued,
        snapshot=snapshot,
    )
    assert await _facts(db_session, case.id) == [*before, "quote_received"]
    gram = await _last(db_session, case.id)
    assert "received" not in gram.fields, "typed over by hand, not from a peer"
    assert gram.effective_on == "2026-03-02"
    assert gram.fields["assignment"]["status"] == "quoted"
    assert (await _types(db_session, case.id))[audit_before:] == [
        "assignment.updated",
        "assignment.status_changed",
    ]
    assert case.quote_date == date(2026, 3, 2)
    await _same(db_session, case.id)

    again = await quotes.receive_quote(
        db_session,
        case.id,
        quote_id=quote_id,
        uri=quote.uri,
        claimed_hash=claimed,
        issued_at=issued,
        snapshot=snapshot,
    )
    assert again is quote
    assert await _facts(db_session, case.id) == [*before, "quote_received"]


async def test_a_received_quote_that_is_refused_leaves_no_fact(db_session, case, owner):
    snapshot, claimed = await _content(db_session, case)
    before = await _facts(db_session, case.id)
    with pytest.raises(QuoteHashMismatchError):
        await quotes.receive_quote(
            db_session,
            case.id,
            quote_id=uuid.uuid4(),
            uri=f"https://grip.ander.example/id/offerte/{uuid.uuid4()}",
            claimed_hash="0" * 64,
            issued_at=datetime.now(UTC),
            snapshot=snapshot,
        )
    assert await _facts(db_session, case.id) == before

    await assignments.transition(db_session, case.id, "cancelled", actor=owner)
    before = await _facts(db_session, case.id)
    with pytest.raises(IllegalTransitionError):
        await quotes.receive_quote(
            db_session,
            case.id,
            quote_id=uuid.uuid4(),
            uri=f"https://grip.ander.example/id/offerte/{uuid.uuid4()}",
            claimed_hash=claimed,
            issued_at=datetime.now(UTC),
            snapshot=snapshot,
        )
    assert await _facts(db_session, case.id) == before
    await _same(db_session, case.id)


async def test_a_moment_without_a_zone_is_read_as_utc(db_session, case):
    snapshot, claimed = await _content(db_session, case)
    quote_id = uuid.uuid4()
    quote = await quotes.receive_quote(
        db_session,
        case.id,
        quote_id=quote_id,
        uri=f"https://grip.ander.example/id/offerte/{quote_id}",
        claimed_hash=claimed,
        issued_at=datetime(2026, 3, 2, 9, 0),
        snapshot=snapshot,
    )
    assert quote.issued_at == datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
    await _same(db_session, case.id)


# -- the file of a quote ------------------------------------------------------


async def test_a_late_file_is_a_fact_with_its_audit_row(db_session, case):
    snapshot, claimed = await _content(db_session, case)
    quote_id = uuid.uuid4()
    quote = await quotes.receive_quote(
        db_session,
        case.id,
        quote_id=quote_id,
        uri=f"https://grip.ander.example/id/offerte/{quote_id}",
        claimed_hash=claimed,
        issued_at=datetime.now(UTC),
        snapshot=snapshot,
    )
    assert quote.document_ref is None
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))

    kept = await quote_files.file_of(db_session, quote)
    assert await _facts(db_session, case.id) == [*before, "quote_document_fixed"]
    gram = await _last(db_session, case.id)
    assert gram.fields["document_origin"] == quote_files.ORIGIN_RECEIVED
    assert gram.refs == {"document_sha256": kept.sha256}
    assert (await _types(db_session, case.id))[audit_before:] == ["quote.updated"]
    await _same(db_session, case.id)

    await quote_files.file_of(db_session, quote)
    assert await _facts(db_session, case.id) == [*before, "quote_document_fixed"]


async def test_opening_a_file_is_no_act_of_who_opens_it(
    client, db_session, case, owner
):
    snapshot, claimed = await _content(db_session, case)
    quote_id = uuid.uuid4()
    await quotes.receive_quote(
        db_session,
        case.id,
        quote_id=quote_id,
        uri=f"https://grip.ander.example/id/offerte/{quote_id}",
        claimed_hash=claimed,
        issued_at=datetime.now(UTC),
        snapshot=snapshot,
    )
    client.cookies.set(DEV_PERSON_COOKIE, str(owner.id))
    trace = "a" * 32
    opened = await client.get(
        f"/api/quotes/{quote_id}/document",
        headers={"traceparent": f"00-{trace}-{'b' * 16}-01"},
    )
    assert opened.status_code == 200, opened.text

    gram = await _last(db_session, case.id)
    assert gram.fact == "quote_document_fixed"
    assert gram.actor_person_id is None and gram.actor_kind == "system"
    assert gram.actor_ref == "quote_files.fix_document"
    assert gram.correlation_id == trace
    moments = (await client.get(f"/api/assignments/{case.id}/chronicle")).json()
    assert moments["items"][-1]["fact"] == "quote_document_fixed"
    assert moments["items"][-1]["actor_name"] is None
    assert moments["items"][-1]["actor_kind"] == "system"

    audit = await db_session.scalar(
        select(StreamEvent).where(
            StreamEvent.type == "quote.updated",
            StreamEvent.subject_id == str(quote_id),
        )
    )
    assert audit.correlation_id == trace
    assert audit.actor_person_id is None and audit.actor_kind == "system"
    assert audit.actor_ref == "quote_files.fix_document"
    assert (
        await ChronicleRepository(db_session).act_end(
            gram.seq, gram.correlation_id, gram.occurred_at, None
        )
        >= audit.seq
    )


# -- offering -----------------------------------------------------------------


async def test_offering_a_document_is_one_fact(db_session, case, owner, quote):
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    offer = await quotes.offer_quote(db_session, quote.id, "document", actor=owner)
    assert await _facts(db_session, case.id) == [*before, "quote_offered"]
    gram = await _last(db_session, case.id)
    assert gram.fields["offer"]["id"] == str(offer.id)
    assert gram.fields["invitation"] is None and gram.fields["shared"] is None
    assert (await _types(db_session, case.id))[audit_before:] == ["quote_offer.created"]
    await _same(db_session, case.id)


async def test_offering_by_link_is_one_fact_with_a_new_invitation(
    db_session, case, owner, quote
):
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    offer = await quotes.offer_quote(
        db_session, quote.id, "signing_link", actor=owner, email=f"  {SIGNER} "
    )
    assert await _facts(db_session, case.id) == [*before, "quote_offered"]
    gram = await _last(db_session, case.id)
    assert offer.recipient == SIGNER and offer.invitation_id is not None
    assert gram.fields["invitation"]["id"] == str(offer.invitation_id)
    assert gram.fields["invitation"]["expires_at"] is not None
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_offer.created",
        "quote_invitation.created",
    ]
    await _same(db_session, case.id)


async def test_offering_a_known_address_again_renews_inside_the_fact(
    db_session, case, owner, quote
):
    first = await quotes.offer_quote(
        db_session, quote.id, "signing_link", actor=owner, email=SIGNER
    )
    await quotes.withdraw_invitation(
        db_session, quote.id, first.invitation_id, actor=owner
    )
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    until = datetime(2027, 1, 1, tzinfo=UTC)
    second = await quotes.offer_quote(
        db_session,
        quote.id,
        "signing_link",
        actor=owner,
        email=SIGNER.upper(),
        expires_at=until,
    )
    assert await _facts(db_session, case.id) == [*before, "quote_offered"]
    gram = await _last(db_session, case.id)
    assert gram.fields["invitation"] is None
    assert gram.fields["renewed"]["invitation_id"] == str(first.invitation_id)
    assert second.invitation_id == first.invitation_id and second.id != first.id
    invitation = await db_session.get(QuoteInvitation, first.invitation_id)
    assert invitation.withdrawn_at is None and invitation.expires_at == until
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_invitation.updated",
        "quote_offer.created",
    ]
    await _same(db_session, case.id)


async def test_offering_to_the_clients_instance_shares_inside_the_fact(
    db_session, case, owner, quote, connected
):
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    offer = await quotes.offer_quote(
        db_session, quote.id, "client_instance", actor=owner
    )
    assert await _facts(db_session, case.id) == [*before, "quote_offered"]
    gram = await _last(db_session, case.id)
    assert gram.fields["shared"]["shared_with_instance_uri"] == INSTANCE
    assert offer.recipient == INSTANCE and case.shared_with_instance_uri == INSTANCE
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_offer.created",
        "quote.offered",
    ]
    await _same(db_session, case.id)

    shared_at = case.shared_at
    await quotes.offer_quote(db_session, quote.id, "client_instance", actor=owner)
    gram = await _last(db_session, case.id)
    assert gram.fact == "quote_offered" and gram.fields["shared"] is None
    assert case.shared_at == shared_at
    await _same(db_session, case.id)


async def test_inviting_alone_is_an_offer_then_a_renewal(
    db_session, case, owner, quote
):
    before = await _facts(db_session, case.id)
    invitation = await quotes.invite_signer(db_session, quote.id, SIGNER, actor=owner)
    assert await _facts(db_session, case.id) == [*before, "quote_offered"]
    await _same(db_session, case.id)

    audit_before = len(await _types(db_session, case.id))
    until = datetime(2027, 2, 1, tzinfo=UTC)
    again = await quotes.invite_signer(
        db_session, quote.id, SIGNER, actor=owner, expires_at=until
    )
    assert again is invitation
    assert await _facts(db_session, case.id) == [
        *before,
        "quote_offered",
        "invitation_renewed",
    ]
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_invitation.updated"
    ]
    offers = await db_session.scalars(
        select(QuoteOffer).where(QuoteOffer.quote_id == quote.id)
    )
    assert len(list(offers)) == 1, "inviting a known address again offers nothing"
    await _same(db_session, case.id)


async def test_two_openings_of_a_link_at_once_are_one_moment(
    db_session, other_request, case, owner, quote, monkeypatch
):
    await quotes.invite_signer(db_session, quote.id, SIGNER, actor=owner)
    before = await _facts(db_session, case.id)

    async def the_other_opening():
        await quotes.mark_invitation_opened(other_request, quote.id, SIGNER)
        await other_request.flush()

    _while_it_waits(monkeypatch, the_other_opening)
    await quotes.mark_invitation_opened(db_session, quote.id, SIGNER)
    await db_session.flush()

    assert await _facts(db_session, case.id) == [*before, "invitation_opened"]
    await _same(db_session, case.id)


async def test_two_openings_of_a_file_at_once_keep_one_file(
    db_session, other_request, case, monkeypatch
):
    snapshot, claimed = await _content(db_session, case)
    quote_id = uuid.uuid4()
    received = await quotes.receive_quote(
        db_session,
        case.id,
        quote_id=quote_id,
        uri=f"https://grip.ander.example/id/offerte/{quote_id}",
        claimed_hash=claimed,
        issued_at=datetime.now(UTC),
        snapshot=snapshot,
    )
    await db_session.flush()
    before = await _facts(db_session, case.id)

    async def the_other_opening():
        other = await other_request.get(Quote, quote_id)
        await quote_files.fix_document(other_request, other, origin="received")
        await other_request.flush()

    _while_it_waits(monkeypatch, the_other_opening)
    await quote_files.fix_document(db_session, received, origin="received")
    await db_session.flush()

    assert await _facts(db_session, case.id) == [*before, "quote_document_fixed"]
    kept = await db_session.scalar(
        select(func.count())
        .select_from(StoredDocument)
        .where(StoredDocument.owner_id == quote_id)
    )
    assert kept == 1
    assert received.document_ref is not None
    await _same(db_session, case.id)


async def test_a_link_withdrawn_while_it_opens_records_no_opening(
    db_session, other_request, case, owner, quote, monkeypatch
):
    invitation = await quotes.invite_signer(db_session, quote.id, SIGNER, actor=owner)
    before = await _facts(db_session, case.id)

    async def the_withdrawal():
        await quotes.withdraw_invitation(
            other_request, quote.id, invitation.id, actor=None
        )
        await other_request.flush()

    _while_it_waits(monkeypatch, the_withdrawal)
    await quotes.mark_invitation_opened(db_session, quote.id, SIGNER)
    await db_session.flush()

    assert await _facts(db_session, case.id) == [*before, "invitation_withdrawn"]
    await _same(db_session, case.id)


async def test_a_link_withdrawn_renewed_and_opened_is_a_fact_each(
    db_session, case, owner, quote
):
    invitation = await quotes.invite_signer(db_session, quote.id, SIGNER, actor=owner)
    before = await _facts(db_session, case.id)

    await quotes.withdraw_invitation(db_session, quote.id, invitation.id, actor=owner)
    gram = await _last(db_session, case.id)
    assert gram.fact == "invitation_withdrawn"
    assert gram.fields["withdrawn_by_id"] == str(owner.id)
    await _same(db_session, case.id)
    await quotes.withdraw_invitation(db_session, quote.id, invitation.id, actor=owner)

    await quotes.mark_invitation_opened(db_session, quote.id, SIGNER)
    assert (await _last(db_session, case.id)).fact == "invitation_withdrawn", (
        "a withdrawn link opens nothing"
    )

    await quotes.renew_invitation(db_session, quote.id, invitation.id, actor=owner)
    assert (await _last(db_session, case.id)).fact == "invitation_renewed"
    assert invitation.withdrawn_at is None and invitation.withdrawn_by_id is None
    await _same(db_session, case.id)

    await quotes.mark_invitation_opened(db_session, quote.id, f" {SIGNER.upper()} ")
    assert invitation.opened_at is not None
    await quotes.mark_invitation_opened(db_session, quote.id, SIGNER)
    assert await _facts(db_session, case.id) == [
        *before,
        "invitation_withdrawn",
        "invitation_renewed",
        "invitation_opened",
    ]
    await _same(db_session, case.id)


# -- deciding -----------------------------------------------------------------


async def test_a_recorded_pdf_is_one_fact_counting_from_the_day_signed(
    db_session, case, owner, quote
):
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    signed = quote.issued_at.replace(hour=23, minute=30) + timedelta(days=1)
    with clock.at(signed + timedelta(days=2)):
        acceptance = await _accept_pdf(db_session, quote, owner, signed_at=signed)
    assert await _facts(db_session, case.id) == [*before, "quote_accepted"]
    gram = await _last(db_session, case.id)
    assert gram.kind == "executogram"
    assert gram.effective_on == clock.local_date(signed).isoformat()
    assert gram.fields["assignment"] == {
        "status": "accepted",
        "quoted_amount_cents": quote.total_cents,
    }
    assert gram.fields["invitation"] is None
    assert gram.refs == {
        "quote_hash": quote.snapshot_hash,
        "document_sha256": acceptance.document_sha256,
    }
    assert quote.status == "accepted" and case.status == "accepted"
    assert (await _types(db_session, case.id))[audit_before:] == [
        "assignment.updated",
        "assignment.status_changed",
        "quote_acceptance.created",
        "quote.accepted",
    ]
    await _same(db_session, case.id)


async def test_an_agreed_amount_stays_as_it_was(db_session, case, owner, quote):
    await assignments.update_assignment(
        db_session, case.id, actor=owner, quoted_amount_cents=123400
    )
    await _accept_pdf(db_session, quote, owner)
    gram = await _last(db_session, case.id)
    assert gram.fields["assignment"] == {"status": "accepted"}
    assert case.quoted_amount_cents == 123400
    await _same(db_session, case.id)


async def test_signing_by_link_uses_the_invitation_inside_the_fact(
    db_session, case, owner, quote, create_person
):
    invitation = await quotes.invite_signer(db_session, quote.id, SIGNER, actor=owner)
    signer = await create_person(SIGNER, name="Tekenaar Voorbeeld")
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    await quote_views.accept_via_signing_link(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name=signer.name,
        signer_email=SIGNER,
        signer_person_id=signer.id,
        declared_mandate=True,
    )
    assert await _facts(db_session, case.id) == [*before, "quote_accepted"]
    gram = await _last(db_session, case.id)
    assert gram.kind == "decretogram"
    assert gram.fields["declared_mandate"] is True
    assert gram.fields["invitation"]["id"] == str(invitation.id)
    assert gram.fields["invitation"]["person_id"] == str(signer.id)
    assert invitation.used_at is not None and invitation.person_id == signer.id
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_invitation.updated",
        "assignment.updated",
        "assignment.status_changed",
        "quote_acceptance.created",
        "quote.accepted",
    ]
    await _same(db_session, case.id)


async def test_signing_by_link_without_a_person_leaves_it_empty(
    db_session, case, owner, quote
):
    invitation = await quotes.invite_signer(db_session, quote.id, SIGNER, actor=owner)
    await quote_views.accept_via_signing_link(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name="Tekenaar Voorbeeld",
        signer_email=SIGNER,
        signer_person_id=None,
    )
    gram = await _last(db_session, case.id)
    assert "declared_mandate" not in gram.fields
    assert invitation.person_id is None
    await _same(db_session, case.id)


async def test_an_acceptance_that_is_refused_leaves_no_fact(
    db_session, case, owner, quote
):
    before = await _facts(db_session, case.id)
    with pytest.raises(QuoteHashMismatchError):
        await quotes.accept_quote(
            db_session,
            quote.id,
            quote_hash="0" * 64,
            signer_name="Iemand",
            signer_email=SIGNER,
            organisation=ORGANISATION,
            form="uploaded_pdf",
            actor=owner,
            document_sha256="0" * 64,
        )
    with pytest.raises(DomainValidationError):
        await quotes.accept_quote(
            db_session,
            quote.id,
            quote_hash=quote.snapshot_hash,
            signer_name="Iemand",
            signer_email=SIGNER,
            organisation=ORGANISATION,
            form="signing_link",
        )
    await assignments.transition(db_session, case.id, "cancelled", actor=owner)
    cancelled = await _facts(db_session, case.id)
    assert cancelled == [*before, "assignment_status_changed"]
    with pytest.raises(IllegalTransitionError):
        await _accept_pdf(db_session, quote, owner)
    assert await _facts(db_session, case.id) == cancelled
    assert quote.status == "issued"
    await _same(db_session, case.id)


async def test_the_same_acceptance_twice_is_one_fact(db_session, case, owner, quote):
    acceptance_id = uuid.uuid4()

    async def accept():
        return await quotes.accept_quote(
            db_session,
            quote.id,
            quote_hash=quote.snapshot_hash,
            signer_name="Iemand",
            signer_email=SIGNER,
            organisation=ORGANISATION,
            form="own_instance",
            jws="handtekening",
            acceptance_id=acceptance_id,
        )

    first = await accept()
    facts = await _facts(db_session, case.id)
    assert await accept() is first
    assert await _facts(db_session, case.id) == facts
    with pytest.raises(QuoteAlreadyDecidedError):
        await _accept_pdf(db_session, quote, owner)
    await _same(db_session, case.id)


async def test_rejecting_is_one_fact_and_a_new_quote_can_follow(
    db_session, case, owner, quote
):
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    rejected = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
    await quotes.reject_quote(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        actor=owner,
        reason="Te duur",
        rejected_at=rejected,
        statement_hash="a" * 64,
        recorded=True,
    )
    assert await _facts(db_session, case.id) == [*before, "quote_rejected"]
    gram = await _last(db_session, case.id)
    assert gram.kind == "executogram"
    assert gram.fields["assignment"] == {"status": "rejected"}
    assert gram.effective_on == "2026-04-01"
    assert gram.refs == {"quote_hash": quote.snapshot_hash, "statement_hash": "a" * 64}
    assert (await _types(db_session, case.id))[audit_before:] == [
        "assignment.updated",
        "quote.updated",
        "assignment.status_changed",
        "quote.rejected",
    ]
    await _same(db_session, case.id)

    second = await quotes.issue_quote(db_session, case.id, actor=owner)
    gram = await _last(db_session, case.id)
    assert gram.fields["supersedes"] == [], "a rejected quote is not open"
    assert gram.fields["assignment"]["status"] == "quoted"
    assert second.status == "issued" and quote.status == "rejected"
    await _same(db_session, case.id)


@pytest.mark.parametrize("with_person", [True, False])
async def test_who_rejects_through_the_link_decides(
    db_session, case, owner, quote, create_person, with_person
):
    signer = await create_person(SIGNER, name="Tess Voorbeeld")
    await quotes.invite_signer(db_session, quote.id, SIGNER, actor=owner)
    rejection = await quote_views.reject_via_signing_link(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_person_id=signer.id if with_person else None,
        reason=" Past niet ",
    )
    assert rejection.recorded_by_id is None
    gram = await _last(db_session, case.id)
    assert gram.kind == "decretogram"
    assert gram.actor_person_id == (signer.id if with_person else None)
    assert words.statement(gram.fact, gram.fields, actor="Tess Voorbeeld") == (
        "Voorbeeldorganisatie wees de offerte af."
    )
    await _same(db_session, case.id)


async def test_rejecting_in_the_own_instance_is_a_decision(
    db_session, case, owner, quote
):
    rejection = await reject_received_quote(db_session, quote.id, actor=owner)
    assert rejection.recorded_by_id is None
    gram = await _last(db_session, case.id)
    assert gram.kind == "decretogram" and gram.actor_person_id == owner.id
    await _same(db_session, case.id)


async def test_only_who_notes_a_rejection_records_it(db_session, case, owner, quote):
    rejection = await quotes.reject_quote(
        db_session,
        quote.id,
        quote_hash=quote.snapshot_hash,
        actor=owner,
        recorded=True,
    )
    assert rejection.recorded_by_id == owner.id
    gram = await _last(db_session, case.id)
    assert gram.kind == "executogram"
    assert words.statement(gram.fact, gram.fields, actor="Priya Voorbeeld") == (
        "Priya Voorbeeld legde vast dat de opdrachtgever de offerte afwees."
    )
    await _same(db_session, case.id)


async def test_a_recorded_rejection_names_the_client(client, db_session, case, owner):
    quote = await quotes.issue_quote(db_session, case.id, actor=owner)
    client.cookies.set(DEV_PERSON_COOKIE, str(owner.id))

    response = await client.post(
        f"/api/quotes/{quote.id}/rejection", json={"reason": "  Te duur. "}
    )

    assert response.status_code == 201, response.text
    gram = await _last(db_session, case.id)
    assert gram.fields["rejection"]["organisation"]["name"] == "Voorbeeldorganisatie"
    assert gram.fields["rejection"]["reason"] == "Te duur."
    assert gram.fields["rejection"]["recorded_by_id"] == str(owner.id)
    assert gram.kind == "executogram"
    assert words.statement(gram.fact, gram.fields, actor="Priya Voorbeeld") == (
        "Priya Voorbeeld legde vast dat Voorbeeldorganisatie de offerte afwees."
    )
    await _same(db_session, case.id)


async def test_a_recorded_rejection_without_a_client_says_the_client(
    client, db_session, case, owner, quote
):
    await assignments.update_assignment(
        db_session, case.id, actor=owner, client_organisation_id=None
    )
    client.cookies.set(DEV_PERSON_COOKIE, str(owner.id))

    response = await client.post(f"/api/quotes/{quote.id}/rejection", json={})

    assert response.status_code == 201, response.text
    gram = await _last(db_session, case.id)
    assert gram.fields["rejection"]["organisation"] is None
    assert words.statement(gram.fact, gram.fields, actor="Priya Voorbeeld") == (
        "Priya Voorbeeld legde vast dat de opdrachtgever de offerte afwees."
    )


async def test_the_same_rejection_twice_is_one_fact(db_session, case, owner, quote):
    rejection_id = uuid.uuid4()

    async def reject():
        return await quotes.reject_quote(
            db_session,
            quote.id,
            quote_hash=quote.snapshot_hash,
            actor=owner,
            rejection_id=rejection_id,
        )

    first = await reject()
    facts = await _facts(db_session, case.id)
    assert await reject() is first
    assert await _facts(db_session, case.id) == facts


# -- correcting the day of a recorded pdf -------------------------------------


async def test_correcting_the_day_is_a_fact_and_the_earlier_one_stays(
    db_session, case, owner, quote
):
    signed = quote.issued_at + timedelta(days=3)
    corrected = quote.issued_at + timedelta(days=1)
    later = quote.issued_at + timedelta(days=5)
    with clock.at(later):
        acceptance = await _accept_pdf(db_session, quote, owner, signed_at=signed)
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))

    with clock.at(later):
        same = await quotes.correct_acceptance_date(
            db_session, quote.id, corrected, "  Datum verkeerd overgenomen ", owner
        )
    assert same is acceptance and acceptance.signed_at == corrected
    assert await _facts(db_session, case.id) == [*before, "acceptance_date_corrected"]
    gram = await _last(db_session, case.id)
    assert gram.effective_on == clock.local_date(corrected).isoformat()
    assert gram.fields["acceptance_id"] == str(acceptance.id)
    assert gram.fields["reason"] == "Datum verkeerd overgenomen"
    assert datetime.fromisoformat(gram.fields["was"]) == signed
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_acceptance.updated"
    ]
    assert any(
        item.fact == "quote_accepted"
        and datetime.fromisoformat(item.fields["acceptance"]["signed_at"]) == signed
        for item in await _grams(db_session, case.id)
    )
    await _same(db_session, case.id)

    facts = await _facts(db_session, case.id)
    with (
        clock.at(later),
        pytest.raises(DomainValidationError, match="al is vastgelegd"),
    ):
        await quotes.correct_acceptance_date(
            db_session, quote.id, corrected, "Nog eens", owner
        )
    assert await _facts(db_session, case.id) == facts, "nothing changes, nothing said"


async def test_only_a_recorded_pdf_with_a_reason_is_corrected(
    db_session, case, owner, quote
):
    moment = datetime(2026, 2, 27, 12, 0, tzinfo=UTC)
    with pytest.raises(quotes.NotFoundError):
        await quotes.correct_acceptance_date(db_session, quote.id, moment, "x", owner)
    await _accept_pdf(db_session, quote, owner)
    for blank in ("", "   "):
        with pytest.raises(DomainValidationError):
            await quotes.correct_acceptance_date(
                db_session, quote.id, moment, blank, owner
            )

    second_case = await assignments.create_assignment(
        db_session,
        name="Tweede voorbeeld",
        actor=owner,
        client_organisation_id=case.client_organisation_id,
    )
    await assignments.add_budget_line(
        db_session,
        second_case.id,
        description="Voorbeeldregel",
        kind="fixed",
        amount_cents=100000,
        year=2026,
        actor=owner,
    )
    signed_elsewhere = await quotes.issue_quote(db_session, second_case.id, actor=owner)
    await quotes.accept_quote(
        db_session,
        signed_elsewhere.id,
        quote_hash=signed_elsewhere.snapshot_hash,
        signer_name="Iemand",
        signer_email=SIGNER,
        organisation=ORGANISATION,
        form="own_instance",
        jws="handtekening",
    )
    with pytest.raises(DomainValidationError):
        await quotes.correct_acceptance_date(
            db_session, signed_elsewhere.id, moment, "Reden", owner
        )


async def test_a_correction_reads_the_date_again_before_it_says_what_stood(
    db_session, other_request, case, owner, quote
):
    first = quote.issued_at + timedelta(days=1)
    second = quote.issued_at + timedelta(days=2)
    third = quote.issued_at + timedelta(days=3)
    with clock.at(quote.issued_at + timedelta(days=5)):
        await _accept_pdf(db_session, quote, owner, signed_at=first)
        seen = await other_request.scalar(
            select(QuoteAcceptance).where(QuoteAcceptance.quote_id == quote.id)
        )
        assert seen.signed_at == first

        await quotes.correct_acceptance_date(
            db_session, quote.id, second, "Eerst", owner
        )
        assert seen.signed_at == first, "this request still holds what it read"

        with pytest.raises(StaleWriteError) as stale:
            await quotes.correct_acceptance_date(
                other_request,
                quote.id,
                third,
                "Later",
                owner,
                expected_signed_at=first,
            )
        assert stale.value.changed_by == "Priya Voorbeeld"

        await quotes.correct_acceptance_date(
            other_request, quote.id, third, "Later", owner
        )
        await other_request.flush()

    gram = await _last(db_session, case.id)
    assert datetime.fromisoformat(gram.fields["was"]) == second
    assert words.statement(gram.fact, gram.fields, actor="Pim Voorbeeld") == (
        "Pim Voorbeeld corrigeerde de datum van tekenen "
        f"van {words.day_words(second)} naar {words.day_words(third)}."
    )
    report = await differences(db_session, case.id)
    assert report.checked and report.differences == []


# -- internal approval --------------------------------------------------------


async def test_asking_approval_records_the_rule_that_applied(
    db_session, case, owner, quote
):
    await instance_settings.set_values(
        db_session,
        {quote_approval.MODE.key: "from_amount", quote_approval.THRESHOLD.key: 100},
        actor=None,
    )
    before = await _facts(db_session, case.id)
    audit_before = len(await _types(db_session, case.id))
    approval = await quote_approval.request_approval(
        db_session, quote.id, actor=owner, note=" Graag vandaag "
    )
    assert await _facts(db_session, case.id) == [*before, "approval_requested"]
    gram = await _last(db_session, case.id)
    assert gram.basis == {"mode": "from_amount", "threshold_cents": 100}
    assert gram.fields["approval"]["request_note"] == "Graag vandaag"
    assert approval.status == "requested"
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_approval.created",
        "quote_approval.requested",
    ]
    await _same(db_session, case.id)


async def test_approving_counts_from_the_moment_in_the_statement(
    db_session, case, owner, approver, quote
):
    await quote_approval.request_approval(db_session, quote.id, actor=owner)
    audit_before = len(await _types(db_session, case.id))
    moment = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    approval = await quote_approval.decide(
        db_session,
        quote.id,
        approve=True,
        actor=approver,
        quote_hash=quote.snapshot_hash,
        statement_hash="b" * 64,
        decided_at=moment,
    )
    gram = await _last(db_session, case.id)
    assert gram.fact == "approval_approved" and gram.kind == "decretogram"
    assert gram.effective_on == "2026-05-01"
    assert gram.fields["decided_by_id"] == str(approver.id)
    assert gram.refs == {"quote_hash": quote.snapshot_hash, "statement_hash": "b" * 64}
    assert approval.status == "approved" and approval.decided_at == moment
    assert (await _types(db_session, case.id))[audit_before:] == [
        "quote_approval.updated",
        "quote_approval.approved",
    ]
    await _same(db_session, case.id)

    await quote_approval.withdraw(db_session, quote.id, actor=owner)
    gram = await _last(db_session, case.id)
    assert gram.fact == "approval_withdrawn"
    assert gram.fields["withdrawn_by_id"] == str(owner.id)
    assert gram.fields["was"] == "approved"
    assert title_of(gram.fact, gram.fields) == "Goedkeuring ingetrokken"
    assert approval.status == "withdrawn"
    await _same(db_session, case.id)


async def test_taking_back_a_request_says_it_was_a_request(
    db_session, case, owner, quote
):
    await quote_approval.request_approval(db_session, quote.id, actor=owner)
    await quote_approval.withdraw(db_session, quote.id, actor=owner)
    gram = await _last(db_session, case.id)
    assert gram.fields["was"] == "requested"
    assert title_of(gram.fact, gram.fields) == "Vraag om goedkeuring ingetrokken"
    assert words.statement(gram.fact, gram.fields, actor=None) == (
        "Vraag om goedkeuring ingetrokken."
    )
    await _same(db_session, case.id)


async def test_taking_back_says_what_stood_and_not_what_was_read_earlier(
    db_session, other_request, case, owner, approver, quote
):
    await quote_approval.request_approval(db_session, quote.id, actor=owner)
    seen = await other_request.scalar(
        select(QuoteApproval).where(QuoteApproval.quote_id == quote.id)
    )
    assert seen.status == "requested"

    await quote_approval.decide(
        db_session,
        quote.id,
        approve=True,
        actor=approver,
        quote_hash=quote.snapshot_hash,
    )
    await quote_approval.withdraw(other_request, quote.id, actor=owner)
    await other_request.flush()

    gram = await _last(db_session, case.id)
    assert gram.fact == "approval_withdrawn" and gram.fields["was"] == "approved"
    assert title_of(gram.fact, gram.fields) == "Goedkeuring ingetrokken"
    report = await differences(db_session, case.id)
    assert report.checked and report.differences == []


async def _allow_self(session) -> None:
    await instance_settings.set_values(
        session, {quote_approval.ALLOW_SELF.key: True}, actor=None
    )


async def test_who_asked_and_approves_is_told_as_who_asked(
    db_session, case, owner, approver, quote
):
    await _allow_self(db_session)
    await quote_approval.request_approval(db_session, quote.id, actor=approver)
    await quote_approval.decide(
        db_session,
        quote.id,
        approve=True,
        actor=approver,
        quote_hash=quote.snapshot_hash,
    )
    gram = await _last(db_session, case.id)
    assert gram.fields["self_approved"] is True and gram.fields["asked_it"] is True
    assert words.statement(gram.fact, gram.fields, actor=None) == (
        "Offerte intern goedgekeurd door wie de goedkeuring zelf vroeg."
    )
    await _same(db_session, case.id)


async def test_who_made_it_and_approves_is_told_as_who_made_it(
    db_session, case, owner, approver, quote
):
    await _allow_self(db_session)
    await quote_approval.request_approval(db_session, quote.id, actor=approver)
    await quote_approval.decide(
        db_session,
        quote.id,
        approve=True,
        actor=owner,
        quote_hash=quote.snapshot_hash,
    )
    gram = await _last(db_session, case.id)
    assert gram.fields["self_approved"] is True and gram.fields["asked_it"] is False
    assert words.statement(gram.fact, gram.fields, actor=None) == (
        "Offerte intern goedgekeurd door wie haar maakte."
    )
    await _same(db_session, case.id)


async def test_a_second_person_who_approves_is_told_as_nothing_more(
    db_session, case, owner, approver, quote
):
    await quote_approval.request_approval(db_session, quote.id, actor=owner)
    await quote_approval.decide(
        db_session,
        quote.id,
        approve=True,
        actor=approver,
        quote_hash=quote.snapshot_hash,
    )
    gram = await _last(db_session, case.id)
    assert gram.fields["self_approved"] is False and gram.fields["asked_it"] is False
    assert words.statement(gram.fact, gram.fields, actor=None) == (
        "Offerte intern goedgekeurd."
    )


async def test_sending_back_needs_a_note_and_then_is_a_fact(
    db_session, case, owner, approver, quote
):
    await quote_approval.request_approval(db_session, quote.id, actor=owner)
    before = await _facts(db_session, case.id)
    with pytest.raises(DomainValidationError):
        await quote_approval.decide(
            db_session,
            quote.id,
            approve=False,
            actor=approver,
            quote_hash=quote.snapshot_hash,
        )
    assert await _facts(db_session, case.id) == before
    approval = await quote_approval.decide(
        db_session,
        quote.id,
        approve=False,
        actor=approver,
        quote_hash=quote.snapshot_hash,
        note=" Het tarief klopt niet ",
    )
    gram = await _last(db_session, case.id)
    assert gram.fact == "approval_sent_back"
    assert "asked_it" not in gram.fields, "nobody approved anything"
    assert gram.effective_on is None, "no moment was given: it counts from now"
    assert gram.fields["decision_note"] == "Het tarief klopt niet"
    assert approval.status == "sent_back"
    await _same(db_session, case.id)


async def test_a_refused_decision_leaves_no_fact(db_session, case, owner, quote):
    await quote_approval.request_approval(db_session, quote.id, actor=owner)
    before = await _facts(db_session, case.id)
    with pytest.raises(DomainValidationError):
        await quote_approval.decide(
            db_session,
            quote.id,
            approve=True,
            actor=owner,
            quote_hash=quote.snapshot_hash,
        )
    assert await _facts(db_session, case.id) == before


def _request(status: str, quote_hash: str = "a") -> SimpleNamespace:
    return SimpleNamespace(status=status, quote_hash=quote_hash)


def test_the_current_request_is_the_latest_in_force_about_these_bytes():
    sent_back, approved = _request("sent_back"), _request("approved")
    other = _request("requested", "b")
    assert quote_approval.current_request([sent_back, approved, other], "a") is approved
    assert quote_approval.current_request([sent_back, other], "a") is None
    assert quote_approval.current_request([], "a") is None


@pytest.mark.parametrize(
    ("mode", "threshold", "total", "required", "reason"),
    [
        ("never", 0, 100, False, None),
        ("always", 0, 100, True, "elke offerte wordt intern goedgekeurd"),
        ("from_amount", 100, 100, True, "vanaf € 1"),
        ("from_amount", 101, 100, False, None),
    ],
)
def test_the_requirement_follows_from_the_setting(
    mode, threshold, total, required, reason
):
    assert quote_approval.requirement_from(
        mode, threshold, total
    ) == quote_approval.Requirement(required, reason)


async def test_an_approver_is_asked_for_on_a_given_day(db_session, create_person):
    person = await create_person("later@example.org", name="Later Voorbeeld")
    db_session.add(
        PersonRole(
            person_id=person.id,
            role_id=quote_approval.APPROVER_FUNCTION,
            start_date=date(2026, 6, 1),
        )
    )
    await db_session.flush()
    assert await quote_approval.approver_available(db_session, on=date(2026, 6, 1))
    assert not await quote_approval.approver_available(db_session, on=date(2026, 5, 31))


# -- a fact in words ----------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "title"),
    [
        ({"from": "draft", "to": "quoted"}, "Offerte als gemaakt gemarkeerd"),
        ({"from": "requested", "to": "quoted"}, "Offerte als gemaakt gemarkeerd"),
        ({"from": "verbally_agreed", "to": "quoted"}, "Terug naar offerte"),
        ({"from": "rejected", "to": "quoted"}, "Terug naar offerte"),
        ({"to": "quoted"}, "Offerte als gemaakt gemarkeerd"),
        ({"from": "draft", "to": "requested"}, "Offerte aangevraagd"),
        (None, "Status gewijzigd"),
    ],
)
def test_a_step_to_a_quote_says_where_it_came_from(fields, title):
    assert title_of("assignment_status_changed", fields) == title


@pytest.mark.parametrize(
    ("target", "kind"),
    [
        ("requested", "executogram"),
        ("verbally_agreed", "executogram"),
        ("accepted", "executogram"),
        ("rejected", "executogram"),
        ("in_progress", "decretogram"),
        ("cancelled", "decretogram"),
        ("completed", "decretogram"),
        ("accounted", "decretogram"),
        ("quoted", "general"),
    ],
)
def test_marking_what_someone_else_asked_is_no_decision(target, kind):
    assert FACTS["assignment_status_changed"].kind_of({"to": target}) == kind


@pytest.mark.parametrize(
    ("fact", "fields", "sentence"),
    [
        (
            "budget_line_changed",
            {"line_id": "x", "changes": {}, "name": "Productmanager"},
            "Begrotingsregel Productmanager gewijzigd.",
        ),
        ("budget_line_changed", {"line_id": "x"}, "Begrotingsregel gewijzigd."),
        (
            "budget_line_changed",
            {"line_id": "x", "name": None},
            "Begrotingsregel gewijzigd.",
        ),
        (
            "budget_line_changed",
            {"line_id": "x", "name": "   "},
            "Begrotingsregel gewijzigd.",
        ),
        (
            "budget_line_removed",
            {"line_id": "x", "name": " Één & <b>twee</b> "},
            "Begrotingsregel Één & <b>twee</b> verwijderd.",
        ),
        ("budget_line_removed", {"line_id": "x"}, "Begrotingsregel verwijderd."),
        (
            "assignment_changed",
            {"changes": {"end_date": "2027-01-01"}},
            "Einddatum van de opdracht gewijzigd.",
        ),
        (
            "assignment_changed",
            {"changes": {"end_date": "2027-01-01", "start_date": "2026-01-01"}},
            "Begindatum en einddatum van de opdracht gewijzigd.",
        ),
        (
            "assignment_changed",
            {
                "changes": {
                    "quoted_amount_cents": 123456,
                    "end_date": "2027-01-01",
                    "name": "Geheime naam",
                }
            },
            "Naam, einddatum en offertebedrag van de opdracht gewijzigd.",
        ),
        (
            "assignment_changed",
            {"changes": {"notes": "Geheime notitie"}},
            "Opdracht gewijzigd.",
        ),
        (
            "assignment_changed",
            {"changes": {"name": "Geheime naam", "notes": "Geheime notitie"}},
            "Opdracht gewijzigd.",
        ),
        ("assignment_changed", {"changes": {}}, "Opdracht gewijzigd."),
        ("assignment_changed", {}, "Opdracht gewijzigd."),
        ("assignment_changed", None, "Opdracht gewijzigd."),
        (
            "approval_withdrawn",
            {"was": "requested"},
            "Vraag om goedkeuring ingetrokken.",
        ),
        ("approval_withdrawn", {"was": "approved"}, "Goedkeuring ingetrokken."),
        ("approval_withdrawn", {"approval_id": "x"}, "Goedkeuring ingetrokken."),
        ("approval_withdrawn", None, "Goedkeuring ingetrokken."),
        (
            "approval_approved",
            {"self_approved": True},
            "Offerte intern goedgekeurd door wie haar maakte.",
        ),
        (
            "approval_approved",
            {"self_approved": True, "asked_it": True},
            "Offerte intern goedgekeurd door wie de goedkeuring zelf vroeg.",
        ),
        (
            "assignment_request_received",
            {
                "received": {
                    "from": "p",
                    "id": "1",
                    "received_from": " Één & Voorbeeld ",
                }
            },
            "Aanvraag ontvangen van Één & Voorbeeld.",
        ),
        (
            "assignment_request_received",
            {"received": {"from": "p", "id": "1", "received_from": "Voorbeeld B.V."}},
            "Aanvraag ontvangen van Voorbeeld B.V.",
        ),
        (
            "assignment_request_received",
            {"received": {"from": "p", "id": "1", "received_from": "   "}},
            "Aanvraag ontvangen.",
        ),
        (
            "assignment_request_received",
            {"received": {"from": "p", "id": "1"}},
            "Aanvraag ontvangen.",
        ),
        ("assignment_request_received", {"assignment": {}}, "Aanvraag ontvangen."),
        ("assignment_request_received", None, "Aanvraag ontvangen."),
        (
            "quote_received",
            {
                "quote": {"reference": "VB-1", "total_cents": 150000},
                "received": {"from": "p", "id": "1", "received_from": "Voorbeeld"},
            },
            "Offerte VB-1 ontvangen van Voorbeeld, € 1.500.",
        ),
        (
            "quote_received",
            {"quote": {"reference": None, "total_cents": 150000}},
            "Offerte ontvangen, € 1.500.",
        ),
    ],
)
def test_a_fact_in_words(fact, fields, sentence):
    assert words.statement(fact, fields, actor=None) == sentence


@pytest.mark.parametrize(
    ("fact", "fields", "told"),
    [
        ("assignment_status_changed", {"reason": "Telefonisch."}, ("Telefonisch.",)),
        ("assignment_status_changed", {"reason": None}, ()),
        ("acceptance_date_corrected", {"reason": "Verkeerd."}, ("Verkeerd.",)),
        ("approval_requested", {"approval": {"request_note": "Graag."}}, ()),
        ("approval_approved", {"decision_note": "Prima."}, ()),
        ("approval_sent_back", {"decision_note": "Anders."}, ()),
        ("quote_rejected", {"rejection": {"reason": "Te duur."}}, ()),
        ("assignment_status_changed", None, ()),
    ],
)
def test_a_moment_says_only_what_no_row_of_the_stand_draws(fact, fields, told):
    assert words.lines(fact, fields) == told


# -- the rate book ------------------------------------------------------------


async def _rate_facts(session) -> list[dict]:
    rows = await session.scalars(
        select(StreamEvent)
        .where(
            StreamEvent.subject_kind == SUBJECT_KIND,
            StreamEvent.subject_id == RATE_BOOK,
            StreamEvent.type == event_type(RATES_FACT),
        )
        .order_by(StreamEvent.seq)
    )
    return [row.new_value for row in rows]


async def test_activating_a_card_records_the_book_with_its_cause(db_session):
    await rates.create_card(
        db_session,
        valid_from=date(2027, 1, 1),
        valid_to=date(2027, 12, 31),
        actor=None,
    )
    await rates.set_rate_band(db_session, 2027, "D", 1900000, actor=None)
    await rates.set_scale_band(db_session, 2027, 14, "D", actor=None)
    drafts_only = len(await _rate_facts(db_session))

    await rates.set_rate_card_status(db_session, 2027, "active", actor=None)
    facts = await _rate_facts(db_session)
    assert len(facts) == drafts_only + 1
    fact = facts[-1]
    assert fact["fields"]["cause"] == (
        "Tarievenkaart Tarieven 2027 vastgesteld, geldt vanaf 1 januari 2027"
    )
    assert fact["effective_on"] == "2027-01-01"
    assert [card["name"] for card in fact["fields"]["book"]["cards"]] == [
        "Tarieven 2027"
    ]


async def test_what_changes_no_price_records_nothing(db_session):
    await _active_card(db_session)
    known = len(await _rate_facts(db_session))

    # Setting the same state again, and everything about a draft.
    await rates.set_rate_card_status(db_session, 2026, "active", actor=None)
    await rates.set_rate_band(db_session, 2026, "D", 1800000, actor=None)
    await rates.set_scale_band(db_session, 2026, 14, "D", actor=None)
    await rates.create_card(db_session, valid_from=date(2027, 1, 1), actor=None)
    await rates.set_rate_band(db_session, 2027, "D", 1900000, actor=None)
    await rates.update_card(db_session, 2027, actor=None, name="Tarieven later")
    assert len(await _rate_facts(db_session)) == known


async def test_a_change_on_a_card_that_prices_is_recorded(db_session):
    await _active_card(db_session)
    known = len(await _rate_facts(db_session))

    await rates.set_rate_band(db_session, 2026, "D", 1810000, actor=None)
    facts = await _rate_facts(db_session)
    assert len(facts) == known + 1
    (card,) = facts[-1]["fields"]["book"]["cards"]
    assert card["rate_bands"] == [{"category": "D", "monthly_rate_cents": 1810000}]
    assert facts[-1]["effective_on"] == "2026-01-01"

    await rates.set_rate_band(db_session, 2026, "E", 2000000, actor=None)
    await rates.set_scale_band(db_session, 2026, 15, "E", actor=None)
    await rates.set_scale_band(db_session, 2026, 15, "D", actor=None)
    await rates.update_card(db_session, 2026, actor=None, valid_to=date(2026, 11, 30))
    facts = await _rate_facts(db_session)
    assert len(facts) == known + 5
    (card,) = facts[-1]["fields"]["book"]["cards"]
    assert card["valid_to"] == "2026-11-30"
    assert {"category": "E", "monthly_rate_cents": 2000000} in card["rate_bands"]
    assert {"scale": 15, "category": "D"} in card["scale_bands"]

    await rates.set_rate_card_status(db_session, 2026, "closed", actor=None)
    fact = (await _rate_facts(db_session))[-1]
    assert fact["fields"]["cause"] == "Tarievenkaart Tarieven 2026 gesloten"
    await rates.set_rate_card_status(
        db_session, 2026, "active", actor=None, allow_closed_year=True
    )
    fact = (await _rate_facts(db_session))[-1]
    assert fact["fields"]["cause"] == "Tarievenkaart Tarieven 2026 heropend"


async def test_activating_records_the_shortened_card_in_one_book(db_session):
    await _active_card(db_session)
    await rates.update_card(db_session, 2026, actor=None, clear_valid_to=True)
    draft = await rates.create_card(
        db_session, valid_from=date(2026, 7, 1), actor=None, copy_previous=True
    )
    known = len(await _rate_facts(db_session))
    await rates.set_rate_card_status(db_session, draft.id, "active", actor=None)
    facts = await _rate_facts(db_session)
    assert len(facts) == known + 1
    first, second = facts[-1]["fields"]["book"]["cards"]
    assert first["valid_to"] == "2026-06-30" and second["valid_from"] == "2026-07-01"


async def test_a_preview_of_an_activation_leaves_no_fact(db_session):
    await _active_card(db_session)
    await rates.update_card(db_session, 2026, actor=None, clear_valid_to=True)
    draft = await rates.create_card(
        db_session, valid_from=date(2026, 7, 1), actor=None, copy_previous=True
    )
    known = len(await _rate_facts(db_session))
    await rates.activation_preview(db_session, draft.id)
    assert len(await _rate_facts(db_session)) == known


# -- one whole path, watched --------------------------------------------------


async def test_a_whole_path_writes_nothing_around_the_chronicle(
    db_session, case, owner, approver, connected
):
    guard.install()
    await db_session.flush()
    with guard.in_request(db_session) as unit:
        first = await quotes.issue_quote(db_session, case.id, actor=owner)
        await quote_approval.request_approval(db_session, first.id, actor=owner)
        await quote_approval.decide(
            db_session,
            first.id,
            approve=False,
            actor=approver,
            quote_hash=first.snapshot_hash,
            note="Anders",
        )
        second = await quotes.issue_quote(db_session, case.id, actor=owner)
        await quote_approval.request_approval(db_session, second.id, actor=owner)
        await quote_approval.decide(
            db_session,
            second.id,
            approve=True,
            actor=approver,
            quote_hash=second.snapshot_hash,
        )
        await quotes.offer_quote(db_session, second.id, "document", actor=owner)
        await quotes.offer_quote(db_session, second.id, "client_instance", actor=owner)
        offer = await quotes.offer_quote(
            db_session, second.id, "signing_link", actor=owner, email=SIGNER
        )
        await quotes.withdraw_invitation(
            db_session, second.id, offer.invitation_id, actor=owner
        )
        await quotes.renew_invitation(
            db_session, second.id, offer.invitation_id, actor=owner
        )
        await quotes.mark_invitation_opened(db_session, second.id, SIGNER)
        await quote_views.accept_via_signing_link(
            db_session,
            second.id,
            quote_hash=second.snapshot_hash,
            signer_name="Tekenaar Voorbeeld",
            signer_email=SIGNER,
            signer_person_id=None,
            declared_mandate=True,
        )
    assert unit.findings == []
    assert unit.cases == {case.id}
    await _same(db_session, case.id)
    grams = await _grams(db_session, case.id)
    assert [gram.fact for gram in grams][2:] == [
        "quote_issued",
        "approval_requested",
        "approval_sent_back",
        "quote_issued",
        "approval_requested",
        "approval_approved",
        "quote_offered",
        "quote_offered",
        "quote_offered",
        "invitation_withdrawn",
        "invitation_renewed",
        "invitation_opened",
        "quote_accepted",
    ]
    assert case.status == "accepted"


async def test_a_row_changed_by_hand_shows_for_each_table(db_session, case, owner):
    quote = await quotes.issue_quote(db_session, case.id, actor=owner)
    await quote_approval.request_approval(db_session, quote.id, actor=owner)
    offer = await quotes.offer_quote(
        db_session, quote.id, "signing_link", actor=owner, email=SIGNER
    )
    acceptance = await _accept_pdf(db_session, quote, owner)
    await _same(db_session, case.id)

    approval = await db_session.scalar(
        select(QuoteApproval).where(QuoteApproval.quote_id == quote.id)
    )
    invitation = await db_session.get(QuoteInvitation, offer.invitation_id)
    assignment = await db_session.get(Assignment, case.id)
    quote.reference = "VOORBEELD-1"
    approval.request_note = "Anders"
    invitation.email = "ander@voorbeeld.example"
    offer.recipient = "ander@voorbeeld.example"
    acceptance.signer_name = "Iemand Anders"
    assignment.quote_date = date(2020, 1, 1)
    await db_session.flush()
    report = await differences(db_session, case.id)
    assert {item.table for item in report.differences} == {
        "assignment",
        "quote",
        "quote_approval",
        "quote_invitation",
        "quote_offer",
        "quote_acceptance",
    }


# -- from another instance ----------------------------------------------------


@pytest.fixture
def bridged(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "INSTANCE_TOOI_URI",
        "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
    )
    clear_registries()
    register_bridge()
    get_bridge_settings.cache_clear()
    yield
    get_bridge_settings.cache_clear()
    clear_registries()
    quote_channels.clear()


async def _case_of_uri(session, uri: str) -> Assignment:
    return await session.scalar(select(Assignment).where(Assignment.uri == uri))


async def test_a_quote_received_from_a_peer(bridged, fed_client, db_session, make_peer):
    peer = await make_peer()
    body = example("quote")
    response = await fed_client.post(
        "/v1/offertes", json=body, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201, response.text
    case = await _case_of_uri(db_session, body[t("assignment_uri")])
    assert await _facts(db_session, case.id) == [
        "assignment_created",
        "assignment_shared",
        "quote_received",
    ]
    gram = await _last(db_session, case.id)
    sender = body[t("contractor")][t("name")]
    assert gram.fields["received"] == {
        "from": peer.peer_id,
        "id": body["id"],
        "received_from": sender,
    }
    assert title_of(gram.fact, gram.fields) == f"Offerte ontvangen van {sender}"
    assert f"ontvangen van {sender}, " in words.statement(
        gram.fact, gram.fields, actor=None
    )
    assert gram.kind == "executogram"
    assert gram.origin == "remote" and gram.origin_peer == peer.peer_id
    assert gram.actor_ref == peer.peer_id
    assert gram.correlation_id == UUID(body["id"]).hex
    assert case.status == "quoted"
    await _same(db_session, case.id)

    types = await _types(db_session, case.id)
    assert "quote.created" not in types and "quote.issued" not in types

    # The same message again is answered as a duplicate and says nothing new.
    again = await fed_client.post(
        "/v1/offertes", json=body, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert again.status_code == 200
    assert (await _facts(db_session, case.id))[-1] == "quote_received"
    assert len(await _facts(db_session, case.id)) == 3


async def test_a_quote_for_a_known_case_names_who_sent_it(
    bridged, fed_client, db_session, make_peer
):
    await make_peer()
    first = example("quote")
    assert (
        await fed_client.post(
            "/v1/offertes", json=first, headers=as_peer(CONTRACTOR_PEER_ID)
        )
    ).status_code == 201
    case = await _case_of_uri(db_session, first[t("assignment_uri")])

    second = {**example("quote"), "id": str(uuid.uuid4())}
    second[t("uri")] = f"https://grip.opdrachtnemer.example/id/offerte/{second['id']}"
    second[t("contractor")] = {
        **second[t("contractor")],
        t("name"): "  Directie Één & Voorbeeld ",
    }
    response = await fed_client.post(
        "/v1/offertes", json=second, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201, response.text
    gram = await _last(db_session, case.id)
    assert gram.fields["quote"]["id"] == second["id"]
    assert title_of(gram.fact, gram.fields) == (
        "Offerte ontvangen van Directie Één & Voorbeeld"
    )
    await _same(db_session, case.id)


async def test_a_request_received_from_a_peer_names_who_sent_it(
    bridged, fed_client, db_session, make_peer
):
    body = example("assignment-request")
    sender = body[t("client")]
    peer = await make_peer(base_uri=sender[t("instance_uri")])
    response = await fed_client.post(
        "/v1/opdrachtaanvragen", json=body, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201, response.text
    case = await _case_of_uri(db_session, body[t("assignment_uri")])
    gram = await _last(db_session, case.id)
    assert gram.fact == "assignment_request_received"
    assert gram.fields["received"] == {
        "from": peer.peer_id,
        "id": body["id"],
        "received_from": sender[t("name")],
    }
    assert title_of(gram.fact, gram.fields) == (
        f"Aanvraag ontvangen van {sender[t('name')]}"
    )
    assert words.statement(gram.fact, gram.fields, actor=None) == (
        f"Aanvraag ontvangen van {sender[t('name')]}."
    )
    await _same(db_session, case.id)


@pytest.fixture
async def offered(db_session, bridged, make_peer, fed_settings):
    """A quote of this instance, offered to the instance of the client."""
    settings = fed_settings.model_copy(
        update={"FEDERATION_SIGNING_KEY": signing.generate_private_key_pem()}
    )
    peer = await make_peer(
        CLIENT_PEER_ID, base_uri=CLIENT_BASE, jwks=signing.own_jwks(settings)
    )
    await _active_card(db_session)
    client = await from_reference(
        db_session,
        {
            "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
            "name": "Voorbeeldministerie",
            "unit_key": "directie-voorbeeld",
            "instance_uri": CLIENT_BASE,
        },
    )
    own = await own_organisation(db_session)
    case = await assignments.create_assignment(
        db_session,
        name="Opdracht Alfa",
        actor=None,
        client_organisation_id=client.id,
        contractor_organisation_id=own.id,
        uri=f"{CLIENT_BASE}/id/opdracht/{FEDERATED_ASSIGNMENT_ID}",
    )
    await assignments.share_with_instance(db_session, case, CLIENT_BASE)
    await assignments.add_budget_line(
        db_session,
        case.id,
        description="Hosting",
        kind="fixed",
        amount_cents=150000,
        year=2026,
        actor=None,
    )
    quote = await quotes.issue_quote(db_session, case.id, actor=None)
    return SimpleNamespace(case=case, quote=quote, peer=peer, settings=settings)


async def test_an_acceptance_received_from_a_peer(fed_client, db_session, offered):
    body = example("acceptance")
    del body[t("jws")]
    body[t("quote_id")] = str(offered.quote.id)
    body[t("quote_hash")] = offered.quote.snapshot_hash
    body[t("jws")] = signing.sign_acceptance(body, offered.settings)
    before = await _facts(db_session, offered.case.id)
    response = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/akkoorden",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 201, response.text
    assert await _facts(db_session, offered.case.id) == [*before, "quote_accepted"]
    gram = await _last(db_session, offered.case.id)
    assert gram.fields["received"] == {"from": CLIENT_PEER_ID, "id": body["id"]}
    assert gram.kind == "executogram"
    assert gram.origin == "remote" and gram.origin_peer == CLIENT_PEER_ID
    assert offered.case.status == "accepted"
    assert offered.quote.status == "accepted"
    await _same(db_session, offered.case.id)


async def test_a_rejection_received_from_a_peer(fed_client, db_session, offered):
    body = example("rejection")
    body[t("quote_id")] = str(offered.quote.id)
    body[t("quote_hash")] = offered.quote.snapshot_hash
    before = await _facts(db_session, offered.case.id)
    response = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/afwijzingen",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 201, response.text
    assert await _facts(db_session, offered.case.id) == [*before, "quote_rejected"]
    gram = await _last(db_session, offered.case.id)
    assert gram.fields["received"] == {"from": CLIENT_PEER_ID, "id": body["id"]}
    assert gram.kind == "executogram"
    assert gram.origin == "remote"
    await _same(db_session, offered.case.id)


async def test_a_refused_message_leaves_no_fact(fed_client, db_session, offered):
    body = example("rejection")
    body[t("quote_id")] = str(offered.quote.id)
    before = await _facts(db_session, offered.case.id)
    response = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/afwijzingen",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 409
    assert await _facts(db_session, offered.case.id) == before


FAR_ENDS = (
    "9999-12-31T23:59:59Z",
    "0001-01-01T00:00:00+14:00",
    "0001-01-01T00:00:00Z",
    "2200-01-01T00:00:00Z",
    "1899-12-31T23:59:59Z",
)


def _rejection_of(offered, **values) -> dict:
    body = example("rejection")
    body["id"] = str(uuid.uuid4())
    body[t("quote_id")] = str(offered.quote.id)
    body[t("quote_hash")] = offered.quote.snapshot_hash
    body.update(values)
    return body


@pytest.mark.parametrize("moment", FAR_ENDS)
async def test_a_rejection_at_the_far_end_of_the_calendar_is_refused(
    fed_client, db_session, offered, moment
):
    before = await _facts(db_session, offered.case.id)
    response = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/afwijzingen",
        json=_rejection_of(offered, **{t("rejected_at"): moment}),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 400, response.text
    assert response.json()["title"] == "Bericht geweigerd"
    assert t("rejected_at") in response.json()["detail"]
    assert await _facts(db_session, offered.case.id) == before


@pytest.mark.parametrize("moment", FAR_ENDS)
async def test_a_quote_at_the_far_end_of_the_calendar_is_refused(
    bridged, fed_client, db_session, make_peer, moment
):
    await make_peer()
    body = example("quote")
    body[t("issued_at")] = moment
    response = await fed_client.post(
        "/v1/offertes", json=body, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 400, response.text
    assert t("issued_at") in response.json()["detail"]
    assert await _case_of_uri(db_session, body[t("assignment_uri")]) is None


@pytest.mark.parametrize("moment", FAR_ENDS)
async def test_an_acceptance_at_the_far_end_of_the_calendar_is_refused(
    fed_client, db_session, offered, moment
):
    body = example("acceptance")
    del body[t("jws")]
    body[t("quote_id")] = str(offered.quote.id)
    body[t("quote_hash")] = offered.quote.snapshot_hash
    body[t("signed_at")] = moment
    body[t("jws")] = signing.sign_acceptance(body, offered.settings)
    before = await _facts(db_session, offered.case.id)
    response = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/akkoorden",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 400, response.text
    assert t("signed_at") in response.json()["detail"]
    assert await _facts(db_session, offered.case.id) == before


@pytest.mark.parametrize(
    "moment", ("1900-01-01T00:00:00Z", "2199-12-31T23:59:59+01:00")
)
async def test_a_rejection_inside_the_years_is_taken(
    fed_client, db_session, offered, moment
):
    response = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/afwijzingen",
        json=_rejection_of(offered, **{t("rejected_at"): moment}),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert response.status_code == 201, response.text
    await _same(db_session, offered.case.id)


async def test_a_catch_up_records_a_far_date_as_refused_and_goes_on(
    fed_client, db_session, offered
):
    clear_registries()
    for body in (
        _rejection_of(offered, **{t("rejected_at"): "9999-12-31T23:59:59Z"}),
        _rejection_of(offered, **{t("rejected_at"): "0001-01-01T00:00:00Z"}),
        _rejection_of(offered),
    ):
        stored = await fed_client.post(
            f"/v1/offertes/{offered.quote.id}/afwijzingen",
            json=body,
            headers=as_peer(CLIENT_PEER_ID),
        )
        assert stored.status_code == 201, stored.text
    register_bridge()

    assert await process_pending(db_session) == 3

    rows = (
        await db_session.scalars(
            select(FederationInbox).order_by(FederationInbox.received_at)
        )
    ).all()
    assert [row.result.get("refused", {}).get("status") for row in rows] == [
        400,
        400,
        None,
    ]
    assert rows[2].result["quote_id"] == str(offered.quote.id)
    assert offered.quote.status == "rejected"
    await _same(db_session, offered.case.id)


async def test_a_row_gone_or_moved_answers_a_peer_so_that_it_tries_again(
    fed_client, db_session, offered, monkeypatch
):
    body = _rejection_of(offered)
    real = quotes.reject_quote

    async def moved_once(*args, **kwargs):
        monkeypatch.setattr(quotes, "reject_quote", real)
        raise StaleDataError("the row is gone")

    monkeypatch.setattr(quotes, "reject_quote", moved_once)
    first = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/afwijzingen",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert first.status_code == 500, "a 409 would end the sender's tries for good"
    assert first.json()["detail"] == "Interne fout"
    assert await db_session.scalar(select(FederationInbox)) is None

    again = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/afwijzingen",
        json=body,
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert again.status_code == 201, again.text
    await _same(db_session, offered.case.id)


async def test_a_row_gone_or_moved_stops_a_catch_up_for_one_round(
    fed_client, db_session, offered, monkeypatch
):
    clear_registries()
    stored = await fed_client.post(
        f"/v1/offertes/{offered.quote.id}/afwijzingen",
        json=_rejection_of(offered),
        headers=as_peer(CLIENT_PEER_ID),
    )
    assert stored.status_code == 201, stored.text
    register_bridge()
    real = quotes.reject_quote

    async def moved_once(*args, **kwargs):
        monkeypatch.setattr(quotes, "reject_quote", real)
        raise StaleDataError("the row is gone")

    monkeypatch.setattr(quotes, "reject_quote", moved_once)
    with pytest.raises(StaleDataError):
        await process_pending(db_session)
    row = await db_session.scalar(select(FederationInbox))
    assert row.processed_at is None

    assert await process_pending(db_session) == 1
    assert "refused" not in row.result
    await _same(db_session, offered.case.id)


async def test_a_stored_message_names_its_peer_when_the_worker_gets_to_it(
    fed_client, db_session, make_peer, bridged
):
    """Stored while no handler was registered, processed later by the worker."""
    peer = await make_peer()
    body = example("quote")
    clear_registries()
    response = await fed_client.post(
        "/v1/offertes", json=body, headers=as_peer(CONTRACTOR_PEER_ID)
    )
    assert response.status_code == 201, response.text
    assert await _case_of_uri(db_session, body[t("assignment_uri")]) is None

    register_bridge()
    with event_context.scope(job="inbox") as outer:
        assert await process_pending(db_session) == 1
        assert event_context.current() == outer, "the worker's own context returns"

    row = await db_session.scalar(select(FederationInbox))
    assert row.processed_at is not None and "refused" not in row.result
    case = await _case_of_uri(db_session, body[t("assignment_uri")])
    gram = await _last(db_session, case.id)
    assert gram.fact == "quote_received"
    assert gram.fields["received"] == {
        "from": peer.peer_id,
        "id": body["id"],
        "received_from": body[t("contractor")][t("name")],
    }
    assert gram.origin == "remote" and gram.origin_peer == peer.peer_id
    assert gram.actor_ref == peer.peer_id
    assert gram.correlation_id == row.message_id.hex
    await _same(db_session, case.id)


async def test_a_message_the_worker_refuses_leaves_no_fact_and_clears_the_context(
    fed_client, db_session, make_peer, bridged
):
    await make_peer()
    body = example("rejection")
    clear_registries()
    response = await fed_client.post(
        f"/v1/offertes/{body[t('quote_id')]}/afwijzingen",
        json=body,
        headers=as_peer(CONTRACTOR_PEER_ID),
    )
    assert response.status_code == 201, response.text
    register_bridge()
    with event_context.scope(job="inbox") as outer:
        assert await process_pending(db_session) == 1
        assert event_context.current() == outer
    row = await db_session.scalar(select(FederationInbox))
    assert row.result["refused"]["status"] == 404


# -- stored documents and small things around it ------------------------------


async def test_the_kept_file_belongs_to_the_quote_it_was_made_for(
    db_session, case, owner
):
    quote = await quotes.issue_quote(db_session, case.id, actor=owner)
    document_id = stored_documents.parse_document_ref(quote.document_ref)
    document = await stored_documents.owned_document(
        db_session, quote_files.QUOTE_DOCUMENT, quote.id, document_id
    )
    assert document.sha256 == quote.document_sha256


def test_the_rate_cards_a_quote_names_are_those_its_lines_touch():
    def card(year: int, status=calc.RateCardStatus.ACTIVE) -> calc.RateCard:
        return calc.RateCard(
            id=str(year),
            name=f"Tarieven {year}",
            valid_from=date(year, 1, 1),
            valid_to=date(year, 12, 31),
            status=status,
            rate_bands=(),
            scale_bands=(),
        )

    book = calc.RateBook(
        cards=(card(2025), card(2026), card(2027, calc.RateCardStatus.DRAFT))
    )

    def line(kind: str, start: date | None, end: date | None) -> SimpleNamespace:
        return SimpleNamespace(kind=kind, start_date=start, end_date=end)

    assert [
        item["name"]
        for item in quotes._cards_touched(
            [
                line("personnel", date(2026, 3, 1), date(2027, 3, 1)),
                line("fixed", date(2025, 1, 1), date(2025, 2, 1)),
                line("personnel", None, None),
            ],
            book,
        )
    ] == ["Tarieven 2026"]
    with_draft = calc.RateBook(cards=book.cards, include_draft=True)
    assert [
        item["name"]
        for item in quotes._cards_touched(
            [line("personnel", date(2026, 12, 31), date(2027, 1, 1))], with_draft
        )
    ] == ["Tarieven 2026", "Tarieven 2027"]


async def test_the_day_a_fact_is_recorded_and_the_day_it_counts_can_differ(
    db_session, case, owner, quote
):
    signed = quote.issued_at
    forty_days_on = signed + timedelta(days=40)
    with clock.at(forty_days_on):
        await _accept_pdf(db_session, quote, owner, signed_at=signed)
    gram = await _last(db_session, case.id)
    assert gram.recorded_on == clock.local_date(forty_days_on).isoformat()
    assert gram.effective_on == clock.local_date(signed).isoformat()
    assert gram.effective_on != gram.recorded_on


async def test_the_quote_rows_of_a_fact_are_those_the_service_returns(
    db_session, case, owner, quote
):
    assert isinstance(quote, Quote)
    rejection = await quotes.reject_quote(
        db_session, quote.id, quote_hash=quote.snapshot_hash, actor=owner
    )
    assert isinstance(rejection, QuoteRejection)
    assert rejection.quote_id == quote.id
