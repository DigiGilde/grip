"""The text of a quote: the draft, what is frozen, and what reaches the model.

All names, texts and amounts are fictional.
"""

from __future__ import annotations

import json

import pytest

from grip.models.quote import Quote
from grip.services import instance_settings, quote_drafts, quote_sender, terms
from grip.services.errors import DomainValidationError
from grip.services.quote_drafting import (
    ALLOWED_INPUT_FIELDS,
    ALLOWED_ROLE_FIELDS,
    build_prompt,
)
from tests.api.quotes.conftest import document_text

SENDER = {
    "organisation": "Voorbeeldorganisatie voor Uitvoering",
    "part_of": ["Voorbeeldministerie"],
    "unit": "VU | Voorbeeldgilde",
    "visiting_address": ["Voorbeeldlaan 1", "1234 AB Voorbeeldstad"],
    "postal_address": ["Postbus 99", "1200 AA Voorbeeldstad"],
    "orders_email": "opdrachten@voorbeeld.example",
    "contact": {"name": "", "role": "", "email": "", "phone": ""},
    "signatory": {
        "on_behalf_of": "het Voorbeeldgilde",
        "name": "Dirk Directeur",
        "title": "Directeur",
        "organisation": "",
    },
}

BLOCKS = [
    {"key": "inleiding", "heading": "Inleiding", "draftable": True},
    {"key": "kosten", "heading": "Kosten", "with_costs": True},
    {
        "key": "voorwaarden",
        "heading": "Leveringsvoorwaarden",
        "body": "1. Facturatie per kwartaal.\n2. Vragen aan {opdrachtenadres}.",
    },
]


class FakeModel:
    model_id = "voorbeeldmodel-1"

    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str, max_tokens: int = 1500) -> str:
        self.requests.append((system, user))
        return "Een concept van het model over de opgave."


@pytest.fixture
async def configured(db_session, world):
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


