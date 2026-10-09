"""The texts of a vacancy as work: versions, rounds of review, remarks,
settling, the standard texts and the public address. All data is fictional."""

from __future__ import annotations

import pytest

from grip.models.vacancy_text_flow import VacancyTextTemplate
from grip.services.vacancies import library, text_flow
from tests.vacancies.conftest import FakeChatClient

BASE = "/api/vacancies"


async def _create(client, budget_line, **extra):
    body = {"budget_line_id": str(budget_line.id), "vacancy_type": "regulier", **extra}
    response = await client.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _work(client, vacancy_id, kind="vacancy_text"):
    response = await client.get(f"{BASE}/{vacancy_id}/text-work")
    assert response.status_code == 200, response.text
    return next(t for t in response.json()["texts"] if t["kind"] == kind)


async def _save(client, vacancy_id, body, based_on=None, kind="vacancy_text"):
    return await client.post(
        f"{BASE}/{vacancy_id}/text-work/versions",
        json={"kind": kind, "body": body, "based_on_id": based_on},
    )


@pytest.fixture
async def shipped(db_session):
    await library.load_profile(db_session, "digigilde")
    await db_session.flush()


# --- the library ---------------------------------------------------------------


async def test_loading_is_idempotent_and_keeps_what_a_person_changed(
    db_session, beheerder
) -> None:
    first = await library.load_profile(db_session, "digigilde")
    assert first.added > 10 and first.updated == 0
    again = await library.load_profile(db_session, "digigilde")
    assert again.added == 0 and again.updated == 0

    template = (await library.list_templates(db_session))[0]
    await library.save_template(
        db_session,
        template.id,
        actor=beheerder,
        role_name=template.role_name,
        sections=[{"key": "intro", "heading": "", "body": "Onze eigen tekst."}],
    )
    # A newer shipped version arrives: the changed text stays, others follow.
    for row in await library.list_templates(db_session):
        if row.id != template.id:
            row.shipped_version = "2020-01-01"
    await db_session.flush()
    result = await library.load_profile(db_session, "digigilde")
    assert result.updated >= 10
    kept = await db_session.get(VacancyTextTemplate, template.id)
    assert kept.sections == [
        {"key": "intro", "heading": "", "body": "Onze eigen tekst."}
    ]


async def test_shipped_texts_name_no_person_and_no_personal_contact(
    shipped, db_session, create_person
):
    import re

    await create_person("iemand@example.org", name="Fictieve Persoon")
    texts = [s.body + s.heading for s in await library.shared_sections(db_session)]
    for template in await library.list_templates(db_session):
        texts += [e.get("body", "") + e.get("heading", "") for e in template.sections]
    everything = "\n".join(texts)
    assert "Fictieve Persoon" not in everything
    assert not re.search(r"\b0\d[\d \-]{7,}\b", everything), "a phone number"
    assert not re.search(r"[\w.]+@[\w.]+\.\w+", everything), "a mail address"
    assert not re.search(r"\bbel dan\b.*\b[A-Z][a-z]+ [A-Z][a-z]+", everything)
    # Nothing but known placeholders between braces.
    assert set(re.findall(r"\{([a-z_]+)\}", everything)) <= set(library.PLACEHOLDERS)


async def test_a_shared_section_changed_once_shows_in_every_role(
    shipped, db_session, beheerder, client, act_as, budget_line, manager
) -> None:
    await library.update_shared_section(
        db_session,
        "dit_bieden_we",
        heading="Dit bieden we",
        body="Eén nieuwe zin.",
        actor=beheerder,
    )
    shared = {s.key: s for s in await library.shared_sections(db_session)}
    for template in await library.list_templates(db_session):
        text = library.resolve(template, shared, {"functie": "X"}).text
        assert "## Dit bieden we\n\nEén nieuwe zin." in text


