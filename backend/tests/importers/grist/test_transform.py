"""From a document to an import plan."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from grip.importers.grist.confirmation import CONFIRMED, KIND_LINE
from grip.importers.grist.document import GristDocument
from grip.importers.grist.mapping import Mapping, check_mapping
from grip.importers.grist.transform import (
    ERROR,
    WARNING,
    build_plan,
    to_cents,
    to_date,
    to_decimal,
)
from tests.importers.grist.builder import build_grist
from tests.importers.grist.conftest import fictional_tables
from tests.importers.grist.helpers import EMAIL_DOMAIN, confirm_all, confirmed_plan


def test_without_confirmations_nothing_is_interpreted(
    document: GristDocument, mapping: Mapping
) -> None:
    plan = build_plan(document, mapping, check_mapping(document, mapping))
    # Every person, scale and budget line is waiting for a person.
    assert len(plan.unconfirmed) == 4 + 3 + 5
    assert plan.scales == []
    # The text stays text: every line is a fixed amount for now.
    assert {line.kind for line in plan.lines} == {"fixed"}
    assert not any(line.confirmed for line in plan.lines)
    assert plan.allocations == []
    assert [line.amount_cents for line in plan.lines][:2] == [17_280_000, 13_500_000]
    assert not plan.errors


def test_the_proposals_cover_every_free_text(
    document: GristDocument, mapping: Mapping
) -> None:
    plan = build_plan(document, mapping, check_mapping(document, mapping))
    items = plan.confirmations.by_key()
    assert items["person:4"].proposal["action"] == "overslaan"
    assert items["person_scale:2"].proposal["billing_scale"] == 12
    assert items["person_scale:2"].source["notitie"] == "Schaal 11, maar rekent met 12"
    quarter = items["budget_line:2"]
    assert quarter.proposal["start_date"] == "2026-04-01"
    assert quarter.proposal["rate_category"] == "C"
    assert items["budget_line:3"].proposal == {
        "kind": "fixed",
        "role": None,
        "fte": None,
        "rate_category": None,
        "start_date": None,
        "end_date": None,
        "amount_cents": 6_000_000,
        "year": 2026,
    }
    # The year comes from the name of the assignment.
    assert items["budget_line:5"].proposal["year"] == 2026


def test_confirmed_plan(document: GristDocument, mapping: Mapping) -> None:
    plan = confirmed_plan(document, mapping)
    assert plan.unconfirmed == []
    assert not plan.errors

    assert plan.rate_bands == {
        "A": 900_000,
        "B": 1_200_000,
        "C": 1_500_000,
        "D": 1_800_000,
        "E": 2_100_000,
    }
    assert plan.scale_bands[14] == "D"

    assert [p.name for p in plan.persons] == ["Vera Voorbeeld", "Tom Test", "Dana Demo"]
    assert all(p.email.endswith(EMAIL_DOMAIN) for p in plan.persons)
    assert plan.skipped_persons == {4}
    assert {s.person_row: s.billing_scale for s in plan.scales} == {1: 14, 2: 12, 3: 10}
    assert [(t.person_row, t.target_pct) for t in plan.targets] == [
        (1, Decimal("90.0"))
    ]

    alfa, beta, internal = plan.assignments
    assert (alfa.name, alfa.year, alfa.status, alfa.kind) == (
        "Opdracht Alfa 2026",
        2026,
        "in_progress",
        "external",
    )
    assert alfa.quoted_amount_cents == 40_000_000
    assert (alfa.start_date, alfa.end_date) == (date(2026, 1, 1), date(2026, 12, 31))
    assert alfa.notes is not None and "2025-11-03" in alfa.notes
    assert beta.status == "quoted"
    assert (internal.kind, internal.status) == ("internal", "in_progress")

    kinds = {line.row_id: line.kind for line in plan.lines}
    assert kinds == {
        1: "personnel",
        2: "personnel",
        3: "fixed",
        4: "personnel",
        5: "fixed",
    }
    second = next(line for line in plan.lines if line.row_id == 2)
    assert (second.fte, second.rate_category, second.start_date) == (
        Decimal(1),
        "C",
        date(2026, 4, 1),
    )

    assert len(plan.allocations) == 4
    across = next(a for a in plan.allocations if a.row_id == 3)
    assert (across.start_date, across.end_date, across.fte_pct) == (
        date(2026, 7, 1),
        date(2027, 6, 30),
        Decimal("50.0"),
    )
    assert [c.pct for c in plan.coverages] == [Decimal("30.0"), Decimal("50.0")]
    assert {c.line_row for c in plan.coverages} == {4, 5}
    assert [(i.kind, i.amount_cents) for i in plan.invoice_lines] == [
        ("actual", 900_000),
        ("estimate", 600_000),
    ]


def test_grist_figures_are_kept_for_the_reconciliation(
    document: GristDocument, mapping: Mapping
) -> None:
    figures = confirmed_plan(document, mapping).figures
    assert figures.assignments[1] == {
        "budgeted": 37_780_000,
        "used": 31_230_000,
        "available": 6_550_000,
    }
    assert figures.allocations == {
        1: 17_280_000,
        2: 13_500_000,
        3: 7_200_000,
        4: 1_200_000,
    }
    assert figures.cost_items[1] == {"forecast": 1_500_000, "covered": 1_200_000}
    assert figures.kpi[1] == {"target": 19_440_000, "realisation": 17_280_000}
    # A cell with a formula error gives no figure, and no zero either.
    assert figures.lines[3] == {"budgeted": 6_000_000}


def test_fractions_are_recognised_and_said(
    document: GristDocument, mapping: Mapping
) -> None:
    plan = confirmed_plan(document, mapping)
    notes = [i.message for i in plan.issues if "fractie" in i.message]
    assert len(notes) == 4


def test_fte_is_derived_from_the_budgeted_amount(
    tmp_path: Path, mapping: Mapping
) -> None:
    tables = fictional_tables()
    for table in tables:
        if table.table_id == "Begroting":
            # Nine months in category C at half time.
            table.rows[1]["Begroot"] = 67_500
            # The text says 0,8 FTE; the amount says something else.
            table.rows[0]["Begroot"] = 200_000
    with GristDocument(build_grist(tmp_path / "fte.grist", tables)) as doc:
        plan = build_plan(doc, mapping, check_mapping(doc, mapping))
    items = plan.confirmations.by_key()
    derived = items["budget_line:2"]
    assert derived.proposal["fte"] == "0.500"
    assert any("afgeleid" in remark for remark in derived.remarks)
    differs = items["budget_line:1"]
    assert differs.confidence == "laag"
    assert any("wijkt af" in remark for remark in differs.remarks)


def test_problems_in_the_data_become_issues_not_crashes(
    tmp_path: Path, mapping: Mapping
) -> None:
    tables = fictional_tables()
    for table in tables:
        if table.table_id == "Inzet":
            table.rows.append({"Naam": 1, "Begrotingsregel": 99, "FTE": 0.5})
            table.rows.append(
                {
                    "Naam": 4,
                    "Begrotingsregel": 1,
                    "Startdatum": date(2026, 1, 1),
                    "Einddatum": date(2026, 6, 30),
                    "FTE": 1,
                    "Inzetbedrag": 108_000,
                }
            )
        if table.table_id == "Opdracht":
            table.rows[1]["Status"] = "Wacht op antwoord"
        if table.table_id == "Tarievenleaflet":
            table.rows.append({"Categorie": "B", "Inzetschaal": 18, "Maandtarief": 99})
    with GristDocument(build_grist(tmp_path / "rommel.grist", tables)) as doc:
        check = check_mapping(doc, mapping)
        proposals = build_plan(doc, mapping, check).confirmations
        plan = build_plan(doc, mapping, check, confirmations=confirm_all(proposals))

    errors = [i.message for i in plan.issues if i.severity == ERROR]
    warnings = [i.message for i in plan.issues if i.severity == WARNING]
    assert any("twee verschillende maandtarieven" in m for m in errors)
    assert any("Inzet niet geladen" in m for m in errors)
    assert any("rij 99" in m for m in warnings)
    assert any("overgeslagen persoon" in m for m in warnings)
    assert any("Wacht op antwoord" in m for m in warnings)
    assert len(plan.allocations) == 4


def test_a_line_confirmed_as_fixed_takes_no_allocations(
    document: GristDocument, mapping: Mapping
) -> None:
    check = check_mapping(document, mapping)
    confirmations = confirm_all(build_plan(document, mapping, check).confirmations)
    item = confirmations.get(f"{KIND_LINE}:4")
    assert item is not None and item.status == CONFIRMED
    item.values = {"kind": "fixed", "amount_cents": 14_400_000, "year": 2026}
    plan = build_plan(document, mapping, check, confirmations=confirmations)
    assert {a.row_id for a in plan.allocations} == {1, 2}
    assert sum("niet als personeelsregel" in i.message for i in plan.issues) == 2


def test_value_helpers() -> None:
    assert to_cents(172800) == 17_280_000
    assert to_cents(0.1 + 0.2) == 30
    assert to_cents("€ 1.250,50") == 125_050
    assert to_cents("") is None
    assert to_cents(True) is None
    assert to_decimal("80%") == Decimal(80)
    assert to_date("2026-03-01") == date(2026, 3, 1)
    assert to_date("1-3-2026") == date(2026, 3, 1)
    assert to_date("morgen") is None
