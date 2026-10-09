"""The reference of a quote, its document as a PDF, and the signing link."""

from __future__ import annotations

import asyncio
import base64
import io
from datetime import UTC, datetime, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from grip.core.config import get_settings
from grip.schema.quotes import content_from_snapshot
from grip.services import assignments, quote_reference, quotes
from grip.services.errors import DomainValidationError
from grip.services.quote_document import (
    DocumentEngineError,
    Letterhead,
    QuoteDocumentContext,
    part_month_note,
    render_quote_html,
    render_quote_pdf,
    scale_text,
)
from tests.api.quotes.conftest import document_text

HASH = "ab" * 32
ISSUED = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
RIBBON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">'
    '<path fill="#154273" d="M256-256h512V768H256z"/></svg>'
)


def _money(cents: int) -> dict:
    return {"amount_cents": cents, "currency": "EUR"}


def _line(position: int, **extra) -> dict:
    return {
        "position": position,
        "description": f"Rol {position}",
        "kind": "personnel",
        "fte": "0.8",
        "rate_category": "D",
        "scales": [14, 15],
        "period": {"start_date": "2026-01-01", "end_date": "2026-12-31"},
        "monthly_rate": _money(1_800_000),
        "amount": _money(17_280_000),
        **extra,
    }


def _content(lines: list[dict], **extra) -> dict:
    total = sum(line["amount"]["amount_cents"] for line in lines)
    return {
        "name": "Opdracht Alfa",
        "sender": "Voorbeeldgilde",
        "reference": "VG-2026-0007",
        "lines": lines,
        "subtotals_per_year": [{"year": 2026, "amount": _money(total)}],
        "total": _money(total),
        **extra,
    }


def _context(letterhead: Letterhead | None = None) -> QuoteDocumentContext:
    return QuoteDocumentContext(
        quote_uri="https://grip.voorbeeld.example/id/offerte/1",
        snapshot_hash=HASH,
        issued_at=ISSUED,
        contractor_name="Voorbeeldgilde",
        client_name="Voorbeeldministerie",
        letterhead=letterhead or Letterhead(),
    )


def _pdf(content: dict, letterhead: Letterhead | None = None) -> PdfReader:
    try:
        data = render_quote_pdf(content, _context(letterhead))
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    assert data.startswith(b"%PDF-")
    return PdfReader(io.BytesIO(data))


def _text(reader: PdfReader) -> str:
    pages = "\n".join(page.extract_text() for page in reader.pages)
    return pages.replace("\xa0", " ")


# -- the document -------------------------------------------------------------


def test_pdf_of_one_line_holds_reference_total_and_fingerprint():
    reader = _pdf(_content([_line(1)]))
    assert len(reader.pages) == 1
    found = _text(reader)
    assert "VG-2026-0007" in found
    assert "€ 172.800,00" in found
    assert HASH in found.replace("\n", "").replace(" ", "")
    assert "pagina 1 van 1" in found
    assert "14 en 15 (categorie D)" in found
    # The reference line never shows an address.
    kenmerk = found[found.index("Kenmerk") : found.index("Betreft")]
    assert "http" not in kenmerk


def test_pdf_is_tagged_titled_and_in_dutch():
    reader = _pdf(_content([_line(1)]))
    catalog = reader.trailer["/Root"]
    assert "/StructTreeRoot" in catalog
    assert catalog["/Lang"] == "nl"
    assert reader.metadata.title == "Offerte VG-2026-0007 Opdracht Alfa"
    assert reader.metadata.creation_date == ISSUED
    fonts = {
        str(font.get_object().get("/BaseFont"))
        for page in reader.pages
        for font in page["/Resources"]["/Font"].values()
    }
    # Every font is an embedded subset: its name has the six-letter tag.
    assert fonts and all(name[1:7].isupper() and name[7] == "+" for name in fonts)


def test_the_same_quote_gives_the_same_bytes():
    content = _content([_line(1)])
    try:
        first = render_quote_pdf(content, _context())
        second = render_quote_pdf(content, _context())
    except DocumentEngineError:
        pytest.skip("the PDF engine's system libraries are not installed here")
    assert first == second


