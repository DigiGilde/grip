"""Looking at a stored form: fields, a filled sample, and changing a mapping."""

from __future__ import annotations

import io
import json

from pypdf import PdfReader


async def _upload(client, content, mapping):
    response = await client.post(
        "/api/form-templates",
        data={"name": "Aanvraagformulier", "mapping": json.dumps(mapping)},
        files={"file": ("formulier.pdf", content, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fields(pdf: bytes) -> dict:
    return PdfReader(io.BytesIO(pdf)).get_fields() or {}


async def test_the_view_is_for_the_beheerder(
    client, act_as, beheerder, planner, manager, blank_form, test_mapping
) -> None:
    act_as(beheerder)
    template = await _upload(client, blank_form, test_mapping)
    base = f"/api/form-templates/{template['id']}"
    for person in (planner, manager):
        act_as(person)
        for path in ("", "/file", "/sample"):
            assert (await client.get(base + path)).status_code == 403
        refused = await client.put(f"{base}/fields/aanvrager", json={"source": None})
        assert refused.status_code == 403


async def test_fields_say_in_words_what_fills_them(
    client, act_as, beheerder, blank_form, test_mapping
) -> None:
    act_as(beheerder)
    template = await _upload(client, blank_form, test_mapping)
    base = f"/api/form-templates/{template['id']}"
    detail = (await client.get(base)).json()
    by_name = {field["name"]: field for field in detail["fields"]}
    assert by_name["aanvrager"]["fills"] == "Naam van de aanvrager"
    assert by_name["aanvrager"]["state"] == "mapped"
    assert by_name["decl_ja"]["fills"] == (
        "Of de vacature declarabel is: aangevinkt bij ja"
    )
    assert {source["key"] for source in detail["sources"]} >= {"scale", "vacancy_type"}

    # Take the mapping of one field away: the form still has it, nothing fills it.
    changed = await client.put(f"{base}/fields/functie", json={"source": None})
    assert changed.status_code == 200, changed.text
    by_name = {field["name"]: field for field in changed.json()["fields"]}
    assert by_name["functie"]["state"] == "unfilled"
    assert by_name["functie"]["fills"] is None


async def test_a_field_is_mapped_from_the_fixed_list(
    client, act_as, beheerder, blank_form, test_mapping
) -> None:
    act_as(beheerder)
    template = await _upload(client, blank_form, test_mapping)
    base = f"/api/form-templates/{template['id']}"

    wrong = await client.put(f"{base}/fields/functie", json={"source": "salaris"})
    assert wrong.status_code == 422
    box = await client.put(f"{base}/fields/decl_ja", json={"source": "scale"})
    assert box.status_code == 422 and "selectievakje" in box.json()["detail"]
    no_choice = await client.put(
        f"{base}/fields/decl_ja", json={"source": "declarable"}
    )
    assert no_choice.status_code == 422
    unknown = await client.put(f"{base}/fields/bestaat-niet", json={"source": "scale"})
    assert unknown.status_code == 422

    ok = await client.put(f"{base}/fields/functie", json={"source": "scale"})
    assert ok.status_code == 200, ok.text
    by_name = {field["name"]: field for field in ok.json()["fields"]}
    assert by_name["functie"]["fills"] == "Schaal"

    sample = await client.get(f"{base}/sample")
    assert sample.status_code == 200
    assert _fields(sample.content)["functie"]["/V"] == "11"


async def test_the_blank_file_and_the_sample(
    client, act_as, beheerder, blank_form, test_mapping
) -> None:
    act_as(beheerder)
    template = await _upload(client, blank_form, test_mapping)
    base = f"/api/form-templates/{template['id']}"

    blank = await client.get(f"{base}/file")
    assert blank.status_code == 200
    assert blank.headers["content-type"] == "application/pdf"
    assert blank.headers["content-disposition"].startswith("inline;")
    assert not any(
        field.get("/V")
        for field in _fields(blank.content).values()
        if field.get("/FT") == "/Tx"
    )

    sample = await client.get(f"{base}/sample")
    assert sample.status_code == 200
    filled = _fields(sample.content)
    # Without a vacancy every mapped text field holds an example value.
    for rule in test_mapping["fields"]:
        if rule["type"] == "text":
            assert filled[rule["name"]].get("/V"), rule["name"]
    assert filled["aanvrager"]["/V"] == "Vera Voorbeeld"
    # The stored blank is not touched by making a sample.
    again = await client.get(f"{base}/file")
    assert again.content == blank.content
