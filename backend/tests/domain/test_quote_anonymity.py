"""A quote never names anyone, and cannot start to by accident."""

import dataclasses
import json
from datetime import date
from decimal import Decimal

import pytest

from grip.federation.bridge import builders
from grip.models.assignment import BudgetLine
from grip.services import (
    assignments,
    budget_intent,
    canonical,
    events,
    quote_content,
    quote_document,
    quote_views,
    quotes,
)
from grip.services.quote_content import (
    ALLOWED_CONTENT_KEYS,
    ALLOWED_LINE_KEYS,
    INTERNAL_COLUMNS,
    QUOTE_SOURCE_COLUMNS,
    QuoteContentError,
    QuoteLineSource,
    check_content,
)
from grip.services.reports import assignment_report

CLIENT_BASE = "https://grip.opdrachtgever.example"
ORG = {
    "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
    "name": "Voorbeeldministerie",
}


# -- structure --------------------------------------------------------------------


def test_every_column_of_a_budget_line_is_classified():
    """A new column must be put on one of the two lists.

    This fails on purpose when a column is added to budget_line: decide in
    grip/services/quote_content.py whether a quote may be built from it.
    """
    columns = {column.name for column in BudgetLine.__table__.columns}
    assert QUOTE_SOURCE_COLUMNS.isdisjoint(INTERNAL_COLUMNS)
    unclassified = columns - QUOTE_SOURCE_COLUMNS - INTERNAL_COLUMNS
    assert unclassified == set(), (
        f"budget_line columns without a decision about the quote: {unclassified}"
    )
    assert (QUOTE_SOURCE_COLUMNS | INTERNAL_COLUMNS) - columns == set()
    assert "intended_person_id" in INTERNAL_COLUMNS


def test_the_quote_builder_only_gets_the_allowed_columns():
    fields = {field.name for field in dataclasses.fields(QuoteLineSource)}
    assert fields == QUOTE_SOURCE_COLUMNS | {"id", "assignment_id"}
    assert not hasattr(QuoteLineSource, "intended_person_id")


def _content(**line_extra):
    line = {
        "position": 1,
        "description": "Rol",
        "kind": "fixed",
        "year": 2026,
        "amount": {"amount_cents": 100, "currency": "EUR"},
    }
    line.update(line_extra)
    return {
        "name": "Opdracht",
        "context_refs": [],
        "lines": [line],
        "subtotals_per_year": [
            {"year": 2026, "amount": {"amount_cents": 100, "currency": "EUR"}}
        ],
        "total": {"amount_cents": 100, "currency": "EUR"},
    }


def test_content_outside_the_allow_list_is_refused():
    assert check_content(_content()) == _content()
    with pytest.raises(QuoteContentError, match="intended_person_id"):
        check_content(_content(intended_person_id="x"))
    with pytest.raises(QuoteContentError, match="person_name"):
        check_content(
            _content(amount={"amount_cents": 1, "currency": "EUR", "person_name": "x"})
        )
    with pytest.raises(QuoteContentError, match="staffing"):
        check_content({**_content(), "staffing": []})
    with pytest.raises(QuoteContentError):
        check_content(_content(period={"start_date": "a", "end_date": "b", "who": "x"}))
    assert not {"intended_person_id", "person_id", "person_name"} & (
        ALLOWED_LINE_KEYS | ALLOWED_CONTENT_KEYS
    )


def test_allow_list_covers_what_the_contract_terms_know():
    """Every allowed key has a contract term, so nothing allowed goes out raw."""
    from grip.services import terms

    translated = terms.to_contract(_content(role="Rol", fte="1", rate_category="D"))
    assert json.dumps(translated)  # serialisable, and no exception on the way


# -- end to end ---------------------------------------------------------------------