async def _write(act_as, world, key: str, body: str) -> dict:
    response = await act_as(world.manager).put(
        f"/api/assignments/{world.assignment.id}/quote-draft/sections/{key}",
        json={"body": body},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _issue(act_as, world, expect: int = 201):
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == expect, response.text
    return response.json()


async def test_a_new_draft_starts_from_the_texts_of_the_organisation(
    act_as, configured
):
    world = configured
    response = await act_as(world.manager).get(
        f"/api/assignments/{world.assignment.id}/quote-draft"
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["saved"] is False and draft["may_edit"] is True
    assert [s["key"] for s in draft["sections"]] == [
        "inleiding",
        "kosten",
        "voorwaarden",
    ]
    terms_section = draft["sections"][2]
    assert terms_section["origin"] == "standard"
    # A placeholder is filled in when the draft starts.
    assert "opdrachten@voorbeeld.example" in terms_section["body"]
    assert draft["problems"] == [{"key": "inleiding", "problem": "Nog geen tekst."}]


async def test_the_text_is_part_of_what_is_hashed(act_as, configured, db_session):
    world = configured
    await _write(act_as, world, "inleiding", "De opgave is groot, en dringend.")
    first = await _issue(act_as, world)
    await _write(act_as, world, "inleiding", "De opgave is groot en dringend.")
    second = await _issue(act_as, world)
    assert first["snapshot_hash"] != second["snapshot_hash"]

    quote = await db_session.get(Quote, second["id"])
    letter = quote.snapshot["letter"]
    assert letter["sections"][0]["body"] == "De opgave is groot en dringend."
    assert [s["key"] for s in letter["sections"]] == [
        "inleiding",
        "kosten",
        "voorwaarden",
    ]
    assert quote.prose_provenance == [
        {"key": "inleiding", "origin": "written"},
        {"key": "kosten", "origin": "empty"},
        {"key": "voorwaarden", "origin": "standard"},
    ]


async def test_the_canonical_form_carries_the_letter_in_contract_terms(
    act_as, configured, db_session
):
    world = configured
    await _write(act_as, world, "inleiding", "Een tekst.")
    issued = await _issue(act_as, world)
    quote = await db_session.get(Quote, issued["id"])
    canonical = json.loads(quote.canonical)
    letter = canonical["brief"]
    assert letter["betreft"] == "Offerte Opdracht Alfa"
    assert letter["onderdelen"][0] == {
        "sleutel": "inleiding",
        "kop": "Inleiding",
        "tekst": "Een tekst.",
        "met_kosten": False,
        "genummerd": True,
    }
    assert letter["afzendergegevens"]["bezoekadres"] == [
        "Voorbeeldlaan 1",
        "1234 AB Voorbeeldstad",
    ]
    assert letter["ondertekening"][0]["namens"] == "het Voorbeeldgilde"
    assert letter["bijlage_factuurinformatie"] is True
    # And back: what the screens read is the code form of the same content.
    assert terms.from_contract(canonical)["letter"] == quote.snapshot["letter"]


async def test_a_quote_cannot_be_made_with_an_empty_section(act_as, configured):
    world = configured
    await _write(act_as, world, "voorwaarden", "1. Facturatie per kwartaal.")
    body = await _issue(act_as, world, expect=422)
    assert "Inleiding" in json.dumps(body, ensure_ascii=False)


async def test_the_name_of_a_colleague_in_a_section_stops_the_making(
    act_as, configured
):
    world = configured
    await _write(
        act_as, world, "inleiding", f"Het werk wordt gedaan door {world.member.name}."
    )
    body = await _issue(act_as, world, expect=422)
    text = json.dumps(body, ensure_ascii=False)
    assert "het onderdeel 'Inleiding'" in text
    assert world.member.name not in text


async def test_a_drafted_section_counts_only_after_a_person_saved_it(
    act_as, configured, db_session
):
    world = configured
    model = FakeModel()
    content = await quote_drafts.draft_section(
        db_session, world.assignment, "inleiding", actor=world.manager, client=model
    )
    section = content["sections"][0]
    assert section["origin"] == "generated" and section["settled"] is False
    assert section["generated"]["model"] == "voorbeeldmodel-1"

    refused = await _issue(act_as, world, expect=422)
    assert "nog niemand heeft vastgesteld" in json.dumps(refused, ensure_ascii=False)

    saved = await _write(act_as, world, "inleiding", section["body"] + " Aangevuld.")
    assert saved["sections"][0]["settled"] is True
    assert saved["sections"][0]["origin"] == "generated"
    issued = await _issue(act_as, world)
    quote = await db_session.get(Quote, issued["id"])
    assert quote.prose_provenance[0]["origin"] == "generated"
    assert quote.prose_provenance[0]["generated"]["model"] == "voorbeeldmodel-1"
    # How the text came about is not in what the client gets.
    assert "voorbeeldmodel" not in quote.canonical.decode()
    assert "taalmodel" not in quote.canonical.decode()


async def test_the_organisation_can_choose_to_say_a_model_was_used(
    act_as, configured, db_session
):
    world = configured
    await instance_settings.set_values(
        db_session, {quote_sender.AI_DISCLOSURE.key: True}, actor=world.beheerder
    )
    content = await quote_drafts.draft_section(
        db_session,
        world.assignment,
        "inleiding",
        actor=world.manager,
        client=FakeModel(),
    )
    await _write(act_as, world, "inleiding", content["sections"][0]["body"])
    issued = await _issue(act_as, world)
    quote = await db_session.get(Quote, issued["id"])
    assert quote_sender.AI_DISCLOSURE_SENTENCE in quote.snapshot["letter"]["closing"]


async def test_what_reaches_the_model_has_no_names_rates_or_amounts(
    configured, db_session
):
    world = configured
    model = FakeModel()
    await quote_drafts.draft_section(
        db_session, world.assignment, "inleiding", actor=world.manager, client=model
    )
    system, user = model.requests[0]
    sent = system + user
    assert "Productmanager" in user and "0,8 fte" in user
    assert "Opdracht Alfa" in user
    # Category D bills 18,000 a month here: no rate, no amount, no category.
    for forbidden in (
        "18000",
        "18.000",
        "1800000",
        "172800",
        "€",
        "categorie",
        "schaal",
    ):
        assert forbidden not in sent.replace("taalniveau", "")
    for person in (world.member, world.manager, world.beheerder):
        assert person.name not in sent
    assert ALLOWED_INPUT_FIELDS == {
        "heading",
        "hint",
        "assignment_name",
        "client_name",
        "sender_name",
        "period_start",
        "period_end",
        "roles",
        "context",
        "outline",
        "settled",
        "passage",
        "instruction",
    }
    assert ALLOWED_ROLE_FIELDS == {"role", "fte", "period_start", "period_end"}


async def test_a_name_in_the_text_never_goes_to_the_model(configured, db_session):
    world = configured
    model = FakeModel()
    with pytest.raises(DomainValidationError, match="naam van een persoon"):
        await quote_drafts.rewrite_passage(
            db_session,
            world.assignment,
            "inleiding",
            f"Het team onder leiding van {world.member.name} levert.",
            client=model,
        )
    assert model.requests == []


async def test_only_draftable_prose_is_drafted(configured, db_session):
    world = configured
    for key in ("kosten", "voorwaarden"):
        with pytest.raises(DomainValidationError, match="geen concept"):
            await quote_drafts.draft_section(
                db_session,
                world.assignment,
                key,
                actor=world.manager,
                client=FakeModel(),
            )


async def test_changing_the_standard_texts_leaves_an_existing_quote_alone(
    act_as, configured, db_session
):
    world = configured
    await _write(act_as, world, "inleiding", "Een tekst.")
    issued = await _issue(act_as, world)
    client = act_as(world.manager)
    before = (await client.get(f"/api/quotes/{issued['id']}/document")).content

    changed = [dict(block) for block in BLOCKS]
    changed[2]["body"] = "1. Heel andere voorwaarden."
    response = await act_as(world.beheerder).patch(
        "/api/quote-sender",
        json={
            "text_blocks": changed,
            "sender": {**SENDER, "organisation": "Een Andere Naam"},
        },
    )
    assert response.status_code == 200, response.text
    after = (
        await act_as(world.manager).get(f"/api/quotes/{issued['id']}/document")
    ).content
    assert before == after
    quote = await db_session.get(Quote, issued["id"])
    assert quote.snapshot["sender"] == "Voorbeeldorganisatie voor Uitvoering"


async def test_the_sender_from_beheer_goes_before_the_environment(
    act_as, world, db_session, monkeypatch
):
    from grip.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ORGANISATION_NAME", "Naam Uit De Omgeving")
    monkeypatch.setattr(get_settings(), "LETTERHEAD_LINES", "Lijn Een|Lijn Twee")
    start = await quote_sender.current_sender(db_session)
    assert start["organisation"] == "Naam Uit De Omgeving"
    assert start["part_of"] == ["Lijn Een", "Lijn Twee"]

    await instance_settings.set_values(
        db_session, {quote_sender.SENDER.key: SENDER}, actor=world.beheerder
    )
    issued = await _issue(act_as, world)
    assert (await db_session.get(Quote, issued["id"])).snapshot["sender"] == (
        "Voorbeeldorganisatie voor Uitvoering"
    )


async def test_a_quote_without_a_draft_is_the_table_as_before(
    act_as, world, db_session
):
    issued = await _issue(act_as, world)
    quote = await db_session.get(Quote, issued["id"])
    assert "letter" not in quote.snapshot
    assert quote.prose_provenance is None
    text = document_text(
        await act_as(world.manager).get(f"/api/quotes/{issued['id']}/document")
    )
    assert "Akkoord" in text and "Omschrijving" in text


async def test_the_document_is_the_letter_in_order(act_as, configured, db_session):
    world = configured
    await act_as(world.manager).patch(
        f"/api/assignments/{world.assignment.id}/quote-draft",
        json={
            "salutation": "Geachte heer Voorbeeld,",
            "addressee": ["Voorbeeldministerie", "Directie Voorbeeld"],
            "client_signatory": {
                "on_behalf_of": "Directie Voorbeeld",
                "name": "Dhr. V. Voorbeeld",
                "function": "Directeur",
                "organisation": "Voorbeeldministerie",
            },
        },
    )
    await _write(
        act_as,
        world,
        "inleiding",
        "De opgave in **twee** delen:\n\n- een eerste deel\n- een tweede deel",
    )
    issued = await _issue(act_as, world)
    text = document_text(
        await act_as(world.manager).get(f"/api/quotes/{issued['id']}/document")
    )
    order = [
        "Directie Voorbeeld",
        "Offerte Opdracht Alfa",
        "Geachte heer Voorbeeld,",
        "Hierbij de offerte.",
        "1. Inleiding",
        "een eerste deel",
        "2. Kosten",
        "Omschrijving",
        "Totaal",
        "3. Leveringsvoorwaarden",
        "Facturatie per kwartaal.",
        "Met vriendelijke groet.",
        "Voor akkoord",
        "namens het Voorbeeldgilde,",
        "Echtheidskenmerk",
        "Factuurinformatie",
    ]
    positions = [text.find(part) for part in order]
    assert all(position >= 0 for position in positions), list(zip(order, positions))
    assert positions == sorted(positions), list(zip(order, positions))
    assert "Voorbeeldlaan 1" in text and "Postbus 99" in text
    assert "Dhr. V. Voorbeeld" in text
    # Marks are lay-out, not characters on paper.
    assert "**" not in text


async def test_who_may_read_and_change_the_draft(act_as, configured):
    world = configured
    url = f"/api/assignments/{world.assignment.id}/quote-draft"
    assert (await act_as(world.planner).get(url)).status_code == 403
    assert (await act_as(world.outsider).get(url)).status_code == 404
    lezer = await act_as(world.lezer).get(url)
    assert lezer.status_code == 200 and lezer.json()["may_edit"] is False
    refused = await act_as(world.lezer).put(
        f"{url}/sections/inleiding", json={"body": "x"}
    )
    assert refused.status_code == 403
    assert (await act_as(world.manager).get("/api/quote-sender")).status_code == 403
    assert (await act_as(world.beheerder).get("/api/quote-sender")).status_code == 200


async def test_a_profile_sets_the_organisation_and_leaves_the_people(
    act_as, world, db_session
):
    await instance_settings.set_values(
        db_session,
        {
            quote_sender.SENDER.key: {
                **SENDER,
                "contact": {
                    "name": "Carla Contact",
                    "role": "",
                    "email": "",
                    "phone": "",
                },
            }
        },
        actor=world.beheerder,
    )
    response = await act_as(world.beheerder).post(
        "/api/quote-sender/profiles/digigilde"
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["sender"]["contact"]["name"] == "Carla Contact"
    assert out["sender"]["visiting_address"]
    assert any(block["with_costs"] for block in out["text_blocks"])
    # A profile is organisation data: it names no person.
    profile = quote_sender.load_profile("digigilde")
    assert not profile["sender"].get("contact")
    assert "name" not in profile["sender"].get("signatory", {})


def test_the_prompt_for_a_rewrite_carries_only_the_passage():
    from grip.services.quote_drafting import SectionInput

    system, user = build_prompt(
        SectionInput(heading="Inleiding", passage="Een zin.", instruction="Korter.")
    )
    assert "Een zin." in user and "Korter." in user
    assert "geen namen van personen" in system


# --- two writers, and what a writer may do with a section ---------------------------


async def test_a_stale_save_is_refused_with_what_is_there_now(act_as, configured):
    world = configured
    url = f"/api/assignments/{world.assignment.id}/quote-draft"
    first = await _write(act_as, world, "inleiding", "Eerste tekst.")
    version = first["sections"][0]["version"]
    assert version == 1 and first["sections"][0]["changed_by"] == world.manager.name

    # Someone saves in between; the writer still holds the old version.
    await _write(act_as, world, "inleiding", "Tekst van een ander.")
    stale = await act_as(world.manager).put(
        f"{url}/sections/inleiding", json={"body": "Mijn tekst.", "version": version}
    )
    assert stale.status_code == 409, stale.text
    problem = stale.json()
    assert problem["changed_by"] == world.manager.name and problem["changed_at"]
    assert problem["current"]["sections"][0]["body"] == "Tekst van een ander."
    assert problem["current"]["sections"][0]["version"] == 2

    # With the version that is there now the save goes through.
    ok = await act_as(world.manager).put(
        f"{url}/sections/inleiding", json={"body": "Mijn tekst.", "version": 2}
    )
    assert ok.status_code == 200 and ok.json()["sections"][0]["version"] == 3
    # Another section is not touched by this: its version stands.
    assert ok.json()["sections"][2]["version"] == 0


async def test_the_head_and_the_outline_have_their_own_version(act_as, configured):
    world = configured
    url = f"/api/assignments/{world.assignment.id}/quote-draft"
    client = act_as(world.manager)
    head = await client.patch(url, json={"subject": "Offerte A", "head_version": 0})
    assert head.status_code == 200 and head.json()["head_version"] == 1
    stale = await client.patch(url, json={"subject": "Offerte B", "head_version": 0})
    assert stale.status_code == 409
    assert stale.json()["current"]["subject"] == "Offerte A"

    keys = ["inleiding", "kosten", "voorwaarden"]
    moved = await client.put(
        f"{url}/outline", json={"keys": keys, "outline_version": 0}
    )
    assert moved.status_code == 200 and moved.json()["outline_version"] == 1
    again = await client.put(
        f"{url}/outline", json={"keys": keys, "outline_version": 0}
    )
    assert again.status_code == 409


async def test_the_outline_of_the_organisation_says_what_a_writer_may_do(
    act_as, configured, db_session
):
    world = configured
    blocks = [dict(block) for block in BLOCKS]
    blocks[2]["required"] = True
    await instance_settings.set_values(
        db_session, {quote_sender.TEXT_BLOCKS.key: blocks}, actor=world.beheerder
    )
    url = f"/api/assignments/{world.assignment.id}/quote-draft"
    client = act_as(world.manager)
    draft = (await client.get(url)).json()
    rules = {
        s["key"]: (s["optional"], s["removable"], s["movable"])
        for s in draft["sections"]
    }
    assert rules == {
        "inleiding": (True, False, True),
        # The amounts stand somewhere in every quote, wherever the writer puts them.
        "kosten": (False, False, True),
        "voorwaarden": (False, False, False),
    }

    # The server holds the same lines.
    left_out = await client.put(f"{url}/sections/voorwaarden", json={"included": False})
    assert left_out.status_code == 422 and "elke offerte" in left_out.json()["detail"]
    removed = await client.put(
        f"{url}/outline", json={"keys": ["kosten", "voorwaarden"]}
    )
    assert removed.status_code == 422 and "Laat het weg" in removed.json()["detail"]
    assert (
        await client.put(f"{url}/sections/inleiding", json={"included": False})
    ).status_code == 200

    # A section the writer adds may move and may go again.
    added = await client.put(
        f"{url}/outline",
        json={
            "keys": ["eigen", "inleiding", "kosten", "voorwaarden"],
            "new_sections": [{"key": "eigen", "heading": "Eigen onderdeel"}],
        },
    )
    assert added.status_code == 200, added.text
    own = added.json()["sections"][0]
    assert (own["optional"], own["removable"], own["movable"]) == (True, True, True)
    gone = await client.put(
        f"{url}/outline", json={"keys": ["inleiding", "kosten", "voorwaarden"]}
    )
    assert gone.status_code == 200
    assert [s["key"] for s in gone.json()["sections"]] == [
        "inleiding",
        "kosten",
        "voorwaarden",
    ]


async def test_required_sections_keep_their_order(act_as, world, db_session):
    blocks = [
        {"key": "a", "heading": "A", "body": "Tekst.", "required": True},
        {"key": "tussen", "heading": "Tussen"},
        {"key": "b", "heading": "B", "body": "Tekst.", "required": True},
    ]
    await instance_settings.set_values(
        db_session, {quote_sender.TEXT_BLOCKS.key: blocks}, actor=world.beheerder
    )
    url = f"/api/assignments/{world.assignment.id}/quote-draft/outline"
    client = act_as(world.manager)
    swapped = await client.put(url, json={"keys": ["b", "tussen", "a"]})
    assert (
        swapped.status_code == 422 and "onderlinge volgorde" in swapped.json()["detail"]
    )
    moved = await client.put(url, json={"keys": ["tussen", "a", "b"]})
    assert moved.status_code == 200


# --- standard texts follow what holds now ------------------------------------------

YEAR_BLOCKS = [
    {"key": "inleiding", "heading": "Inleiding", "draftable": True},
    {"key": "kosten", "heading": "Kosten", "with_costs": True},
    {
        "key": "voorwaarden",
        "heading": "Leveringsvoorwaarden",
        "body": "1. Deze offerte is gebaseerd op de tarieven van {jaar}.",
    },
]


async def _with_year_blocks(db_session, world) -> None:
    await instance_settings.set_values(
        db_session, {quote_sender.TEXT_BLOCKS.key: YEAR_BLOCKS}, actor=world.beheerder
    )


async def test_the_rate_year_in_the_letter_is_the_year_of_the_budget(
    act_as, configured, db_session
):
    """Not the year the quote happens to be written in: the years the
    personnel lines run over, also when the budget moves after the draft
    was started."""
    world = configured
    await _with_year_blocks(db_session, world)
    await _write(act_as, world, "inleiding", "Wij helpen u graag.")
    draft = (
        await act_as(world.manager).get(
            f"/api/assignments/{world.assignment.id}/quote-draft"
        )
    ).json()
    assert "tarieven van 2026." in draft["sections"][2]["body"]

    # The line now runs into the next year: the saved draft follows.
    moved = await act_as(world.manager).patch(
        f"/api/budget-lines/{world.line.id}",
        json={"start_date": "2026-07-01", "end_date": "2027-06-30"},
    )
    assert moved.status_code == 200, moved.text
    draft = (
        await act_as(world.manager).get(
            f"/api/assignments/{world.assignment.id}/quote-draft"
        )
    ).json()
    assert "tarieven van 2026 en 2027." in draft["sections"][2]["body"]
    issued = await _issue(act_as, world)
    quote = await db_session.get(Quote, issued["id"])
    frozen = {s["key"]: s["body"] for s in quote.snapshot["letter"]["sections"]}
    assert "tarieven van 2026 en 2027." in frozen["voorwaarden"]


async def test_a_standard_text_a_person_changed_is_left_alone(
    act_as, configured, db_session
):
    world = configured
    await _with_year_blocks(db_session, world)
    await _write(act_as, world, "inleiding", "Wij helpen u graag.")
    await _write(act_as, world, "voorwaarden", "1. Eigen voorwaarden voor dit jaar.")
    await act_as(world.manager).patch(
        f"/api/budget-lines/{world.line.id}",
        json={"start_date": "2026-07-01", "end_date": "2027-06-30"},
    )
    draft = (
        await act_as(world.manager).get(
            f"/api/assignments/{world.assignment.id}/quote-draft"
        )
    ).json()
    assert draft["sections"][2]["body"] == "1. Eigen voorwaarden voor dit jaar."


async def test_a_quote_is_not_made_while_the_letter_would_print_an_empty_sender(
    act_as, configured, db_session
):
    """No signatory, and a closing that names a contact person nobody filled
    in: the draft says so, and making is refused with the place."""
    world = configured
    await instance_settings.set_values(
        db_session,
        {
            quote_sender.SENDER.key: {
                **SENDER,
                "signatory": {**SENDER["signatory"], "name": ""},
            },
            quote_sender.LETTER.key: {
                "opening": "Hierbij de offerte.",
                "closing": "**Contactpersoon {eenheid}**\n{contactpersoon}",
                "billing_annex": True,
            },
        },
        actor=world.beheerder,
    )
    await _write(act_as, world, "inleiding", "Wij helpen u graag.")
    draft = (
        await act_as(world.manager).get(
            f"/api/assignments/{world.assignment.id}/quote-draft"
        )
    ).json()
    assert draft["sender_problem"] == (
        "Onder Beheer, Afzender ontbreekt nog: de contactpersoon en de ondertekenaar."
    )
    assert draft["may_set_sender"] is False
    as_beheerder = (
        await act_as(world.beheerder).get(
            f"/api/assignments/{world.assignment.id}/quote-draft"
        )
    ).json()
    assert as_beheerder["may_set_sender"] is True
    refused = await _issue(act_as, world, expect=422)
    assert "de contactpersoon en de ondertekenaar" in json.dumps(
        refused, ensure_ascii=False
    )

    # Filled in under Beheer: the draft that was already saved follows.
    await instance_settings.set_values(
        db_session,
        {
            quote_sender.SENDER.key: {
                **SENDER,
                "contact": {
                    "name": "Carla Contact",
                    "role": "",
                    "email": "contact@voorbeeld.example",
                    "phone": "",
                },
            }
        },
        actor=world.beheerder,
    )
    draft = (
        await act_as(world.manager).get(
            f"/api/assignments/{world.assignment.id}/quote-draft"
        )
    ).json()
    assert draft["sender_problem"] is None
    assert "Carla Contact" in draft["closing"]
    issued = await _issue(act_as, world)
    quote = await db_session.get(Quote, issued["id"])
    assert "Carla Contact" in quote.snapshot["letter"]["closing"]
