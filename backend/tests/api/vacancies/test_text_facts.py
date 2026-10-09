"""A vacancy text follows the facts of its vacancy: a draft names them by
key, settling freezes them, and a later change is shown next to what the
settled text says. All data is fictional."""

from __future__ import annotations

import re

import pytest

from grip.dev import fix_open_places
from grip.models.vacancy import Vacancy, VacancyText
from grip.services.vacancies import library, text_flow
from tests.vacancies.conftest import FakeChatClient

BASE = "/api/vacancies"
SCALE_PLACE = "[vul aan: Vul de schaal in op de aanvraag]"


@pytest.fixture
async def shipped(db_session):
    await library.load_profile(db_session, "digigilde")
    await db_session.flush()


async def _create(client, budget_line, **extra):
    body = {
        "budget_line_id": str(budget_line.id),
        "vacancy_type": "regulier",
        "function_title": "Software engineer",
        **extra,
    }
    response = await client.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _work(client, vacancy_id, kind="vacancy_text"):
    response = await client.get(f"{BASE}/{vacancy_id}/text-work")
    assert response.status_code == 200, response.text
    return next(t for t in response.json()["texts"] if t["kind"] == kind)


async def _started(client, vacancy_id):
    response = await client.post(f"{BASE}/{vacancy_id}/text-work/standard")
    assert response.status_code == 201, response.text
    return await _work(client, vacancy_id)


async def _save(client, vacancy_id, body, based_on):
    response = await client.post(
        f"{BASE}/{vacancy_id}/text-work/versions",
        json={"kind": "vacancy_text", "body": body, "based_on_id": based_on},
    )
    assert response.status_code == 201, response.text
    return await _work(client, vacancy_id)


def _filled(body: str, facts: list[dict]) -> str:
    """The draft with every open place written, as a person would."""
    body = re.sub(r"\[vul aan[^\]]*\]", "een eigen zin", body)
    for fact in facts:
        if fact["value"] is None:
            body = body.replace("{" + fact["key"] + "}", "eigen woorden")
    return body


async def _settle(client, vacancy_id, version_id):
    return await client.post(
        f"{BASE}/{vacancy_id}/text-work/versions/{version_id}/settle"
    )


