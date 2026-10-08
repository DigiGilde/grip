"""Filling a fillable PDF from a field mapping. Synthetic forms only."""

from __future__ import annotations

import io
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pypdf import PdfReader

from grip.services.vacancies import form as forms


def _fields(pdf: bytes) -> dict:
    return PdfReader(io.BytesIO(pdf)).get_fields() or {}


def _widget_states(pdf: bytes) -> dict[str, str]:
    states: dict[str, str] = {}
    for page in PdfReader(io.BytesIO(pdf)).pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            if widget.get("/FT") == "/Btn":
                states[str(widget["/T"])] = str(widget.get("/AS"))
    return states


VALUES = {
    "requester_name": "Fictieve Aanvrager",
    "request_date": date(2026, 10, 8),
    "declarable": True,
    "vacancy_type": "regulier",
    "contract_type": "temporary_project",
    "function_title": "Backend-ontwikkelaar",
    "scale": 11,
    "fte": Decimal("0.80"),
    "hr_adviser_name": "Fictieve Adviseur",
    "hr_decision": False,
}


def test_inspect_lists_fields_without_values(filled_form, test_mapping):
    fields = {f.name: f for f in forms.inspect_form(filled_form)}
    assert len(fields) == len(test_mapping["fields"])
    assert fields["aanvrager"].type == "text"
    assert fields["aanvrager"].has_value
    assert not fields["datum"].has_value
    assert fields["decl_ja"].type == "checkbox"
    assert set(fields["decl_ja"].states) == {"/Ja", "/Off"}
    assert fields["decl_ja"].has_value
    assert not fields["decl_nee"].has_value
    # No field object carries the value itself.
    assert not hasattr(fields["aanvrager"], "value")


def test_text_fields_and_checkboxes_are_filled(blank_form, test_mapping):
    mapping = forms.parse_mapping(test_mapping)
    filled = forms.fill_form(blank_form, mapping, VALUES)
    fields = _fields(filled)

    assert fields["aanvrager"]["/V"] == "Fictieve Aanvrager"
    assert fields["datum"]["/V"] == "8-10-2026"
    assert fields["functie"]["/V"] == "Backend-ontwikkelaar"
    assert fields["schaal"]["/V"] == "11"
    assert fields["fte"]["/V"] == "0,8"
    assert fields["hr_naam"]["/V"] == "Fictieve Adviseur"

    states = _widget_states(filled)
    assert states["decl_ja"] == "/Ja"
    assert states["decl_nee"] == "/Off"
    assert states["type_regulier"] == "/Ja"
    assert states["type_gerede"] == "/Off"
    assert states["contract_project"] == "/Ja"
    assert states["hr_wel"] == "/Off"
    assert states["hr_niet"] == "/Ja"
    assert fields["hr_niet"]["/V"] == "/Ja"


def test_fields_without_a_value_stay_empty(blank_form, test_mapping):
    mapping = forms.parse_mapping(test_mapping)
    filled = forms.fill_form(blank_form, mapping, VALUES)
    fields = _fields(filled)
    for name in ("aan", "fgr", "motivatie", "controller", "akkoord_naam"):
        assert not fields[name].get("/V")
    states = _widget_states(filled)
    # No decision recorded: neither box of the pair is ticked.
    assert states["control_wel"] == "/Off"
    assert states["akkoord_wel"] == "/Off"
    assert states["akkoord_niet"] == "/Off"


def test_the_result_is_still_fillable(blank_form, test_mapping):
    mapping = forms.parse_mapping(test_mapping)
    first = forms.fill_form(blank_form, mapping, VALUES)

    reader = PdfReader(io.BytesIO(first))
    acroform = reader.trailer["/Root"]["/AcroForm"]
    assert len(acroform["/Fields"]) == len(test_mapping["fields"])
    assert acroform["/NeedAppearances"]
    assert {f.name for f in forms.inspect_form(first)} == {
        f["name"] for f in test_mapping["fields"]
    }

    # Completing it afterwards works: an adviser adds what was left open.
    second = forms.fill_form(
        first, mapping, {"controller_name": "Fictieve Controller", "hr_decision": True}
    )
    fields = _fields(second)
    assert fields["controller"]["/V"] == "Fictieve Controller"
    assert fields["aanvrager"]["/V"] == "Fictieve Aanvrager"
    states = _widget_states(second)
    assert states["hr_wel"] == "/Ja"
    assert states["hr_niet"] == "/Off"


def test_a_filled_template_is_refused_and_can_be_cleared(filled_form, test_mapping):
    mapping = forms.parse_mapping(test_mapping)
    with pytest.raises(forms.FormTemplateError, match="al ingevuld") as raised:
        forms.check_template(filled_form, mapping)
    # The message names fields, never their contents.
    assert "Fictieve" not in str(raised.value)

    cleared = forms.clear_form(filled_form)
    assert not any(f.has_value for f in forms.inspect_form(cleared))
    assert b"Fictieve Aanvrager" not in cleared
    forms.check_template(cleared, mapping)


