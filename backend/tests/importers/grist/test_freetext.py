"""Free text to proposed fields."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from grip.importers.grist.freetext import (
    FIXED,
    HIGH,
    LOW,
    MEDIUM,
    PERSONNEL,
    assignment_year,
    parse_amount_cents,
    parse_budget_line,
    parse_scale_note,
)

CATEGORIES = {10: "B", 11: "B", 12: "C", 13: "C", 14: "D", 15: "D", 16: "E"}


def line(text: str, budgeted: int | None = None, **kwargs):
    return parse_budget_line(
        text,
        year=2026,
        budgeted_cents=budgeted,
        scale_to_category=CATEGORIES,
        **kwargs,
    )


def test_note_with_two_scales_proposes_the_billing_scale() -> None:
    proposal = parse_scale_note("Schaal 11, maar rekent met 12", 11, 2026)
    assert proposal.billing_scale == 12
    assert proposal.confidence == HIGH
    assert proposal.valid_from == date(2026, 1, 1)
    assert any("11" in remark for remark in proposal.remarks)


def test_scale_from_the_column_when_the_note_is_empty() -> None:
    proposal = parse_scale_note("", 14, 2026)
    assert (proposal.billing_scale, proposal.confidence) == (14, HIGH)
    assert parse_scale_note(None, 14, 2026).billing_scale == 14


@pytest.mark.parametrize(
    ("note", "column", "scale", "confidence"),
    [
        ("Schaal 12, niet zeker", 12, 12, LOW),
        ("Schaal 12/13", None, 12, LOW),
        ("Schaal 11 en later schaal 12", 11, 11, LOW),
        ("Schaal 13", 12, 13, MEDIUM),
        ("Werkt via een leverancier", 12, 12, MEDIUM),
        ("Rekenen met schaal 14", 13, 14, HIGH),
    ],
)
def test_scale_note_cases(note, column, scale, confidence) -> None:
    proposal = parse_scale_note(note, column, 2026)
    assert (proposal.billing_scale, proposal.confidence) == (scale, confidence)


def test_note_without_any_scale_stays_text() -> None:
    proposal = parse_scale_note("Start na de zomer", None, 2026)
    assert not proposal.parsed
    assert proposal.billing_scale is None
    assert proposal.source == "Start na de zomer"


def test_start_month_in_a_note() -> None:
    proposal = parse_scale_note("Schaal 12, start 15 maart", 12, 2026)
    assert proposal.valid_from == date(2026, 3, 15)


def test_role_with_fte_and_band() -> None:
    proposal = line("Productmanager (0,8 FTE, schaal 14/15)")
    assert proposal.kind == PERSONNEL
    assert proposal.role == "Productmanager"
    assert proposal.fte == Decimal("0.8")
    assert (proposal.scale_low, proposal.scale_high) == (14, 15)
    assert proposal.rate_category == "D"
    assert (proposal.start_date, proposal.end_date) == (
        date(2026, 1, 1),
        date(2026, 12, 31),
    )
    assert proposal.confidence == HIGH
    assert proposal.complete


def test_description_with_a_start_quarter() -> None:
    proposal = line("Developer #2 (vanaf Q2, schaal 10/11)")
    assert proposal.role == "Developer #2"
    assert proposal.start_date == date(2026, 4, 1)
    assert proposal.rate_category == "B"
    # No FTE in the text: one is assumed and the confidence says so.
    assert proposal.fte == Decimal(1)
    assert proposal.confidence == MEDIUM


def test_start_and_end_months() -> None:
    proposal = line("Tester (0,5 fte, schaal 12, vanaf 1 maart t/m september)")
    assert proposal.start_date == date(2026, 3, 1)
    assert proposal.end_date == date(2026, 9, 30)


def test_fixed_lines() -> None:
    amount = line("60k externe expertise", 6_000_000)
    assert (amount.kind, amount.amount_cents, amount.year) == (FIXED, 6_000_000, 2026)
    assert amount.confidence == HIGH
    stelpost = line("Beveiliging en pentesten (stelpost)", 2_500_000)
    assert (stelpost.kind, stelpost.amount_cents) == (FIXED, 2_500_000)
    plain = line("Reiskosten", 300_000)
    assert (plain.kind, plain.confidence) == (FIXED, MEDIUM)
    different = line("60k externe expertise", 5_000_000)
    assert different.amount_cents == 5_000_000
    assert any("wijkt af" in remark for remark in different.remarks)


def test_what_cannot_be_read_is_incomplete_and_low() -> None:
    no_amount = line("Nog te bepalen")
    assert not no_amount.complete
    assert no_amount.confidence == LOW
    unknown_scale = line("Architect (schaal 18)")
    assert unknown_scale.rate_category is None
    assert unknown_scale.confidence == LOW
    assert not unknown_scale.complete


def test_band_across_two_categories_is_flagged() -> None:
    proposal = line("Adviseur (1 fte, schaal 13/14)")
    assert proposal.rate_category == "C"
    assert proposal.confidence == MEDIUM
    assert any("verschillende" in remark for remark in proposal.remarks)


def test_structured_columns_win_over_the_text() -> None:
    proposal = line(
        "Developer (schaal 10/11)",
        column_fte=Decimal("0.6"),
        column_scale=12,
        column_start=date(2026, 5, 1),
        column_is_person=True,
    )
    assert proposal.fte == Decimal("0.6")
    assert proposal.rate_category == "C"
    assert proposal.start_date == date(2026, 5, 1)
    forced_fixed = line("Developer (schaal 10/11)", 100_000, column_is_person=False)
    assert forced_fixed.kind == FIXED


def test_amounts_and_years() -> None:
    assert parse_amount_cents("60k externe expertise") == 6_000_000
    assert parse_amount_cents("Licenties € 5.000") == 500_000
    assert parse_amount_cents("Licenties € 1.250,50") == 125_050
    assert parse_amount_cents("Developer #2") is None
    assert assignment_year("Opdracht Alfa 2026") == ("Opdracht Alfa", 2026)
    assert assignment_year("Opdracht zonder jaar") == ("Opdracht zonder jaar", None)
