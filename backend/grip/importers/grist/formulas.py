"""Check the Grist formulas behind the rules the import must confirm.

Four questions in docs/domein.md depend on how the Grist document computes
its amounts. The formulas are in the document's metadata, so they can be
read rather than guessed at. This module recognises the few shapes that
decide those questions and reports anything else as unrecognised, with the
formula text, for a person to read. It does not parse Python in general.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from grip.calc import CoverageBasis, PartialMonths
from grip.importers.grist.document import GristColumn, GristDocument
from grip.importers.grist.mapping import Mapping

MATCH = "herkend"
UNRECOGNISED = "niet herkend"
ENTERED = "ingevoerd"
ABSENT = "ontbreekt"


@dataclass(frozen=True)
class FormulaFinding:
    rule: str
    question: str
    column: str
    verdict: str
    # The calc option this formula matches, as its value; None when the
    # question is not about an option or the formula is unrecognised.
    option: str | None
    explanation: str
    formula: str = ""

    @property
    def decided(self) -> bool:
        return self.verdict in (MATCH, ENTERED)


def _squash(formula: str) -> str:
    return re.sub(r"\s+", "", formula)


_DATEDIF = re.compile(r"DATEDIF\((?P<args>[^)]*)\)", re.I)


def classify_partial_months(formula: str) -> tuple[PartialMonths | None, str]:
    """Which partial-month strategy an allocation amount formula uses."""
    flat = _squash(formula)
    if not flat:
        return None, "Geen formule."
    datedif = _DATEDIF.search(flat)
    if datedif:
        unit = datedif.group("args").rsplit(",", 1)[-1].strip("\"'").upper()
        rest = flat[: datedif.start()] + flat[datedif.end() :]
        if unit == "M" and re.search(r"\+1(?!\d)", rest):
            return (
                PartialMonths.GRIST_DATEDIF,
                'Aantal maanden is DATEDIF(start, eind, "M") + 1; elke maand telt '
                "volledig.",
            )
        if unit == "M":
            return None, 'DATEDIF met "M" zonder + 1: een maand minder dan verwacht.'
        if unit == "D":
            return (
                PartialMonths.CALENDAR_DAYS,
                "Rekent in dagen; komt overeen met naar rato van kalenderdagen.",
            )
    if re.search(r"\.year.*\*12.*\.month.*\.month", flat) or re.search(
        r"\.month.*\.month.*\.year.*\*12", flat
    ):
        return (
            PartialMonths.WHOLE_MONTHS,
            "Telt kalendermaanden uit jaar en maand; elke geraakte maand telt "
            "volledig.",
        )
    if "monthrange" in flat or re.search(r"\.days\b", flat):
        return (
            PartialMonths.CALENDAR_DAYS,
            "Rekent met dagen in de maand; naar rato van kalenderdagen.",
        )
    return None, "Vorm van de formule is niet herkend."


def classify_forecast(formula: str, kind_column: str | None) -> tuple[bool | None, str]:
    """Whether a cost item's forecast adds actual and estimate lines together.

    Returns True for "both", False for "a subset", None when unrecognised.
    """
    flat = _squash(formula)
    if not flat:
        return None, "Geen formule."
    if "lookupRecords" not in flat or not re.search(r"\bSUM\(|sum\(", flat):
        return None, "Geen som over opgezochte factuurregels."
    lookup = re.search(r"lookupRecords\((?P<args>[^)]*)\)", flat)
    args = lookup.group("args") if lookup else ""
    filters = [part.split("=", 1)[0] for part in args.split(",") if "=" in part]
    if len(filters) <= 1 and not (kind_column and kind_column in args):
        return (
            True,
            "Somt alle factuurregels van de kostenpost: realisatie en inschatting.",
        )
    return False, "Somt een deel van de factuurregels (extra filter in de opzoeking)."


def classify_coverage_basis(
    formula: str, *, forecast_column: str | None, budgeted_column: str | None
) -> tuple[CoverageBasis | None, str]:
    """Whether a coverage amount is a percentage of the forecast or the budget."""
    flat = _squash(formula)
    if not flat:
        return None, "Geen formule."
    uses_forecast = bool(forecast_column and f".{forecast_column}" in flat) or bool(
        re.search(r"\.[A-Za-z_]*([Pp]rognose|[Rr]ealisatie)", flat)
    )
    uses_budgeted = bool(budgeted_column and f".{budgeted_column}" in flat)
    if uses_forecast and not uses_budgeted:
        return CoverageBasis.FORECAST, "Percentage van de prognose van de kostenpost."
    if uses_budgeted and not uses_forecast:
        return (
            CoverageBasis.BUDGETED,
            "Percentage van het begrote bedrag van de kostenpost.",
        )
    if uses_forecast and uses_budgeted:
        return None, "Gebruikt zowel prognose als begroot."
    return None, "Verwijst niet naar prognose of begroot van de kostenpost."


def _column(
    document: GristDocument, mapping: Mapping, table: str, field: str
) -> tuple[GristColumn | None, str]:
    table_mapping = mapping.table(table)
    if table_mapping is None:
        return None, f"{table}.{field}"
    col_id = table_mapping.col(field)
    label = f"{table_mapping.grist_table}.{col_id or '?'}"
    if col_id is None:
        return None, label
    grist_table = document.table(table_mapping.grist_table)
    if grist_table is None:
        return None, label
    return grist_table.column(col_id), label


def check_formulas(document: GristDocument, mapping: Mapping) -> list[FormulaFinding]:
    """The four formula questions, each with a verdict."""
    findings: list[FormulaFinding] = []

    # R2 and R3: the allocation amount and partial months.
    column, label = _column(document, mapping, "allocations", "amount")
    question = "Hoe worden gedeeltelijke maanden geprijsd?"
    if column is None:
        findings.append(
            FormulaFinding("R2", question, label, ABSENT, None, "Kolom niet gevonden.")
        )
    elif not column.is_formula:
        findings.append(
            FormulaFinding(
                "R2",
                question,
                label,
                ENTERED,
                None,
                "Het inzetbedrag is ingevoerd, niet berekend; de aansluiting moet "
                "uitwijzen welke strategie past.",
            )
        )
    else:
        strategy, why = classify_partial_months(column.formula)
        findings.append(
            FormulaFinding(
                "R2",
                question,
                label,
                MATCH if strategy else UNRECOGNISED,
                strategy.value if strategy else None,
                why,
                column.formula,
            )
        )

    # R6: the forecast of a cost item.
    column, label = _column(document, mapping, "cost_items", "forecast")
    question = "Telt de prognose realisatie en inschatting bij elkaar op?"
    invoice_mapping = mapping.table("invoice_lines")
    kind_column = invoice_mapping.col("kind") if invoice_mapping else None
    if column is None:
        findings.append(
            FormulaFinding("R6", question, label, ABSENT, None, "Kolom niet gevonden.")
        )
    elif not column.is_formula:
        findings.append(
            FormulaFinding(
                "R6", question, label, ENTERED, None, "De prognose is ingevoerd."
            )
        )
    else:
        both, why = classify_forecast(column.formula, kind_column)
        findings.append(
            FormulaFinding(
                "R6",
                question,
                label,
                MATCH if both is not None else UNRECOGNISED,
                None if both is None else ("both" if both else "subset"),
                why,
                column.formula,
            )
        )

    # R7: the basis of a coverage amount.
    column, label = _column(document, mapping, "coverages", "amount")
    question = "Gaat het dekkingspercentage over de prognose of over begroot?"
    cost_mapping = mapping.table("cost_items")
    if column is None:
        findings.append(
            FormulaFinding("R7", question, label, ABSENT, None, "Kolom niet gevonden.")
        )
    elif not column.is_formula:
        findings.append(
            FormulaFinding(
                "R7", question, label, ENTERED, None, "Het dekkingsbedrag is ingevoerd."
            )
        )
    else:
        basis, why = classify_coverage_basis(
            column.formula,
            forecast_column=cost_mapping.col("forecast") if cost_mapping else None,
            budgeted_column=cost_mapping.col("budgeted") if cost_mapping else None,
        )
        findings.append(
            FormulaFinding(
                "R7",
                question,
                label,
                MATCH if basis else UNRECOGNISED,
                basis.value if basis else None,
                why,
                column.formula,
            )
        )

    # R4: budgeted on a budget line, entered or computed.
    column, label = _column(document, mapping, "budget_lines", "budgeted")
    question = "Is Begroot op een begrotingsregel ingevoerd of berekend?"
    if column is None:
        findings.append(
            FormulaFinding("R4", question, label, ABSENT, None, "Kolom niet gevonden.")
        )
    elif column.is_formula:
        findings.append(
            FormulaFinding(
                "R4",
                question,
                label,
                UNRECOGNISED,
                "computed",
                "Begroot is een formule; lees haar en vergelijk met FTE maal "
                "maandtarief (R4). De aansluiting somt de afwijkingen op.",
                column.formula,
            )
        )
    else:
        findings.append(
            FormulaFinding(
                "R4",
                question,
                label,
                ENTERED,
                "entered",
                "Begroot is een ingevoerd bedrag. Voor personeelsregels rekent grip "
                "het uit (R4); de aansluiting somt de afwijkingen op.",
                column.formula if column.has_default_formula else "",
            )
        )
    return findings


def suggested_partial_months(findings: list[FormulaFinding]) -> PartialMonths | None:
    for finding in findings:
        if finding.rule == "R2" and finding.verdict == MATCH and finding.option:
            return PartialMonths(finding.option)
    return None


def suggested_coverage_basis(findings: list[FormulaFinding]) -> CoverageBasis | None:
    for finding in findings:
        if finding.rule == "R7" and finding.verdict == MATCH and finding.option:
            return CoverageBasis(finding.option)
    return None