def test_pdf_over_two_years_has_subtotals_and_rates_per_year():
    line = _line(
        1,
        period={"start_date": "2026-07-01", "end_date": "2027-06-30"},
        amount=_money(17_712_000),
    )
    del line["monthly_rate"]
    line["monthly_rates_per_year"] = [
        {"year": 2026, "monthly_rate": _money(1_800_000)},
        {"year": 2027, "monthly_rate": _money(1_890_000)},
    ]
    content = _content([line])
    content["subtotals_per_year"] = [
        {"year": 2026, "amount": _money(8_640_000)},
        {"year": 2027, "amount": _money(9_072_000)},
    ]
    found = _text(_pdf(content))
    assert "Subtotaal 2026" in found and "Subtotaal 2027" in found
    assert "2026: € 18.000,00" in found and "2027: € 18.900,00" in found
    assert "€ 177.120,00" in found


def test_a_long_table_breaks_pages_and_repeats_its_header():
    reader = _pdf(_content([_line(n) for n in range(1, 81)]))
    assert len(reader.pages) >= 3
    total = len(reader.pages)
    for number, page in enumerate(reader.pages, start=1):
        found = page.extract_text().replace("\xa0", " ")
        assert f"pagina {number} van {total}" in found
        # The reference stands on every page.
        assert "VG-2026-0007" in found
    # The header row comes back on a page the table continues on.
    assert "Omschrijving" in reader.pages[1].extract_text()
    # The signing block is not split: its lines are on one page.
    last = [
        p.extract_text() for p in reader.pages if "Handtekening" in p.extract_text()
    ]
    assert len(last) == 1 and "Voor akkoord namens" in last[0]


def test_with_and_without_the_ribbon(tmp_path):
    svg = tmp_path / "lint.svg"
    svg.write_text(RIBBON_SVG)
    with_ribbon = Letterhead(
        lines=("Rijksorganisatie Voorbeeld", "Ministerie van Voorbeeldzaken"),
        ribbon_data_uri="data:image/svg+xml;base64,"
        + base64.b64encode(svg.read_bytes()).decode(),
    )
    html = render_quote_html(_content([_line(1)]), _context(with_ribbon))
    assert 'class="ribbon"' in html and "Logo Rijksoverheid" in html
    plain = render_quote_html(_content([_line(1)]), _context())
    assert 'class="ribbon"' not in plain and 'class="plain-head"' in plain

    found = _text(_pdf(_content([_line(1)]), with_ribbon))
    assert "Voorbeeldgilde" in found
    assert "Ministerie van Voorbeeldzaken" in found
    assert "Voorbeeldgilde" in _text(_pdf(_content([_line(1)])))


def test_the_ribbon_is_off_until_configured(tmp_path, monkeypatch):
    from grip.services.quote_document import letterhead_from_settings

    settings = get_settings().model_copy(
        update={"LETTERHEAD_LOGO_PATH": "", "LETTERHEAD_LINES": "Een | Twee"}
    )
    plain = letterhead_from_settings(settings)
    assert plain.ribbon_data_uri is None
    assert plain.lines == ("Een", "Twee")
    svg = tmp_path / "lint.svg"
    svg.write_text(RIBBON_SVG)
    configured = letterhead_from_settings(
        settings.model_copy(update={"LETTERHEAD_LOGO_PATH": str(svg)})
    )
    assert configured.ribbon_data_uri is not None
    # A path that is not an SVG file switches nothing on.
    missing = letterhead_from_settings(
        settings.model_copy(update={"LETTERHEAD_LOGO_PATH": str(tmp_path / "geen.svg")})
    )
    assert missing.ribbon_data_uri is None


def test_scales_and_part_month_in_words():
    assert scale_text({"rate_category": "D", "scales": [14, 15]}) == (
        "14 en 15 (categorie D)"
    )
    assert scale_text({"rate_category": "D"}) == "Categorie D"
    whole = [_line(1)]
    assert part_month_note(whole) == ""
    part = [_line(1, period={"start_date": "2026-10-01", "end_date": "2026-10-29"})]
    assert "oktober 2026 telt voor 29 van de 31 dagen" in part_month_note(part)
    late = [_line(1, period={"start_date": "2026-03-16", "end_date": "2026-12-31"})]
    assert "maart 2026 telt voor 16 van de 31 dagen" in part_month_note(late)


