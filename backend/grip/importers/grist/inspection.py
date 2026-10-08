"""The inspection report: what is in a Grist document.

This is the first thing to run on the real document. It prints every table
with its row count, every column with its type, and every formula in full,
followed by the verdict on the formulas that decide open questions and the
result of checking the mapping. It prints structure only, never cell values,
so the output can be shared to finish the mapping.
"""

from __future__ import annotations

from grip.importers.grist.document import GristDocument
from grip.importers.grist.formulas import FormulaFinding, check_formulas
from grip.importers.grist.mapping import Mapping, MappingCheck, check_mapping


def render_tables(document: GristDocument) -> list[str]:
    lines = []
    for table in document.tables:
        kind = " (samenvattingstabel)" if table.is_summary else ""
        noun = "rij" if table.row_count == 1 else "rijen"
        lines.append(f"{table.table_id}{kind}: {table.row_count} {noun}")
        for column in table.user_columns:
            marker = "formule" if column.is_formula else "gegevens"
            label = (
                f"  label: {column.label}"
                if column.label and column.label != column.col_id
                else ""
            )
            lines.append(f"  {column.col_id}  [{column.type}, {marker}]{label}")
            formula = column.formula.strip()
            if formula:
                prefix = "= " if column.is_formula else "standaardwaarde = "
                first, *rest = formula.splitlines()
                lines.append(f"      {prefix}{first}")
                lines += [f"        {line}" for line in rest]
        lines.append("")
    return lines


def render_formulas(findings: list[FormulaFinding]) -> list[str]:
    lines = []
    for finding in findings:
        option = f" -> {finding.option}" if finding.option else ""
        lines.append(f"{finding.rule}  {finding.question}")
        lines.append(f"    kolom: {finding.column}")
        lines.append(f"    oordeel: {finding.verdict}{option}")
        lines.append(f"    {finding.explanation}")
        if finding.formula.strip():
            first, *rest = finding.formula.strip().splitlines()
            lines.append(f"    formule: {first}")
            lines += [f"             {line}" for line in rest]
        lines.append("")
    return lines


def render_check(check: MappingCheck) -> list[str]:
    lines = []
    order = {"fout": 0, "waarschuwing": 1, "info": 2}
    for finding in sorted(check.findings, key=lambda f: (order[f.severity], f.table)):
        lines.append(f"[{finding.severity}] {finding.table}: {finding.message}")
    if not check.findings:
        lines.append("Geen bevindingen.")
    errors = len(check.errors)
    lines.append("")
    lines.append(
        "De koppeling past op het document."
        if check.ok
        else f"De koppeling past niet: {errors} fout(en). Pas mapping.toml aan."
    )
    return lines


def render_inspection(document: GristDocument, mapping: Mapping) -> str:
    check = check_mapping(document, mapping)
    findings = check_formulas(document, mapping)
    lines = [
        f"Inspectie van {document.path.name}",
        "=" * (14 + len(document.path.name)),
        "",
        f"Tabellen: {len(document.tables)}. Hieronder staat alleen structuur, "
        "geen inhoud van cellen.",
        "",
        "Tabellen en kolommen",
        "--------------------",
        "",
        *render_tables(document),
        "Formules achter de open vragen",
        "------------------------------",
        "",
        *render_formulas(findings),
        f"Koppeling ({mapping.source})",
        "-" * (12 + len(mapping.source)),
        "",
        *render_check(check),
    ]
    return "\n".join(lines) + "\n"
