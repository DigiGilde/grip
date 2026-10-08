"""What goes to the language model is fixed by construction."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from grip.models.vacancy import ContractType, TextKind
from grip.services.vacancies.drafting import (
    ALLOWED_INPUT_FIELDS,
    PROMPT_VERSION,
    DraftInput,
    DraftInputError,
    build_prompt,
    ensure_no_person_names,
    find_person_names,
)


def _input(**overrides) -> DraftInput:
    values = {
        "role": "Backend-ontwikkelaar",
        "scale_band": "schaal 11",
        "fte": Decimal("0.80"),
        "period_start": date(2027, 1, 1),
        "period_end": date(2027, 12, 31),
        "contract_type": ContractType.temporary_project,
        "assignment_name": "Opdracht Alfa",
        "assignment_summary": "Een register bouwen voor fictieve vergunningen.",
        "organisation_description": "Een team dat digitale producten maakt.",
    }
    return DraftInput(**(values | overrides))


def test_the_whitelist_is_exactly_these_fields():
    assert ALLOWED_INPUT_FIELDS == {
        "role",
        "scale_band",
        "fte",
        "period_start",
        "period_end",
        "contract_type",
        "assignment_name",
        "assignment_summary",
        "organisation_description",
        "examples",
    }


@pytest.mark.parametrize(
    "field",
    [
        "person_name",
        "candidate_name",
        "billing_scale",
        "rate_category",
        "monthly_rate",
        "cost_rate",
        "margin",
        "billability_target",
        "requester_name",
    ],
)
def test_nothing_outside_the_whitelist_can_be_passed(field):
    with pytest.raises(TypeError):
        _input(**{field: "x"})


def test_the_input_cannot_be_changed_afterwards():
    draft_input = _input()
    with pytest.raises(AttributeError):
        draft_input.role = "iets anders"


def test_the_prompt_holds_the_whitelisted_values_and_nothing_else():
    system, user = build_prompt(TextKind.vacancy_text, _input())
    for expected in (
        "Backend-ontwikkelaar",
        "schaal 11",
        "0,8",
        "van 2027-01-01 tot en met 2027-12-31",
        "tijdelijk (projectcontract)",
        "Opdracht Alfa",
        "fictieve vergunningen",
        "digitale producten",
    ):
        assert expected in user
    # Every line under "Gegevens:" is one of the known labels.
    facts = user.split("Gegevens:\n", 1)[1].splitlines()
    labels = {line.split(":", 1)[0] for line in facts if line.startswith("- ")}
    assert labels == {
        "- Rol",
        "- Schaal",
        "- Omvang (fte)",
        "- Periode",
        "- Soort contract",
        "- Opdracht",
        "- Over de opdracht",
        "- Over de organisatie",
    }
    assert "geen namen van personen" in system


def test_missing_values_are_left_out_of_the_prompt():
    _system, user = build_prompt(TextKind.motivation, DraftInput(role="Tester"))
    assert "- Rol: Tester" in user
    for label in ("Schaal", "Omvang", "Periode", "Soort contract", "Opdracht"):
        assert f"- {label}" not in user
    assert "Aanleiding en motivatie" in user


def test_examples_only_in_the_vacancy_text_prompt():
    draft_input = _input(examples=("Een eerdere vacaturetekst.",))
    _s, vacancy_prompt = build_prompt(TextKind.vacancy_text, draft_input)
    _s, motivation_prompt = build_prompt(TextKind.motivation, draft_input)
    assert "Een eerdere vacaturetekst." in vacancy_prompt
    assert "Een eerdere vacaturetekst." not in motivation_prompt


def test_at_most_three_examples_and_a_role_is_required():
    with pytest.raises(DraftInputError):
        _input(examples=("a", "b", "c", "d"))
    with pytest.raises(DraftInputError):
        DraftInput(role="  ")


def test_a_known_person_name_in_free_text_is_refused():
    names = ["Fictieve Collega", "Jan"]
    clean = _input()
    assert find_person_names(clean, names) == []
    ensure_no_person_names(clean, names)

    tainted = _input(assignment_summary="Vervanging van fictieve  COLLEGA in het team.")
    assert find_person_names(tainted, ["Fictieve Collega"]) == ["Fictieve Collega"]
    with pytest.raises(DraftInputError, match="naam van een persoon") as raised:
        ensure_no_person_names(tainted, names)
    # The error does not repeat the name.
    assert "Collega" not in str(raised.value)

    in_example = _input(examples=("Neem contact op met Fictieve Collega.",))
    with pytest.raises(DraftInputError):
        ensure_no_person_names(in_example, names)


def test_short_names_do_not_match_ordinary_words():
    # "Jan" occurs in "januari"; a three-letter name is not a usable signal.
    draft_input = _input(assignment_summary="Start in januari.")
    assert find_person_names(draft_input, ["Jan"]) == []


def test_prompt_version_is_set():
    assert PROMPT_VERSION
