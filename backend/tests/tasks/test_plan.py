"""The plan is data, and can only name what the catalogue offers."""

from __future__ import annotations

import copy
import json

import pytest

from grip.tasks import catalogue
from grip.tasks.plan import DEFAULT_PLAN_FILE, PlanError, current_plan, parse_plan

RAW = json.loads(DEFAULT_PLAN_FILE.read_text(encoding="utf-8"))


def _first(raw: dict) -> dict:
    return raw["case_kinds"]["assignment"]["templates"][0]


def test_the_shipped_plan_is_valid_and_small():
    plan = current_plan()
    keys = [t.key for templates in plan.templates.values() for t in templates]
    assert len(keys) == len(set(keys))
    assert 12 <= len(keys) <= 26
    assert plan.version


def test_every_template_names_only_the_catalogue():
    plan = current_plan()
    for case_kind, templates in plan.templates.items():
        for template in templates:
            known = catalogue.facts_for(case_kind, template.subject)
            for condition in template.when:
                assert condition.removeprefix("not ") in known
            assert template.assignee in catalogue.ASSIGNEES[case_kind]


def test_a_fact_that_closes_a_task_has_words_for_the_screen():
    for templates in current_plan().templates.values():
        for template in templates:
            if template.done_when:
                assert template.done_when in catalogue.FACT_LABELS, template.key


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("for", "invented_subject", "onbekend onderwerp"),
        ("when", ["invented_fact"], "onbekend feit"),
        ("done_when", "invented_fact", "onbekend feit"),
        ("assignee", "koning", "onbekende rol"),
        ("track", "nergens", "onbekend spoor"),
        ("due", {"working_days": 3, "after": "ooit"}, "onbekend moment"),
        ("set_fact", "quote_accepted", "onbekende instelling"),
    ],
)
def test_a_plan_cannot_reach_past_the_catalogue(field, value, message):
    raw = copy.deepcopy(RAW)
    _first(raw)[field] = value
    with pytest.raises(PlanError, match=message):
        parse_plan(raw)


def test_a_template_waits_for_its_event_type():
    raw = copy.deepcopy(RAW)
    _first(raw)["requires_event"] = "nog_niet.bestaand"
    plan = parse_plan(raw)
    assert plan.template(_first(raw)["key"]) is None
    assert plan.template("financien.naverrekening_aanleveren") is not None


def test_a_key_cannot_be_used_twice():
    raw = copy.deepcopy(RAW)
    templates = raw["case_kinds"]["assignment"]["templates"]
    templates.append(copy.deepcopy(templates[0]))
    with pytest.raises(PlanError, match="twee keer"):
        parse_plan(raw)