def test_a_rate_that_changes_inside_the_period_shows_every_rate():
    line = _line(1)
    del line["monthly_rate"]
    line["monthly_rate_periods"] = [
        {
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",
            "monthly_rate": _money(1_800_000),
        },
        {
            "start_date": "2026-07-01",
            "end_date": "2026-12-31",
            "monthly_rate": _money(1_900_000),
        },
    ]
    content = _content([line])
    html = render_quote_html(content, _context())
    assert "1 januari 2026 t/m 30 juni 2026: € 18.000,00 per maand" in html
    assert "1 juli 2026 t/m 31 december 2026: € 19.000,00 per maand" in html
    assert "Het tarief wijzigt per 1 juli 2026." in html
    found = _text(_pdf(content))
    assert "19.000,00" in found
    # The response for the screen carries the same periods.
    shown = content_from_snapshot(content).lines[0]
    assert [p.monthly_rate_cents for p in shown.rate_periods] == [1_800_000, 1_900_000]
    assert shown.monthly_rates == []


def test_what_the_content_holds_is_escaped():
    content = _content([_line(1, description='<img src=x onerror="alert(1)">')])
    html = render_quote_html(content, _context())
    assert "<img src=x" not in html and "&lt;img" in html
    assert "<script" not in html


# -- the reference ------------------------------------------------------------


def test_prefix_comes_from_the_setting_or_the_instance_key():
    settings = get_settings()
    assert (
        quote_reference.reference_prefix(
            settings.model_copy(update={"QUOTE_REFERENCE_PREFIX": "dg"})
        )
        == "DG"
    )
    assert (
        quote_reference.reference_prefix(
            settings.model_copy(
                update={"QUOTE_REFERENCE_PREFIX": "", "INSTANCE_KEY": "digi-gilde"}
            )
        )
        == "DIGIGILDE"
    )
    assert quote_reference.format_reference("DG", 2026, 7) == "DG-2026-0007"
    assert quote_reference.file_stem("DG-2026-0007", "x") == "DG-2026-0007"
    assert quote_reference.file_stem(None, "20261008-abc") == "20261008-abc"


async def _issue(act_as, world, **body) -> dict:
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json=body
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_the_settings_show_the_reference_the_next_quote_really_gets(
    act_as, world
):
    """Not "0001" as an example when quotes exist: the number that comes next,
    and showing it takes no number."""
    prefix = quote_reference.reference_prefix()
    year = datetime.now(UTC).year
    beheerder = act_as(world.beheerder)
    shown = (await beheerder.get("/api/instance-settings")).json()
    assert shown["next_quote_reference"] == f"{prefix}-{year}-0001"
    await _issue(act_as, world)
    for _ in range(2):
        shown = (await act_as(world.beheerder).get("/api/instance-settings")).json()
        assert shown["next_quote_reference"] == f"{prefix}-{year}-0002"
    assert (await _issue(act_as, world))["reference"] == f"{prefix}-{year}-0002"


async def test_a_quote_gets_a_reference_that_is_part_of_what_is_hashed(
    act_as, world, db_session
):
    prefix = quote_reference.reference_prefix()
    year = datetime.now(UTC).year
    first = await _issue(act_as, world, client_reference="ZK-4411")
    second = await _issue(act_as, world)
    assert first["reference"] == f"{prefix}-{year}-0001"
    # A new version for the same assignment is a new quote with its own number.
    assert second["reference"] == f"{prefix}-{year}-0002"
    assert first["content"]["client_reference"] == "ZK-4411"

    quote = await quotes.get_quote(db_session, first["id"])
    assert quote.snapshot["reference"] == first["reference"]
    # In the frozen form the terms are Dutch.
    assert b'"kenmerk":"' + first["reference"].encode() in quote.canonical
    assert b'"uw_kenmerk":"ZK-4411"' in quote.canonical
    assert b'"afzender":' in quote.canonical
    assert b'"schalen":[14,15]' in quote.canonical
    assert first["snapshot_hash"] != second["snapshot_hash"]