async def test_a_fact_filled_in_later_appears_in_the_draft(
    shipped, client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    work = await _started(client, vid)
    version = work["versions"][-1]
    # Unknown at the start: the key stays, the place says where to fill it.
    assert "Salaris in schaal {schaal}" in version["body"]
    assert f"Salaris in schaal {SCALE_PLACE}" in version["text"]
    assert "Vul de schaal in op de aanvraag" in work["open_passages"]
    assert "Kies het type contract op de aanvraag" in work["open_passages"]
    scale = next(fact for fact in work["facts"] if fact["key"] == "schaal")
    assert scale["value"] is None and scale["where"] == "request"
    settle = await _settle(client, vid, version["id"])
    assert settle.status_code == 422
    assert "Vul de schaal in op de aanvraag" in settle.json()["detail"]

    patched = await client.patch(
        f"{BASE}/{vid}",
        json={"scale": 12, "contract_type": "temporary_before_permanent"},
    )
    assert patched.status_code == 200, patched.text
    work = await _work(client, vid)
    version = work["versions"][-1]
    assert "Salaris in schaal 12" in version["text"]
    assert (
        "- Een jaarcontract met uitzicht op een vast dienstverband" in (version["text"])
    )
    assert not any("aanvraag" in passage for passage in work["open_passages"])
    scale = next(fact for fact in work["facts"] if fact["key"] == "schaal")
    assert scale["value"] == "12" and scale["source"] == "uit de aanvraag: Schaal"


async def test_a_changed_fact_follows_a_draft_and_flags_a_settled_text(
    shipped, client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(
        client, budget_line, scale=12, contract_type="temporary_project"
    )
    vid = vacancy["id"]
    work = await _started(client, vid)
    await client.patch(f"{BASE}/{vid}", json={"scale": 13})
    work = await _work(client, vid)
    assert "Salaris in schaal 13" in work["versions"][-1]["text"]

    first = work["versions"][-1]
    written = _filled(first["body"], work["facts"])
    work = await _save(client, vid, written, first["id"])
    assert work["open_passages"] == []
    draft = work["versions"][-1]
    # Nothing a person typed is lost and the keys come back as they went.
    assert draft["body"] == written
    settled = await _settle(client, vid, draft["id"])
    assert settled.status_code in (200, 201), settled.text
    work = await _work(client, vid)
    version = work["versions"][-1]
    assert work["state"] == "settled" and work["changed_facts"] == []
    assert "Salaris in schaal 13" in version["text"]
    assert "{" not in version["text"]
    # What leaves grip is the frozen text.
    detail = (await client.get(f"{BASE}/{vid}")).json()
    current = next(t for t in detail["texts"] if t["is_current"])
    assert "Salaris in schaal 13" in current["body"] and "{" not in current["body"]

    await client.patch(f"{BASE}/{vid}", json={"scale": 11})
    work = await _work(client, vid)
    version = work["versions"][-1]
    assert "Salaris in schaal 13" in version["text"]
    assert work["changed_facts"] == [
        {"key": "schaal", "label": "Schaal", "settled": "13", "current": "11"}
    ]
    # Writing on starts from the draft with its keys, so the text follows again.
    assert version["body"] == written
    reopened = await _save(
        client, vid, version["body"] + "\n\nTot ziens.", version["id"]
    )
    assert "Salaris in schaal 11" in reopened["versions"][-1]["text"]
    assert reopened["versions"][-1]["text"].endswith("Tot ziens.")


def test_hours_follow_the_working_week_in_whole_hours() -> None:
    from decimal import Decimal

    assert library._hours(Decimal("0.2")) == "7"
    assert library._hours(Decimal("0.8")) == "29"
    assert library._hours(Decimal("1")) == "36"


def test_rekey_only_replaces_what_grip_wrote_itself() -> None:
    text = (
        "- Salaris in schaal [vul aan: de schaal van de vacature]\n"
        "- [vul aan: het soort contract]\n"
        "- [vul aan: de asd van de vacature]\n"
        "Wij zijn [vul aan: beschrijf in twee zinnen wat het team maakt]."
    )
    once, places = library.rekey(text)
    assert places == 2
    assert once == (
        "- Salaris in schaal {schaal}\n"
        "- {contract}\n"
        "- [vul aan: de asd van de vacature]\n"
        "Wij zijn [vul aan: beschrijf in twee zinnen wat het team maakt]."
    )
    assert library.rekey(once) == (once, 0)


async def test_conversion_touches_drafts_only_and_can_be_repeated(
    shipped, client, act_as, manager, budget_line, db_session
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line, scale=12)
    vid = vacancy["id"]
    work = await _started(client, vid)
    # A text as it was stored before a draft kept its keys.
    row = await db_session.get(VacancyText, work["versions"][-1]["id"])
    row.body = (
        "Mijn eigen zin over het team.\n\n"
        "- Salaris in schaal [vul aan: de schaal van de vacature]\n"
        "- [vul aan: het soort contract]"
    )
    await db_session.flush()
    changed = await fix_open_places.fix(db_session)
    assert changed["places"] == 2 and changed["versions"] == 1
    assert changed["vacancies"] == 1
    await db_session.refresh(row)
    assert row.body.startswith("Mijn eigen zin over het team.")
    work = await _work(client, vid)
    assert "- Salaris in schaal 12\n" in work["versions"][-1]["text"]
    assert work["open_passages"] == ["Kies het type contract op de aanvraag"]
    again = await fix_open_places.fix(db_session)
    assert again["places"] == 0 and again["versions"] == 0


@pytest.fixture
def passage_model(monkeypatch) -> FakeChatClient:
    fake = FakeChatClient("Het team bouwt een dienst waarmee burgers zaken regelen.")
    monkeypatch.setattr(
        "grip.services.vacancies.text_flow.get_chat_client", lambda *a, **k: fake
    )
    return fake


async def test_a_proposal_for_one_open_place_uses_the_facts_and_stores_nothing(
    shipped, client, act_as, manager, budget_line, passage_model
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line, scale=12)
    vid = vacancy["id"]
    work = await _started(client, vid)
    body = work["versions"][-1]["body"]
    place = next(p for p in work["open_passages"] if "team of product" in p)
    response = await client.post(
        f"{BASE}/{vid}/text-work/passage", json={"body": body, "place": place}
    )
    assert response.status_code == 200, response.text
    assert response.json()["proposal"] == (
        "Het team bouwt een dienst waarmee burgers zaken regelen."
    )
    sent = passage_model.calls[0]["user"]
    assert "<<HIER>>" in sent and place not in sent
    assert "Schaal: schaal 12" in sent and "Rol: Software engineer" in sent
    # The model reads the text as it reads, not the keys.
    assert "{schaal}" not in sent and "Salaris in schaal 12" in sent
    assert len((await _work(client, vid))["versions"]) == 1

    gone = await client.post(
        f"{BASE}/{vid}/text-work/passage",
        json={"body": body, "place": "[vul aan: iets anders]"},
    )
    assert gone.status_code == 422


async def test_a_text_for_a_known_candidate_is_written_when_someone_wants_it(
    shipped, client, act_as, manager, colleague, budget_line, db_session
) -> None:
    act_as(manager)
    vacancy = await _create(
        client,
        budget_line,
        vacancy_type="gerede",
        scale=12,
        candidate_person_id=str(colleague.id),
    )
    vid = vacancy["id"]
    response = (await client.get(f"{BASE}/{vid}/text-work")).json()
    assert response["vacancy_text_skipped"] is True
    assert response["may_want_text"] is True
    assert [t["kind"] for t in response["texts"]] == ["motivation"]

    wanted = await client.post(f"{BASE}/{vid}/text-work/wanted")
    assert wanted.status_code == 201, wanted.text
    response = wanted.json()
    assert response["vacancy_text_skipped"] is False
    work = next(t for t in response["texts"] if t["kind"] == "vacancy_text")
    assert work["needed"] is True and work["action"]["key"] == "start"
    row = await db_session.get(Vacancy, vid)
    assert text_flow.is_due(row, "vacancy_text") is True