@pytest.fixture
async def budget_with_people(
    db_session, rate_cards, beheerder, create_person, make_assignment
):
    """A budget of three lines, two of them meant for someone."""
    from grip.services import rates

    people = []
    for index, scale in ((1, 14), (2, 12)):
        person = await create_person(
            f"zeta{index}7731@example.org", name=f"Persoon-Zeta-{index}7731"
        )
        await rates.set_person_scale(
            db_session, person.id, date(2026, 1, 1), scale, actor=beheerder
        )
        people.append(person)
    client = await assignments.upsert_organisation(
        db_session, **ORG, unit_key="directie-voorbeeld", instance_uri=CLIENT_BASE
    )
    assignment = await make_assignment(client_organisation_id=client.id)
    for person, role in zip(people, ("Productmanager", "Developer"), strict=True):
        await budget_intent.add_line(
            db_session,
            assignment.id,
            actor=beheerder,
            intended_person_id=person.id,
            description=role,
            kind="personnel",
            role=role,
            fte=Decimal("0.8"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
    await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Hosting",
        kind="fixed",
        amount_cents=15_000_00,
        year=2026,
        actor=beheerder,
    )
    return assignment, people


def _needles(people) -> list[str]:
    needles = []
    for person in people:
        needles += [str(person.id), person.id.hex, person.name, person.email]
        needles += [person.name.split("-")[-1], person.email.split("@")[0]]
    return needles


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except TypeError:
        return repr(value)


def _assert_anonymous(what: str, value, people) -> None:
    text = _text(value)
    assert text, what
    for needle in _needles(people):
        assert needle not in text, f"{what} names an intended person ({needle})"
    assert "intended" not in text, f"{what} mentions an intended person"


async def test_no_intended_person_from_preview_to_federated_quote(
    db_session, budget_with_people, beheerder
):
    assignment, people = budget_with_people
    seen = []

    async def record(session, event_type, payload):
        seen.append((event_type, payload))

    for event_type in (events.QUOTE_ISSUED, events.QUOTE_ACCEPTED):
        events.register_handler(event_type, record)

    # The check itself works: it objects to a name, an id and an address.
    for leak in (people[0].name, {"x": people[1].id}, people[0].email.encode()):
        with pytest.raises(AssertionError):
            _assert_anonymous("a leak", leak, people)

    # The names are in the budget ...
    lines = await db_session.run_sync(
        lambda s: s.query(BudgetLine).filter_by(assignment_id=assignment.id).all()
    )
    assert {line.intended_person_id for line in lines} == {p.id for p in people} | {
        None
    }

    # ... and nowhere in the preview,
    preview = await quotes.build_snapshot(db_session, assignment)
    _assert_anonymous("the preview", preview, people)
    _assert_anonymous(
        "the preview's canonical form", canonical.canonical_form(preview), people
    )
    assert [line.get("role") for line in preview["lines"]] == [
        "Productmanager",
        "Developer",
        None,
    ]
    assert [line.get("rate_category") for line in preview["lines"]] == ["D", "C", None]
    assert all(
        set(line) <= quote_content.ALLOWED_LINE_KEYS for line in preview["lines"]
    )

    # the issued quote,
    quote = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    _assert_anonymous("the canonical form", quote.canonical, people)
    _assert_anonymous("the contract form", quote.contract_snapshot, people)
    _assert_anonymous("the quote content", quote.snapshot, people)
    (issued,) = [payload for kind, payload in seen if kind == events.QUOTE_ISSUED]
    _assert_anonymous("the quote.issued event", issued, people)

    # the document,
    context = await quote_views.document_context(db_session, quote)
    html = quote_document.render_quote_html(quote.snapshot, context)
    assert "Productmanager" in html
    _assert_anonymous("the quote document", html, people)

    # the message to the client's instance,
    assignments.share_with_instance(assignment, CLIENT_BASE)
    await db_session.flush()
    built = await builders.quote_offered(
        db_session,
        {
            "quote_id": str(quote.id),
            "quote_uri": quote.uri,
            "assignment_id": str(assignment.id),
            "channel": "client_instance",
            "issued_at": quote.issued_at.isoformat(),
            "origin": "local",
        },
    )
    assert built is not None, "the federated quote was not built"
    message = dict(built["message"])
    message["snapshot"] = getattr(message["snapshot"], "value", message["snapshot"])
    assert "Productmanager" in _text(message)  # the content is really in there
    _assert_anonymous("the federated quote", message, people)
    _assert_anonymous("the federated quote (raw)", repr(built), people)

    # and what the report to the client says was agreed.
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
    agreed = await assignment_report.accepted_quote(db_session, assignment.id)
    assert agreed is not None and len(agreed.lines) == 3
    _assert_anonymous("the agreed part of the report", repr(agreed), people)
    (accepted,) = [payload for kind, payload in seen if kind == events.QUOTE_ACCEPTED]
    _assert_anonymous("the quote.accepted event", accepted, people)


async def test_a_leaking_field_is_stopped_before_anything_is_hashed(
    db_session, budget_with_people, beheerder, monkeypatch
):
    """If a builder ever copies something extra into a line, issuing fails."""
    assignment, people = budget_with_people
    original = quotes._snapshot_line

    def leaking(line, rates, options):
        entry = original(line, rates, options)
        entry["intended_person_id"] = str(people[0].id)
        return entry

    monkeypatch.setattr(quotes, "_snapshot_line", leaking)
    with pytest.raises(QuoteContentError, match="intended_person_id"):
        await quotes.build_snapshot(db_session, assignment)
    with pytest.raises(QuoteContentError):
        await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    assert assignment.status == "draft"
