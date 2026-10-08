"""The confirmation list: nothing counts until a person approves it."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from grip.importers.grist.confirmation import (
    CONFIRMED,
    KIND_LINE,
    KIND_PERSON,
    KIND_SCALE,
    PROPOSED,
    SKIPPED,
    ConfirmationError,
    ConfirmationItem,
    ConfirmationList,
    confirm_by_confidence,
    merge,
    read_confirmations,
)


def line_item(key: str = "budget_line:1", text: str = "Developer (schaal 10/11)"):
    return ConfirmationItem(
        key=key,
        kind=KIND_LINE,
        label=text,
        source={"omschrijving": text, "begroot_centen": 14_400_000},
        proposal={
            "kind": "personnel",
            "role": "Developer",
            "fte": "1",
            "rate_category": "B",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "amount_cents": None,
            "year": None,
        },
        confidence="middel",
    )


def test_round_trip_through_the_file(tmp_path: Path) -> None:
    confirmations = ConfirmationList(document="voorbeeld.grist", items=[line_item()])
    path = tmp_path / "lijst.json"
    confirmations.write(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["items"][0]["status"] == PROPOSED
    assert data["items"][0]["values"] == data["items"][0]["proposal"]
    assert "uitleg" in data

    again = read_confirmations(path)
    assert again.items[0].key == "budget_line:1"
    assert again.items[0].hash == confirmations.items[0].hash


def test_only_confirmed_items_give_a_decision() -> None:
    item = line_item()
    confirmations = ConfirmationList("d", [item])
    assert confirmations.line(item.key) is None
    item.status = CONFIRMED
    decision = confirmations.line(item.key)
    assert decision is not None
    assert decision.kind == "personnel"
    assert decision.fte == Decimal(1)
    assert decision.start_date == date(2026, 1, 1)
    item.status = SKIPPED
    assert confirmations.line(item.key) is None


def test_a_person_can_correct_the_values() -> None:
    item = line_item()
    item.status = CONFIRMED
    item.values.update({"fte": "0,6", "rate_category": "c"})
    decision = ConfirmationList("d", [item]).line(item.key)
    assert decision is not None
    assert decision.fte == Decimal("0.6")
    assert decision.rate_category == "C"


def test_a_confirmed_item_must_be_complete() -> None:
    item = line_item()
    item.status = CONFIRMED
    item.values["rate_category"] = None
    with pytest.raises(ConfirmationError, match="mist rate_category"):
        ConfirmationList("d", [item]).line(item.key)
    item.values.update({"rate_category": "B", "start_date": "volgend jaar"})
    with pytest.raises(ConfirmationError, match="geen datum"):
        ConfirmationList("d", [item]).line(item.key)
    item.values.update({"start_date": "2026-12-01", "end_date": "2026-01-01"})
    with pytest.raises(ConfirmationError, match="einddatum"):
        ConfirmationList("d", [item]).line(item.key)


def test_person_and_scale_decisions() -> None:
    person = ConfirmationItem(
        key="person:1",
        kind=KIND_PERSON,
        label="Vera Voorbeeld",
        source={"naam": "Vera Voorbeeld", "email": ""},
        proposal={"action": "laden", "email": ""},
        confidence="laag",
    )
    scale = ConfirmationItem(
        key="person_scale:1",
        kind=KIND_SCALE,
        label="Vera Voorbeeld",
        source={"schaal": 14, "notitie": ""},
        proposal={"billing_scale": 14, "valid_from": "2026-01-01"},
        confidence="hoog",
    )
    confirmations = ConfirmationList("d", [person, scale])
    assert confirmations.person("person:1") is None
    person.status = CONFIRMED
    person.values["email"] = "vera@voorbeeld.example"
    decision = confirmations.person("person:1")
    assert decision is not None and decision.load
    assert decision.email == "vera@voorbeeld.example"
    person.values["email"] = "geen adres"
    with pytest.raises(ConfirmationError, match="geen e-mailadres"):
        confirmations.person("person:1")
    person.status = SKIPPED
    skipped = confirmations.person("person:1")
    assert skipped is not None and not skipped.load

    scale.status = CONFIRMED
    scale_decision = confirmations.scale("person_scale:1")
    assert scale_decision is not None
    assert scale_decision.billing_scale == 14
    assert scale_decision.valid_from == date(2026, 1, 1)


def test_merge_keeps_a_decision_while_the_source_is_unchanged() -> None:
    earlier = ConfirmationList("d", [line_item()])
    earlier.items[0].status = CONFIRMED
    earlier.items[0].values["fte"] = "0.5"
    result = merge(ConfirmationList("d", [line_item()]), earlier)
    assert result.kept == 1
    assert result.merged.items[0].status == CONFIRMED
    assert result.merged.items[0].values["fte"] == "0.5"


def test_merge_resets_a_decision_when_the_source_changed() -> None:
    earlier = ConfirmationList("d", [line_item()])
    earlier.items[0].status = CONFIRMED
    earlier.items[0].values["fte"] = "0.5"
    fresh = ConfirmationList("d", [line_item(text="Developer (schaal 12/13)")])
    result = merge(fresh, earlier)
    item = result.merged.items[0]
    assert result.reset == ("budget_line:1",)
    assert item.status == PROPOSED
    assert item.previous_values is not None and item.previous_values["fte"] == "0.5"
    assert any("gewijzigd" in remark for remark in item.remarks)


def test_merge_reports_new_and_dropped_items() -> None:
    earlier = ConfirmationList("d", [line_item("budget_line:1")])
    fresh = ConfirmationList("d", [line_item("budget_line:2")])
    result = merge(fresh, earlier)
    assert result.new == ("budget_line:2",)
    assert result.dropped == ("budget_line:1",)


def test_bulk_confirm_is_limited_to_one_confidence() -> None:
    high = line_item("budget_line:1")
    high.confidence = "hoog"
    medium = line_item("budget_line:2")
    done = line_item("budget_line:3")
    done.confidence = "hoog"
    done.status = SKIPPED
    confirmations = ConfirmationList("d", [high, medium, done])
    assert confirm_by_confidence(confirmations, "hoog") == ["budget_line:1"]
    assert [i.status for i in confirmations.items] == [CONFIRMED, PROPOSED, SKIPPED]


def test_a_broken_file_gives_a_clear_message(tmp_path: Path) -> None:
    path = tmp_path / "lijst.json"
    path.write_text("{ niet af", encoding="utf-8")
    with pytest.raises(ConfirmationError, match="geen geldige JSON"):
        read_confirmations(path)
    path.write_text(json.dumps({"format": 99, "items": []}), encoding="utf-8")
    with pytest.raises(ConfirmationError, match="onbekend formaat"):
        read_confirmations(path)
    ConfirmationList("d", [line_item()]).write(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][0]["status"] = "akkoord"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfirmationError, match="status is 'akkoord'"):
        read_confirmations(path)
    data["items"][0]["status"] = PROPOSED
    data["items"].append(data["items"][0])
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfirmationError, match="twee keer"):
        read_confirmations(path)