def test_template_must_match_the_mapping(form_builder, test_mapping):
    mapping = forms.parse_mapping(test_mapping)
    with pytest.raises(forms.FormTemplateError, match="staat niet in de pdf"):
        forms.check_template(form_builder(["aanvrager"], ["decl_ja"]), mapping)
    with pytest.raises(forms.FormTemplateError, match="geen invulbare velden"):
        forms.check_template(form_builder([], []), mapping)
    with pytest.raises(forms.FormTemplateError, match="geen leesbare pdf"):
        forms.check_template(b"dit is geen pdf", mapping)

    other_state = form_builder(
        [f["name"] for f in test_mapping["fields"] if f["type"] == "text"],
        [f["name"] for f in test_mapping["fields"] if f["type"] == "checkbox"],
        on_value="/On",
    )
    with pytest.raises(forms.FormTemplateError, match="aan-waarde"):
        forms.check_template(other_state, mapping)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"fields": []}, "geen velden"),
        ({"date_format": "mm/dd/yy"}, "datumnotatie"),
        (
            {"fields": [{"name": "a", "type": "text", "source": "salary_scale"}]},
            "onbekend gegeven",
        ),
        (
            {"fields": [{"name": "a", "type": "radio", "source": "scale"}]},
            "onbekend type",
        ),
        (
            {"fields": [{"name": "a", "type": "checkbox", "source": "declarable"}]},
            "mist de waarde",
        ),
        (
            {
                "fields": [
                    {"name": "a", "type": "text", "source": "scale"},
                    {"name": "a", "type": "text", "source": "fte"},
                ]
            },
            "twee keer",
        ),
    ],
)
def test_a_broken_mapping_is_refused(test_mapping, change, message):
    with pytest.raises(forms.FormMappingError, match=message):
        forms.parse_mapping(test_mapping | change)


def test_unknown_values_are_refused(blank_form, test_mapping):
    mapping = forms.parse_mapping(test_mapping)
    with pytest.raises(forms.FormMappingError, match="Onbekende gegevens"):
        forms.fill_form(blank_form, mapping, {"salary_scale": 12})


def test_value_formats():
    assert forms.format_value(date(2026, 1, 5)) == "5-1-2026"
    assert forms.format_value(date(2026, 1, 5), "dd-mm-yyyy") == "05-01-2026"
    assert forms.format_value(Decimal("1.00")) == "1"
    assert forms.format_value(Decimal("0.50")) == "0,5"
    assert forms.format_value(14) == "14"


def test_the_bundled_mapping_is_valid_and_fully_verified():
    data = forms.load_bundled_mapping("odi-vacature-aanvraagformulier")
    mapping = forms.parse_mapping(data)
    assert len(mapping.fields) == 27
    assert mapping.unverified == ()
    assert {rule.source for rule in mapping.fields} == forms.FORM_SOURCES
    # A mapping holds field names and labels, never a filled-in value.
    assert set(data) == {
        "form",
        "title",
        "mapping_version",
        "description",
        "date_format",
        "fields",
    }
    with pytest.raises(forms.FormMappingError):
        forms.load_bundled_mapping("../geheim")


@pytest.mark.skipif(
    not os.environ.get("GRIP_VACANCY_FORM_TEMPLATE"),
    reason="set GRIP_VACANCY_FORM_TEMPLATE to a blank copy of the real form",
)
def test_the_real_template_local_only():
    """Fills the real form when a blank copy is available on this machine.

    The form is not in the repository, so this never runs in CI.
    """
    template = Path(os.environ["GRIP_VACANCY_FORM_TEMPLATE"]).read_bytes()
    mapping = forms.parse_mapping(
        forms.load_bundled_mapping("odi-vacature-aanvraagformulier")
    )
    forms.check_template(template, mapping)
    filled = forms.fill_form(template, mapping, VALUES | {"approval_decision": True})
    fields = _fields(filled)
    assert fields["Text1"]["/V"] == "Fictieve Aanvrager"
    assert fields["Text6-1"]["/V"] == "11"
    assert fields["Selectievakje 16"]["/V"] == "/Ja"
    assert fields["Selectievakje 64"]["/V"] == "/Off"
    assert fields["Selectievakje 19"]["/V"] == "/Ja"
    assert fields["Selectievakje 56"]["/V"] == "/Ja"
    assert fields["Selectievakje 62"]["/V"] == "/Ja"
    assert {f.name for f in forms.inspect_form(filled)} == {
        rule.name for rule in mapping.fields
    }