async def test_the_beheerder_sets_the_prefix_for_new_references(db_session):
    from grip.services import instance_settings

    await instance_settings.set_values(
        db_session, {quote_reference.PREFIX.key: "dg"}, actor=None
    )
    assert (await quote_reference.next_reference(db_session, 2998)).startswith(
        "DG-2998-"
    )
    # Empty goes back to what the installation was set up with.
    await instance_settings.set_values(
        db_session, {quote_reference.PREFIX.key: ""}, actor=None
    )
    assert await quote_reference.current_prefix(db_session) == (
        quote_reference.reference_prefix()
    )
    with pytest.raises(DomainValidationError):
        await instance_settings.set_values(
            db_session,
            {quote_reference.PREFIX.key: "te lang en met spaties"},
            actor=None,
        )


async def test_a_quote_that_cannot_be_made_uses_no_number(act_as, world, db_session):
    await assignments.delete_allocation(
        db_session, world.allocation.id, actor=world.manager
    )
    await assignments.delete_budget_line(db_session, world.line.id, actor=world.manager)
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 422
    count = await db_session.scalar(
        text("SELECT count(*) FROM quote_reference_counter")
    )
    assert count == 0


async def test_references_are_unique_when_issued_at_the_same_moment():
    """Separate transactions that take a number at once all get another one."""
    year = 2999
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)

    async def take() -> str:
        async with AsyncSession(engine) as session, session.begin():
            reference = await quote_reference.next_reference(session, year)
            # Hold the transaction open for a moment, so the others have to wait.
            await asyncio.sleep(0.05)
            return reference

    try:
        taken = await asyncio.gather(*(take() for _ in range(12)))
        assert len(set(taken)) == 12
        numbers = sorted(int(reference.rsplit("-", 1)[1]) for reference in taken)
        assert numbers == list(range(1, 13))
    finally:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                text("DELETE FROM quote_reference_counter WHERE year = :y"), {"y": year}
            )
        await engine.dispose()


async def test_find_a_quote_by_its_reference(act_as, world):
    quote = await _issue(act_as, world)
    number = quote["reference"].rsplit("-", 1)[1]
    found = (
        await act_as(world.manager).get("/api/quote-references", params={"q": number})
    ).json()
    assert [q["id"] for q in found["quotes"]] == [quote["id"]]
    # Someone who may not know the assignment finds nothing.
    hidden = (
        await act_as(world.outsider).get(
            "/api/quote-references", params={"q": quote["reference"]}
        )
    ).json()
    assert hidden == {"quotes": []}


# -- the routes ---------------------------------------------------------------


async def test_download_is_a_pdf_named_after_the_reference(act_as, world):
    quote = await _issue(act_as, world, conditions="Verrekening per maand.")
    client = act_as(world.manager)
    view = await client.get(f"/api/quotes/{quote['id']}/document")
    assert view.headers["content-disposition"].startswith("inline;")
    assert quote["reference"] in document_text(view)

    response = await client.get(f"/api/quotes/{quote['id']}/document?download=true")
    if response.status_code == 422 and "opmaakbibliotheek" in response.text:
        pytest.skip("the PDF engine's system libraries are not installed here")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="offerte-{quote["reference"]}.pdf"'
    )
    found = _text(PdfReader(io.BytesIO(response.content)))
    assert quote["reference"] in found
    assert "€ 172.800,00" in found
    assert quote["snapshot_hash"] in found.replace("\n", "").replace(" ", "")


async def test_no_name_of_staff_is_on_the_document(act_as, world, db_session):
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    html = document_text(await client.get(f"/api/quotes/{quote['id']}/document"))
    names = (await db_session.execute(text("SELECT name FROM person"))).scalars().all()
    assert len(names) >= 6
    for name in names:
        assert name not in html, name
    response = await client.get(f"/api/quotes/{quote['id']}/document?download=true")
    if response.status_code == 200:
        found = _text(PdfReader(io.BytesIO(response.content)))
        for name in names:
            assert name not in found, name


