"""Recognising the formulas that decide the open questions."""

from __future__ import annotations

from pathlib import Path

from grip.calc import CoverageBasis, PartialMonths
from grip.importers.grist.document import GristDocument
from grip.importers.grist.formulas import (
    ENTERED,
    MATCH,
    UNRECOGNISED,
    check_formulas,
    classify_coverage_basis,
    classify_forecast,
    classify_partial_months,
    suggested_coverage_basis,
    suggested_partial_months,
)
from grip.importers.grist.mapping import Mapping
from tests.importers.grist.builder import build_grist
from tests.importers.grist.conftest import fictional_tables


def test_partial_month_shapes() -> None:
    assert (
        classify_partial_months(
            '(DATEDIF($Startdatum, $Einddatum, "M") + 1) * $Maandbedrag'
        )[0]
        is PartialMonths.GRIST_DATEDIF
    )
    assert (
        classify_partial_months('$Maandbedrag*(DATEDIF($Start,$Eind,"M")+1)')[0]
        is PartialMonths.GRIST_DATEDIF
    )
    assert (
        classify_partial_months(
            "(($Eind.year - $Start.year) * 12 + $Eind.month - $Start.month + 1)"
            " * $Maandbedrag"
        )[0]
        is PartialMonths.WHOLE_MONTHS
    )
    assert (
        classify_partial_months("($Eind - $Start).days / 30.0 * $Maandbedrag")[0]
        is PartialMonths.CALENDAR_DAYS
    )
    assert (
        classify_partial_months('DATEDIF($Start, $Eind, "D") / 30 * $Maandbedrag')[0]
        is PartialMonths.CALENDAR_DAYS
    )
    # One month short of the expected shape is not waved through.
    assert classify_partial_months('DATEDIF($Start, $Eind, "M") * $Bedrag')[0] is None
    # A plus one elsewhere in the number does not count.
    assert classify_partial_months('DATEDIF($S, $E, "M") * $B + 10')[0] is None
    assert classify_partial_months("$Bedrag * 12")[0] is None
    assert classify_partial_months("")[0] is None


def test_forecast_shapes() -> None:
    both, _ = classify_forecast(
        "SUM(Factuur.lookupRecords(Kosten=$id).Bedrag)", "Soort"
    )
    assert both is True
    subset, _ = classify_forecast(
        'SUM(Factuur.lookupRecords(Kosten=$id, Soort="Realisatie").Bedrag)', "Soort"
    )
    assert subset is False
    assert classify_forecast("MAX($Begroot, $Iets)", "Soort")[0] is None


def test_coverage_basis_shapes() -> None:
    forecast, _ = classify_coverage_basis(
        "$Percentage * $Kosten.Prognose_realisatie",
        forecast_column="Prognose_realisatie",
        budgeted_column="Begroot",
    )
    assert forecast is CoverageBasis.FORECAST
    budgeted, _ = classify_coverage_basis(
        "$Percentage * $Kosten.Begroot",
        forecast_column="Prognose_realisatie",
        budgeted_column="Begroot",
    )
    assert budgeted is CoverageBasis.BUDGETED
    assert (
        classify_coverage_basis(
            "$Percentage * max($Kosten.Begroot, $Kosten.Prognose_realisatie)",
            forecast_column="Prognose_realisatie",
            budgeted_column="Begroot",
        )[0]
        is None
    )
    assert (
        classify_coverage_basis(
            "$Percentage * 1000", forecast_column="P", budgeted_column="B"
        )[0]
        is None
    )


def test_findings_on_the_fictional_document(
    document: GristDocument, mapping: Mapping
) -> None:
    findings = {f.rule: f for f in check_formulas(document, mapping)}
    assert findings["R2"].verdict == MATCH
    assert findings["R2"].option == "grist_datedif"
    assert findings["R6"].option == "both"
    assert findings["R7"].option == "forecast"
    # Budgeted is typed in, so R4 is a question for the reconciliation.
    assert findings["R4"].verdict == ENTERED
    all_findings = list(findings.values())
    assert suggested_partial_months(all_findings) is PartialMonths.GRIST_DATEDIF
    assert suggested_coverage_basis(all_findings) is CoverageBasis.FORECAST


def test_unknown_formula_is_shown_not_guessed(tmp_path: Path, mapping: Mapping) -> None:
    tables = fictional_tables()
    for table in tables:
        if table.table_id == "Inzet":
            for col in table.columns:
                if col.col_id == "Inzetbedrag":
                    col.formula = "bereken_inzet($Startdatum, $Einddatum, $FTE)"
    with GristDocument(build_grist(tmp_path / "eigen.grist", tables)) as doc:
        findings = {f.rule: f for f in check_formulas(doc, mapping)}
    r2 = findings["R2"]
    assert r2.verdict == UNRECOGNISED
    assert r2.option is None
    assert "bereken_inzet" in r2.formula
    assert suggested_partial_months(list(findings.values())) is None
