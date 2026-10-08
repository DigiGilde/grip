"""The request form of a vacancy as a kept document. All names are fictional."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

from pypdf import PdfReader

from grip.models.vacancy import Vacancy, VacancyStatus
from grip.services import instance_settings
from grip.services.vacancies import request_forms
from tests.api.vacancies.test_vacancies_api import (
    BASE,
    _create,
    _decide,
    _motivate,
)


async def _template(client, act_as, beheerder, blank_form, test_mapping) -> None:
    act_as(beheerder)
    response = await client.post(
        "/api/form-templates",
        data={"name": "Aanvraagformulier", "mapping": json.dumps(test_mapping)},
        files={"file": ("formulier.pdf", blank_form, "application/pdf")},
    )
    assert response.status_code == 201, response.text


async def _vacancy(client, act_as, manager, budget_line) -> str:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _motivate(client, vacancy["id"])
    await client.post(
        f"{BASE}/{vacancy['id']}/submit", json={"requested_on": "2026-09-28"}
    )
    return vacancy["id"]


async def test_the_form_is_made_once_and_the_kept_bytes_are_served(
    client, act_as, manager, beheerder, budget_line, blank_form, test_mapping
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    vid = await _vacancy(client, act_as, manager, budget_line)
    url = f"{BASE}/{vid}/request-forms"

    before = (await client.get(url)).json()
    assert before["available"] is True and before["may_make"] is True
    assert before["current"] is None and before["earlier"] == []

    made = await client.post(url)
    assert made.status_code == 201, made.text
    current = made.json()["current"]
    assert current["made_by_name"] == "Fictieve Eigenaar"
    assert made.json()["changed"] == []

    first = await client.get(f"{url}/{current['id']}")
    again = await client.get(f"{url}/{current['id']}?download=true")
    assert first.status_code == 200 and first.content == again.content
    assert first.headers["x-document-sha256"] == current["sha256"]
    assert first.headers["content-disposition"].startswith("inline;")
    assert again.headers["content-disposition"].startswith("attachment;")
    fields = PdfReader(io.BytesIO(first.content)).get_fields()
    assert fields["aanvrager"]["/V"] == "Fictieve Eigenaar"
    # Still a form: an adviser outside grip can complete it.
    assert fields["hr_naam"]["/FT"] == "/Tx"

    # Nothing changed, so there is nothing to make a new version of.
    refused = await client.post(url)
    assert refused.status_code == 422
    assert "klopt nog" in refused.json()["detail"]


async def test_a_change_makes_the_form_out_of_date_and_says_what_changed(
    client, act_as, manager, beheerder, adviser, budget_line, blank_form, test_mapping
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    vid = await _vacancy(client, act_as, manager, budget_line)
    url = f"{BASE}/{vid}/request-forms"
    first = (await client.post(url)).json()["current"]

    # The advice is recorded by someone who may; the requester then looks again.
    act_as(beheerder)
    decided = await _decide(
        client,
        vid,
        "hr_advice",
        person_name="Fictieve Adviseur",
        person_email="adviseur@example.org",
        agreed=True,
    )
    assert decided.status_code == 200, decided.text
    act_as(manager)
    standing = (await client.get(url)).json()
    assert standing["current"]["id"] == first["id"]
    assert "Naam van de HR-adviseur" in standing["changed"]
    assert "Advies van HR" in standing["changed"]
    assert "Naam van de aanvrager" not in standing["changed"]

    remade = await client.post(url)
    assert remade.status_code == 201, remade.text
    out = remade.json()
    assert out["current"]["id"] != first["id"] and out["changed"] == []
    assert [version["id"] for version in out["earlier"]] == [first["id"]]
    # The earlier version is still the file it was.
    old = await client.get(f"{url}/{first['id']}")
    assert old.headers["x-document-sha256"] == first["sha256"]
    assert not PdfReader(io.BytesIO(old.content)).get_fields()["hr_naam"].get("/V")


async def test_a_signed_copy_is_kept_as_its_own_document(
    client, act_as, manager, beheerder, budget_line, blank_form, test_mapping
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    vid = await _vacancy(client, act_as, manager, budget_line)
    url = f"{BASE}/{vid}/request-forms"
    await client.post(url)

    wrong = await client.post(
        f"{url}/signed", files={"file": ("scan.txt", b"geen pdf", "text/plain")}
    )
    assert wrong.status_code == 422
    signed = await client.post(
        f"{url}/signed",
        files={"file": ("getekend.pdf", blank_form, "application/pdf")},
    )
    assert signed.status_code == 201, signed.text
    out = signed.json()
    assert [doc["file_name"] for doc in out["signed"]] == ["getekend.pdf"]
    assert out["current"] is not None
    served = await client.get(f"{url}/{out['signed'][0]['id']}")
    assert served.content == blank_form


async def test_who_may_read_make_and_record(
    client,
    act_as,
    manager,
    beheerder,
    planner,
    lezer,
    colleague,
    budget_line,
    other_budget_line,
    blank_form,
    test_mapping,
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    vid = await _vacancy(client, act_as, manager, budget_line)
    url = f"{BASE}/{vid}/request-forms"
    document = (await client.post(url)).json()["current"]

    # The form holds names: a reader without the staffing class gets nothing.
    for person in (lezer, colleague):
        act_as(person)
        assert (await client.get(url)).status_code in (403, 404)
        assert (await client.get(f"{url}/{document['id']}")).status_code in (403, 404)
        assert (await client.post(url)).status_code in (403, 404)

    # A document of this vacancy cannot be reached through another vacancy.
    act_as(beheerder)
    other = await _create(client, other_budget_line)
    crossed = await client.get(f"{BASE}/{other['id']}/request-forms/{document['id']}")
    assert crossed.status_code == 404


async def test_the_forms_go_when_the_vacancy_has_closed(
    client,
    act_as,
    manager,
    beheerder,
    budget_line,
    blank_form,
    test_mapping,
    db_session,
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    vid = await _vacancy(client, act_as, manager, budget_line)
    url = f"{BASE}/{vid}/request-forms"
    await client.post(url)
    await client.post(
        f"{url}/signed",
        files={"file": ("getekend.pdf", blank_form, "application/pdf")},
    )

    # A vacancy that still runs keeps its forms.
    assert await request_forms.remove_expired(db_session) == 0

    vacancy = await db_session.get(Vacancy, vid)
    vacancy.status = VacancyStatus.withdrawn.value
    await db_session.flush()
    await instance_settings.set_values(
        db_session, {request_forms.RETENTION_DAYS.key: 30}, actor=beheerder
    )
    now = datetime.now(UTC)
    assert await request_forms.remove_expired(db_session, now=now) == 0
    removed = await request_forms.remove_expired(
        db_session, now=now + timedelta(days=31)
    )
    assert removed == 2
    out = (await client.get(url)).json()
    assert out["current"] is None and out["signed"] == []


async def test_no_form_and_no_request_while_the_motivation_is_not_settled(
    client, act_as, manager, beheerder, budget_line, blank_form, test_mapping
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    act_as(manager)
    vacancy = await _create(client, budget_line)
    assert vacancy["request_missing"] == ["een vastgestelde aanleiding en motivatie"]
    url = f"{BASE}/{vacancy['id']}/request-forms"

    standing = (await client.get(url)).json()
    assert standing["missing"] == ["een vastgestelde aanleiding en motivatie"]
    refused = await client.post(url)
    assert refused.status_code == 422
    assert (
        "Ontbreekt nog: een vastgestelde aanleiding en motivatie"
        in (refused.json()["detail"])
    )
    refused = await client.post(f"{BASE}/{vacancy['id']}/submit", json={})
    assert refused.status_code == 422
    assert "kan nog niet worden aangevraagd" in refused.json()["detail"]

    await _motivate(client, vacancy["id"])
    assert (await client.get(url)).json()["missing"] == []
    assert (await client.post(url)).status_code == 201