async def test_library_is_read_by_who_makes_vacancies_and_changed_by_the_beheerder(
    shipped, client, act_as, beheerder, planner, colleague
) -> None:
    act_as(colleague)
    assert (await client.get("/api/vacancy-texts")).status_code == 403
    act_as(planner)
    seen = await client.get("/api/vacancy-texts")
    assert seen.status_code == 200 and seen.json()["may_manage"] is False
    key = seen.json()["shared_sections"][0]["key"]
    refused = await client.put(
        f"/api/vacancy-texts/shared/{key}", json={"heading": "Kop", "body": "Tekst"}
    )
    assert refused.status_code == 403
    act_as(beheerder)
    changed = await client.put(
        f"/api/vacancy-texts/shared/{key}", json={"heading": "Kop", "body": "Tekst"}
    )
    assert changed.status_code == 200, changed.text
    derived = [
        t for t in changed.json()["templates"] if t["status"] == "derived_unread"
    ]
    assert derived, "derived texts start unread"
    read = await client.post(f"/api/vacancy-texts/templates/{derived[0]['id']}/read")
    by_id = {t["id"]: t for t in read.json()["templates"]}
    assert by_id[derived[0]["id"]]["status"] == "derived"


# --- the standard text on a vacancy --------------------------------------------


async def test_standard_text_lands_as_a_draft_with_its_origin(
    shipped, client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(
        client, budget_line, function_title="Software engineer", scale=12
    )
    before = await _work(client, vacancy["id"])
    assert before["state"] == "none"
    assert before["action"] == {"key": "start", "text": "Begin met de standaardtekst"}
    assert before["standard_text"]["role"] == "Software engineer"

    response = await client.post(f"{BASE}/{vacancy['id']}/text-work/standard")
    assert response.status_code == 201, response.text
    work = await _work(client, vacancy["id"])
    assert work["state"] == "draft"
    version = work["versions"][0]
    assert version["source"] == "template"
    assert version["origin"].startswith(
        "Uit de standaardtekst Software engineer, versie "
    )
    assert "## Dit ga je doen" in version["body"]
    # The draft names a fact by key and reads with its value.
    assert "Salaris in schaal {schaal}" in version["body"]
    assert "Salaris in schaal 12" in version["text"]
    # 0.8 fte of a 36 hour week.
    assert "29 uur per week" in version["text"]
    # What the vacancy could not supply is named, and blocks settling.
    assert any("reageren kan" in passage for passage in work["open_passages"])
    assert work["may_settle"] is False
    settle = await client.post(
        f"{BASE}/{vacancy['id']}/text-work/versions/{version['id']}/settle"
    )
    assert settle.status_code == 422
    assert "nog iets om in te vullen" in settle.json()["detail"]
    # Not settled, so nothing leaves grip.
    detail = (await client.get(f"{BASE}/{vacancy['id']}")).json()
    assert not any(t["is_current"] for t in detail["texts"])


async def test_nearest_text_is_used_and_said_when_the_role_has_none(
    shipped, client, act_as, planner
) -> None:
    act_as(planner)
    response = await client.post(
        BASE,
        json={
            "function_title": "Informatiebeveiliger",
            "fte": "1",
            "vacancy_type": "regulier",
            "fgr_function_name": "Expert Iv",
        },
    )
    assert response.status_code == 201, response.text
    work = await _work(client, response.json()["id"])
    assert work["standard_text"]["match"] == "function_group"
    assert work["standard_text"]["role"] == "Product owner"


# --- writing together ----------------------------------------------------------


async def test_two_writers_cannot_overwrite_each_other(
    client, act_as, manager, planner, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    first = await _save(client, vacancy["id"], "## Dit ga je doen\n\nEerste versie.")
    assert first.status_code == 201, first.text
    start = (await _work(client, vacancy["id"]))["versions"][-1]["id"]

    act_as(planner)
    theirs = await _save(
        client, vacancy["id"], "## Dit ga je doen\n\nVan de planner.", start
    )
    assert theirs.status_code == 201

    act_as(manager)
    mine = await _save(
        client, vacancy["id"], "## Dit ga je doen\n\nVan de eigenaar.", start
    )
    assert mine.status_code == 409
    assert "Fictieve Planner" in mine.json()["detail"]
    work = await _work(client, vacancy["id"])
    assert [v["number"] for v in work["versions"]] == [1, 2]
    assert "Van de planner." in work["versions"][-1]["body"]
    assert work["latest_changes"][0]["summary"].startswith(
        "Dit ga je doen: 1 alinea herschreven"
    )


# --- back and forth ------------------------------------------------------------


async def test_rounds_of_review_until_settled(
    client, act_as, manager, adviser, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    await _save(client, vid, "## Dit ga je doen\n\nEerste versie.")
    v1 = (await _work(client, vid))["versions"][-1]["id"]

    alone = await client.post(
        f"{BASE}/{vid}/text-work/reviews",
        json={"kind": "vacancy_text", "reviewer_ids": [str(manager.id)]},
    )
    assert alone.status_code == 422
    offered = await client.post(
        f"{BASE}/{vid}/text-work/reviews",
        json={
            "kind": "vacancy_text",
            "reviewer_ids": [str(adviser.id)],
            "note": "Kijk je mee?",
        },
    )
    assert offered.status_code == 201, offered.text
    work = await _work(client, vid)
    assert work["state"] == "in_review"
    assert work["with_whom"] == "Wacht op het oordeel van Fictieve Adviseur"
    assert work["may_write"] is False
    assert (await _save(client, vid, "Toch nog iets.", v1)).status_code == 422
    review_id = work["rounds"][0]["id"]

    # Someone who was not asked sees nothing; the reviewer sees the text
    # without names and can judge and remark, and nothing else.
    act_as(colleague)
    assert (await client.get(f"{BASE}/{vid}/text-work")).status_code == 404
    act_as(adviser)
    seen = await _work(client, vid)
    assert seen["action"]["key"] == "judge"
    assert seen["viewer_review_id"] == review_id
    assert "created_by_name" not in seen["versions"][0]
    assert (await _save(client, vid, "Ik herschrijf het.", v1)).status_code == 403
    empty = await client.post(
        f"{BASE}/{vid}/text-work/reviews/{review_id}/verdict",
        json={"verdict": "remarks"},
    )
    assert empty.status_code == 422
    remark = await client.post(
        f"{BASE}/{vid}/text-work/remarks",
        json={
            "kind": "vacancy_text",
            "section": "Dit ga je doen",
            "body": "Te algemeen.",
        },
    )
    assert remark.status_code == 201, remark.text
    back = await client.post(
        f"{BASE}/{vid}/text-work/reviews/{review_id}/verdict",
        json={"verdict": "remarks"},
    )
    assert back.status_code == 200, back.text
    twice = await client.post(
        f"{BASE}/{vid}/text-work/reviews/{review_id}/verdict",
        json={"verdict": "agreed"},
    )
    assert twice.status_code == 422

    act_as(manager)
    work = await _work(client, vid)
    assert work["state"] == "returned"
    assert work["action"]["key"] == "process"
    remark_id = work["remarks"][0]["id"]
    answered = await client.post(
        f"{BASE}/{vid}/text-work/remarks",
        json={"kind": "vacancy_text", "body": "Aangepast.", "parent_id": remark_id},
    )
    assert answered.status_code == 201
    resolved = await client.post(
        f"{BASE}/{vid}/text-work/remarks/{remark_id}/resolve", json={"resolved": True}
    )
    assert resolved.status_code == 200
    assert (
        await _save(client, vid, "## Dit ga je doen\n\nTweede versie, concreter.", v1)
    ).status_code == 201
    work = await _work(client, vid)
    assert work["state"] == "draft"
    assert work["remarks"][0]["resolved_at"] is not None
    assert work["remarks"][0]["answers"][0]["body"] == "Aangepast."

    again = await client.post(
        f"{BASE}/{vid}/text-work/reviews",
        json={"kind": "vacancy_text", "reviewer_ids": [str(adviser.id)]},
    )
    assert again.status_code == 201
    round_two = (await _work(client, vid))["rounds"][-1]
    assert round_two["round"] == 2
    act_as(adviser)
    agreed = await client.post(
        f"{BASE}/{vid}/text-work/reviews/{round_two['id']}/verdict",
        json={"verdict": "agreed"},
    )
    assert agreed.status_code == 200

    act_as(manager)
    work = await _work(client, vid)
    assert work["state"] == "agreed" and work["action"]["key"] == "settle"
    assert [r["outcome"] for r in work["rounds"]] == ["returned", "agreed"]
    latest = work["versions"][-1]["id"]
    old = await client.post(f"{BASE}/{vid}/text-work/versions/{v1}/settle")
    assert old.status_code == 422
    settled = await client.post(f"{BASE}/{vid}/text-work/versions/{latest}/settle")
    assert settled.status_code == 200, settled.text
    work = await _work(client, vid)
    assert work["state"] == "settled"
    detail = (await client.get(f"{BASE}/{vid}")).json()
    assert [t["id"] for t in detail["texts"] if t["is_current"]] == [latest]

    # Writing on after settling: the settled text stays what leaves grip,
    # and the screen says it is being revised.
    reopened = await _save(client, vid, "## Dit ga je doen\n\nDerde versie.", latest)
    assert reopened.status_code == 201
    work = await _work(client, vid)
    assert work["state"] == "draft" and work["revising"] is True
    detail = (await client.get(f"{BASE}/{vid}")).json()
    assert [t["id"] for t in detail["texts"] if t["is_current"]] == [latest]


async def test_the_writer_takes_the_text_back(
    client, act_as, manager, adviser, budget_line
):
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    await _save(client, vid, "Motivatie in een alinea.", kind="motivation")
    await client.post(
        f"{BASE}/{vid}/text-work/reviews",
        json={"kind": "motivation", "reviewer_ids": [str(adviser.id)]},
    )
    work = await _work(client, vid, "motivation")
    review_id = work["rounds"][0]["id"]
    assert work["action"]["key"] == "withdraw"
    taken = await client.post(f"{BASE}/{vid}/text-work/reviews/{review_id}/withdraw")
    assert taken.status_code == 200
    work = await _work(client, vid, "motivation")
    assert work["state"] == "draft" and work["rounds"][0]["outcome"] == "withdrawn"
    # The reviewer is no longer asked, and no longer reads the vacancy.
    act_as(adviser)
    assert (await client.get(f"{BASE}/{vid}/text-work")).status_code == 404


def test_a_vacancy_for_a_ready_candidate_needs_no_vacancy_text() -> None:
    from grip.models.vacancy import Vacancy

    for kind, needed in (
        ("regulier", True),
        ("specialistisch", True),
        ("gerede", False),
        ("beoogd", False),
    ):
        vacancy = Vacancy(vacancy_type=kind)
        assert text_flow.is_needed(vacancy, "vacancy_text") is needed
        assert text_flow.is_needed(vacancy, "motivation") is True


def test_compare_says_what_changed_in_words() -> None:
    before = (
        "Opening.\n\n## Dit ga je doen\n\nEen.\n\nTwee."
        "\n\n## Dit vragen wij\n\n- a\n- b"
    )
    after = (
        "Opening.\n\n## Dit ga je doen\n\nEen.\n\nTwee, maar anders en langer."
        "\n\n## Dit krijg je\n\nIets."
    )
    changes = {c.heading: c for c in text_flow.compare(before, after)}
    assert changes[""].change == "same"
    assert changes["Dit ga je doen"].summary == (
        "Dit ga je doen: 1 alinea herschreven, 4 woorden langer."
    )
    assert changes["Dit vragen wij"].change == "removed"
    assert changes["Dit krijg je"].summary == "Dit krijg je: toegevoegd."


# --- a tailored draft ----------------------------------------------------------


@pytest.fixture
def tailored_model(monkeypatch) -> FakeChatClient:
    fake = FakeChatClient(
        "## Inleiding\n\nBouw mee aan iets dat ertoe doet.\n\n"
        "## Dit ga je doen\n\nJe bouwt en test.\n\n- bouwen\n- testen\n\n"
        "## Dit vragen wij\n\nJe hebt ervaring.\n\n"
        "## Dit bieden we nog meer\n\nEen leaseauto en een bonus."
    )
    monkeypatch.setattr(
        "grip.services.vacancies.text_flow.get_chat_client", lambda *a, **k: fake
    )
    return fake


async def test_tailored_draft_sends_examples_and_facts_and_never_boilerplate(
    shipped,
    client,
    act_as,
    manager,
    budget_line,
    tailored_model,
    db_session,
    create_person,
) -> None:
    await create_person("kandidaat@example.org", name="Karel Kandidaatsma")
    act_as(manager)
    vacancy = await _create(
        client, budget_line, function_title="Software engineer", scale=12
    )
    vid = vacancy["id"]
    named = await client.post(
        f"{BASE}/{vid}/text-work/tailored",
        json={"instruction": "Schrijf het zoals Karel Kandidaatsma het zou willen."},
    )
    assert named.status_code == 422 and not tailored_model.calls

    response = await client.post(
        f"{BASE}/{vid}/text-work/tailored",
        json={"instruction": "Leg nadruk op open source."},
    )
    assert response.status_code == 201, response.text
    sent = tailored_model.calls[0]
    user = sent["user"]
    assert "<gegevens>" in user and "Rol: Software engineer" in user
    assert "Schaal: schaal 12" in user and "Opdracht: Opdracht Alfa" in user
    assert "<aanwijzing>\nLeg nadruk op open source.\n</aanwijzing>" in user
    assert '<voorbeeld nummer="1" rol="Software engineer">' in user
    # The shared sections are never sent and never asked for.
    assert "keuzebudget" not in user and "Dit bieden we nog meer" not in user
    assert "sollicitatieknop" not in user
    # No rate, no cost, no name of a colleague.
    for forbidden in ("tarief", "€", "Fictieve Eigenaar", "Karel", "eigenaar@"):
        assert forbidden not in user, forbidden
    assert "je-vorm" in sent["system"] and "Beloof niets over salaris" in sent["system"]

    work = await _work(client, vid)
    version = work["versions"][-1]
    assert version["source"] == "model"
    assert version["origin"].startswith(
        "Opgesteld met VLAM, testmodel-1, met de standaardtekst"
    )
    body = version["body"]
    assert "Bouw mee aan iets dat ertoe doet." in body
    assert "## Dit ga je doen\n\nJe bouwt en test." in body
    # Boilerplate is inserted from the library, not taken from the model.
    assert "leaseauto" not in body
    assert "individueel keuzebudget" in body
    assert work["state"] == "draft"
    # A draft never leaves unsettled.
    detail = (await client.get(f"{BASE}/{vid}")).json()
    assert not any(t["is_current"] for t in detail["texts"])


def test_the_local_model_is_refused_outside_development() -> None:
    from grip.core.config import Settings
    from grip.services.llm.client import (
        ClaudeCliClient,
        active_provider,
        provider_label,
    )

    with pytest.raises(ValueError, match="alleen voor lokale ontwikkeling"):
        Settings(
            LLM_PROVIDER="claude_cli",
            OIDC_ISSUER="https://login.example.org/realms/x",
            SESSION_SECRET_KEY="x" * 48,
            DEV_NO_AUTH=False,
            _env_file=None,
        )
    # Deployed: refused whatever else is set (another check fires first).
    with pytest.raises(ValueError):
        Settings(
            LLM_PROVIDER="claude_cli",
            DEV_NO_AUTH=True,
            PUBLIC_HOST="grip.example.org",
            _env_file=None,
        )
    local = Settings(LLM_PROVIDER="claude_cli", DEV_NO_AUTH=True, _env_file=None)
    assert active_provider(local) == "claude_cli"
    client = ClaudeCliClient(command="claude", model="sonnet", timeout=5)
    assert client.model_id == "claude-cli:sonnet"
    assert (
        provider_label(client.model_id)
        == "Claude via de lokale ontwikkelomgeving, sonnet"
    )
    assert provider_label("testmodel-1") == "VLAM, testmodel-1"
    arguments = client._arguments("systeem")
    assert arguments[arguments.index("--tools") + 1] == ""
    assert "--no-session-persistence" in arguments and "--print" in arguments
    text = client._parse(
        '{"type":"result","is_error":false,"result":"Hallo","modelUsage":{"model-x":{}}}',
        "",
    )
    assert text == "Hallo" and client.model_id == "claude-cli:model-x"


# --- where the vacancy is published --------------------------------------------


async def test_public_address_is_recorded_once_the_vacancy_is_open(
    client, act_as, manager, beheerder, budget_line, db_session
) -> None:
    from grip.models.vacancy import Vacancy

    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    link = {
        "place": "government_wide",
        "url": "https://www.werkenvoornederland.example/v/1",
    }
    early = await client.put(f"{BASE}/{vid}/publications", json=link)
    assert early.status_code == 422

    row = await db_session.get(Vacancy, vacancy["id"])
    row.status = "open"
    await db_session.flush()
    seen = (await client.get(f"{BASE}/{vid}/text-work")).json()
    assert (
        seen["publication_missing"] is True and seen["may_record_publication"] is True
    )
    plain = await client.put(
        f"{BASE}/{vid}/publications",
        json={**link, "url": "http://onveilig.example/v/1"},
    )
    assert plain.status_code == 422
    stored = await client.put(f"{BASE}/{vid}/publications", json=link)
    assert stored.status_code == 200, stored.text
    body = stored.json()
    assert body["publication_missing"] is False
    assert body["publications"][0]["place_text"] == "Werken voor Nederland"
    removed = await client.delete(
        f"{BASE}/{vid}/publications/{body['publications'][0]['id']}"
    )
    assert removed.json()["publications"] == []