async def test_the_sender_is_the_organisation_not_the_software(
    act_as, world, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "ORGANISATION_NAME", "Voorbeeldgilde")
    quote = await _issue(act_as, world)
    assert quote["content"]["sender"] == "Voorbeeldgilde"
    html = document_text(
        await act_as(world.manager).get(f"/api/quotes/{quote['id']}/document")
    )
    assert "Voorbeeldgilde" in html
    assert settings.INSTANCE_NAME not in html


async def test_default_conditions_are_proposed(act_as, world, monkeypatch):
    monkeypatch.setattr(
        get_settings(), "QUOTE_DEFAULT_CONDITIONS", "Verrekening per maand."
    )
    preview = (
        await act_as(world.manager).get(
            f"/api/assignments/{world.assignment.id}/quote-preview"
        )
    ).json()
    assert preview["default_conditions"] == "Verrekening per maand."


# -- the signing link ---------------------------------------------------------


async def _offer_link(act_as, world, quote: dict) -> dict:
    response = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/offers",
        json={"channel": "signing_link", "email": world.signer.email},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_the_link_comes_back_with_the_offer_and_lives_thirty_days(act_as, world):
    quote = await _issue(act_as, world)
    offered = await _offer_link(act_as, world, quote)
    offer = offered["offers"][0]
    invitation = offer["invitation"]
    assert invitation["signing_path"] == f"/tekenen/{quote['id']}"
    assert invitation["state"] == "invited"
    expires = datetime.fromisoformat(invitation["expires_at"])
    assert timedelta(days=29) < expires - datetime.now(UTC) <= timedelta(days=30)

    # It stays retrievable for whoever manages the assignment.
    again = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    assert again["offers"][0]["invitation"]["signing_path"] == f"/tekenen/{quote['id']}"

    # A reader of the figures sees that it was offered, not to whom or where.
    seen = (await act_as(world.lezer).get(f"/api/quotes/{quote['id']}")).json()
    assert seen["offers"][0]["channel"] == "signing_link"
    assert seen["offers"][0].get("invitation") is None
    assert seen["offers"][0].get("recipient") is None


async def test_opening_is_seen_and_withdrawing_closes_the_link(act_as, world):
    quote = await _issue(act_as, world)
    offered = await _offer_link(act_as, world, quote)
    invitation_id = offered["offers"][0]["invitation"]["id"]

    assert (
        await act_as(world.signer).get(f"/api/signing/quotes/{quote['id']}")
    ).status_code == 200
    state = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    assert state["offers"][0]["invitation"]["state"] == "opened"
    assert state["offers"][0]["invitation"]["opened_at"] is not None

    # Only whoever manages the assignment withdraws or renews.
    for person in (world.lezer, world.planner, world.signer):
        refused = await act_as(person).post(
            f"/api/quotes/{quote['id']}/invitations/{invitation_id}/withdraw"
        )
        assert refused.status_code in (403, 404), person.email

    withdrawn = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/invitations/{invitation_id}/withdraw"
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["offers"][0]["invitation"]["state"] == "withdrawn"
    signer = act_as(world.signer)
    assert (await signer.get(f"/api/signing/quotes/{quote['id']}")).status_code == 404
    assert (await signer.get("/api/signing/invitations")).json() == {"invitations": []}
    refused = await signer.post(
        f"/api/signing/quotes/{quote['id']}/accept",
        json={"quote_hash": quote["snapshot_hash"], "confirm_mandate": True},
    )
    assert refused.status_code == 404

    renewed = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/invitations/{invitation_id}/renew"
    )
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["offers"][0]["invitation"]["state"] == "opened"
    assert (
        await act_as(world.signer).get(f"/api/signing/quotes/{quote['id']}")
    ).status_code == 200


async def test_a_signed_link_shows_as_signed_and_cannot_be_withdrawn(act_as, world):
    quote = await _issue(act_as, world)
    offered = await _offer_link(act_as, world, quote)
    invitation_id = offered["offers"][0]["invitation"]["id"]
    accepted = await act_as(world.signer).post(
        f"/api/signing/quotes/{quote['id']}/accept",
        json={"quote_hash": quote["snapshot_hash"], "confirm_mandate": True},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["reference"] == quote["reference"]
    state = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    assert state["offers"][0]["invitation"]["state"] == "signed"
    refused = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/invitations/{invitation_id}/withdraw"
    )
    assert refused.status_code == 422
