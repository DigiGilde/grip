"""The report of an assignment as one printable HTML page.

The page is rendered from the response that was already filtered for the
reader, never from the read model, so it cannot show a field the reader may
not see: a section whose data is absent is left out. Same plain style as the
quote document; nothing is loaded from outside the page.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

from grip.services.quote_document import format_date, format_euro
from grip.services.reports.labels import (
    ACCEPTANCE_FORM_LABELS,
    ASSIGNMENT_KIND_LABELS,
    status_label,
)

_STYLE = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    font-family: "Rijksoverheid Sans Text", "RO Sans", Verdana, Arial, sans-serif;
    font-size: 11pt; line-height: 1.45; color: #111; background: #fff;
    margin: 0; padding: 2rem 1rem;
  }
  main { max-width: 48rem; margin: 0 auto; }
  h1 { font-size: 20pt; margin: 0 0 0.25rem; }
  p.lead { margin: 0 0 1.5rem; color: #444; }
  h2 { font-size: 13pt; margin: 2rem 0 0.5rem; }
  h3 { font-size: 11pt; margin: 1.25rem 0 0.35rem; }
  dl.meta { display: grid; grid-template-columns: 11rem 1fr; gap: 0.2rem 1rem;
    margin: 0 0 1.5rem; }
  dl.meta dt { color: #444; }
  dl.meta dd { margin: 0; overflow-wrap: anywhere; }
  table { border-collapse: collapse; width: 100%; font-size: 10pt; }
  caption { text-align: left; color: #444; font-size: 9pt; padding-bottom: 0.25rem; }
  th, td { text-align: left; vertical-align: top; padding: 0.35rem 0.5rem;
    border-bottom: 1px solid #999; }
  th { border-bottom: 2px solid #111; }
  td.num, th.num { text-align: right; white-space: nowrap;
    font-variant-numeric: tabular-nums; }
  tr.total td { font-weight: bold; border-top: 2px solid #111; border-bottom: 0; }
  .sub { color: #444; font-size: 9pt; }
  .text { white-space: pre-wrap; }
  ul { margin: 0.25rem 0 0; padding-left: 1.25rem; }
  footer { margin-top: 2.5rem; padding-top: 0.75rem; border-top: 1px solid #999;
    font-size: 8.5pt; color: #333; }
  @page { size: A4; margin: 20mm 18mm; }
  @media print {
    body { padding: 0; }
    main { max-width: none; }
    h2, h3, thead { break-after: avoid; }
    tr { break-inside: avoid; }
    thead { display: table-header-group; }
  }
"""


def _date(value: Any) -> str:
    if isinstance(value, datetime):
        return format_date(value.date())
    if isinstance(value, date):
        return format_date(value)
    if isinstance(value, str) and value:
        try:
            return format_date(date.fromisoformat(value[:10]))
        except ValueError:
            return value
    return ""


def _period(start: Any, end: Any) -> str:
    first, last = _date(start), _date(end)
    if first and last:
        return f"{first} t/m {last}"
    if first:
        return f"vanaf {first}"
    if last:
        return f"t/m {last}"
    return ""


def _euro(cents: Any) -> str:
    return format_euro(cents) if isinstance(cents, int) else ""


def _number(value: Any) -> str:
    """A decimal as the Dutch write it, without trailing zeros."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ""
    text = format(number.normalize(), "f")
    return text.replace(".", ",")


def _rows(cells: list[list[str]], numeric_from: int) -> str:
    return "\n".join(
        "<tr>"
        + "".join(
            f'<td class="num">{cell}</td>'
            if index >= numeric_from
            else f"<td>{cell}</td>"
            for index, cell in enumerate(row)
        )
        + "</tr>"
        for row in cells
    )


def _head(labels: list[str], numeric_from: int) -> str:
    return (
        "<thead><tr>"
        + "".join(
            f'<th scope="col" class="num">{escape(label)}</th>'
            if index >= numeric_from
            else f'<th scope="col">{escape(label)}</th>'
            for index, label in enumerate(labels)
        )
        + "</tr></thead>"
    )


_TOTALS_HEAD = ["Begroot", "Gerealiseerd", "Prognose", "Kosten", "Beschikbaar"]


def _totals_cells(totals: Any) -> list[str] | None:
    if not isinstance(totals, dict) or "budgeted_cents" not in totals:
        return None
    return [
        escape(_euro(totals.get("budgeted_cents"))),
        escape(_euro(totals.get("realised_cents"))),
        escape(_euro(totals.get("forecast_cents"))),
        escape(_euro(totals.get("coverage_cents"))),
        escape(_euro(totals.get("available_cents")))
        + (
            ' <span class="sub">(overschrijding)</span>'
            if totals.get("overrun")
            else ""
        ),
    ]


def _agreed_section(report: dict[str, Any]) -> str:
    agreed = report.get("agreed")
    if isinstance(agreed, dict) and "total_cents" in agreed:
        rows = [
            [
                escape(str(line.get("description") or ""))
                + (
                    f'<br><span class="sub">{escape(str(line["role"]))}</span>'
                    if line.get("role") and line.get("role") != line.get("description")
                    else ""
                ),
                escape(_period(line.get("start_date"), line.get("end_date"))),
                escape(_number(line.get("fte"))) if line.get("fte") else "",
                escape(_euro(line.get("amount_cents"))),
            ]
            for line in agreed.get("lines") or []
        ]
        subtotals = agreed.get("subtotals") or []
        subtotal_rows = ""
        if len(subtotals) > 1:
            subtotal_rows = "\n".join(
                f'<tr><td colspan="3">Subtotaal {escape(str(s.get("year")))}</td>'
                f'<td class="num">{escape(_euro(s.get("amount_cents")))}</td></tr>'
                for s in subtotals
            )
        facts = [f"Offerte uitgegeven op {escape(_date(agreed.get('issued_at')))}."]
        if agreed.get("accepted_at"):
            form = ACCEPTANCE_FORM_LABELS.get(str(agreed.get("form") or ""), "")
            facts.append(
                f"Akkoord op {escape(_date(agreed.get('accepted_at')))}"
                + (f" ({escape(form.lower())})" if form else "")
                + "."
            )
        return f"""<h2>Wat is afgesproken</h2>
<p>{" ".join(facts)}</p>
<table>
{_head(["Omschrijving", "Periode", "FTE", "Bedrag"], 2)}
<tbody>
{_rows(rows, 2)}
{subtotal_rows}
<tr class="total"><td colspan="3">Totaal afgesproken</td>
<td class="num">{escape(_euro(agreed.get("total_cents")))}</td></tr>
</tbody>
</table>"""
    if isinstance(report.get("quoted_amount_cents"), int):
        return (
            "<h2>Wat is afgesproken</h2>\n"
            "<p>Er is geen offerte waarop akkoord is gegeven. Het afgesproken bedrag "
            f"is {escape(_euro(report['quoted_amount_cents']))}.</p>"
        )
    if "quoted_amount_cents" in report or "agreed" in report:
        return (
            "<h2>Wat is afgesproken</h2>\n"
            "<p>Er is geen offerte waarop akkoord is gegeven.</p>"
        )
    return ""


def _delivered_section(report: dict[str, Any]) -> str:
    parts: list[str] = ["<h2>Wat is geleverd</h2>"]
    final = report.get("final_report")
    if isinstance(final, dict) and final:
        parts.append(f"<p>Eindrapport van {escape(_date(final.get('issued_at')))}.</p>")
        if final.get("summary"):
            parts.append(f'<p class="text">{escape(str(final["summary"]))}</p>')
        delivered = final.get("delivered") or []
        not_delivered = final.get("not_delivered") or []
        parts.append("<h3>Geleverd</h3>")
        parts.append(
            "<ul>" + "".join(f"<li>{escape(str(i))}</li>" for i in delivered) + "</ul>"
            if delivered
            else "<p>Het eindrapport noemt niets als geleverd.</p>"
        )
        parts.append("<h3>Niet geleverd</h3>")
        parts.append(
            "<ul>"
            + "".join(f"<li>{escape(str(i))}</li>" for i in not_delivered)
            + "</ul>"
            if not_delivered
            else "<p>Het eindrapport noemt niets als niet geleverd.</p>"
        )
    else:
        parts.append("<p>Er is nog geen eindrapport uitgegeven.</p>")

    total, closed = report.get("months_total"), report.get("months_closed")
    if isinstance(total, int) and isinstance(closed, int) and total:
        parts.append(
            f"<p>Van de {total} maanden van de opdracht zijn er {closed} afgesloten "
            "met vastgestelde inzet.</p>"
        )

    history = report.get("status_history") or []
    if history:
        rows = [
            [
                escape(_date(change.get("occurred_at"))),
                escape(status_label(change.get("new_status")))
                + (
                    f'<br><span class="sub">{escape(str(change["reason"]))}</span>'
                    if change.get("reason")
                    else ""
                ),
            ]
            for change in history
        ]
        parts.append(
            "<h3>Verloop</h3>\n<table>\n"
            + _head(["Datum", "Status"], 2)
            + f"\n<tbody>\n{_rows(rows, 2)}\n</tbody>\n</table>"
        )
    return "\n".join(parts)


def _cost_section(report: dict[str, Any]) -> str:
    whole = _totals_cells(report.get("totals"))
    if whole is None and not report.get("pricing_error"):
        return ""
    parts: list[str] = ["<h2>Wat het heeft gekost</h2>"]
    if report.get("pricing_error"):
        parts.append(f"<p>{escape(str(report['pricing_error']))}</p>")

    period_rows = []
    for period in report.get("periods") or []:
        cells = _totals_cells(period.get("totals"))
        if cells is not None:
            period_rows.append([escape(str(period.get("year")))] + cells)
    if period_rows or whole is not None:
        total_row = ""
        if whole is not None:
            total_row = (
                '<tr class="total"><td>Hele looptijd</td>'
                + "".join(f'<td class="num">{cell}</td>' for cell in whole)
                + "</tr>"
            )
        parts.append(
            "<table>\n<caption>Per jaar. Gerealiseerd is de inzet van afgesloten "
            "maanden; prognose is de geplande inzet van open maanden.</caption>\n"
            + _head(["Periode"] + _TOTALS_HEAD, 1)
            + f"\n<tbody>\n{_rows(period_rows, 1)}\n{total_row}\n</tbody>\n</table>"
        )

    line_rows = []
    for line in report.get("lines") or []:
        cells = _totals_cells(line.get("totals"))
        if cells is not None:
            line_rows.append([escape(str(line.get("description") or ""))] + cells)
    if line_rows:
        parts.append(
            "<h3>Per begrotingsregel</h3>\n<table>\n"
            + _head(["Begrotingsregel"] + _TOTALS_HEAD, 1)
            + f"\n<tbody>\n{_rows(line_rows, 1)}\n</tbody>\n</table>"
        )

    costs = report.get("costs") or []
    if costs:
        cost_rows = [
            [
                escape(str(cost.get("description") or "")),
                escape(str(cost.get("budget_line_description") or "")),
                escape(_number(cost.get("pct"))) + "%",
                escape(_euro(cost.get("amount_cents"))),
            ]
            for cost in costs
        ]
        parts.append(
            "<h3>Kosten en dekking</h3>\n<table>\n"
            + _head(["Kostenpost", "Gedekt door", "Aandeel", "Bedrag"], 2)
            + f"\n<tbody>\n{_rows(cost_rows, 2)}\n</tbody>\n</table>"
        )
    return "\n".join(parts)


def _staffing_section(report: dict[str, Any]) -> str:
    staffing = report.get("staffing") or []
    if not staffing:
        return ""
    rows = [
        [
            escape(str(member.get("person_name") or "")),
            escape(
                str(member.get("role") or member.get("budget_line_description") or "")
            ),
            escape(_period(member.get("start_date"), member.get("end_date"))),
            (escape(_number(member.get("fte_pct"))) + "%")
            if "fte_pct" in member
            else "",
        ]
        for member in staffing
    ]
    return (
        "<h2>Wie eraan werkte</h2>\n"
        '<p class="sub">Alleen voor intern gebruik.</p>\n<table>\n'
        + _head(["Naam", "Rol", "Periode", "Inzet"], 3)
        + f"\n<tbody>\n{_rows(rows, 3)}\n</tbody>\n</table>"
    )


def render_report_html(report: dict[str, Any], *, instance_name: str) -> str:
    """The filtered report of an assignment as one self-contained HTML page."""
    name = escape(str(report.get("name") or ""))
    internal = report.get("audience") == "internal"
    meta: list[tuple[str, str]] = []
    if report.get("client_name"):
        meta.append(("Opdrachtgever", escape(str(report["client_name"]))))
    meta.append(
        ("Opdrachtnemer", escape(str(report.get("contractor_name") or instance_name)))
    )
    period = _period(report.get("start_date"), report.get("end_date"))
    if period:
        meta.append(("Looptijd", escape(period)))
    meta.append(("Status", escape(status_label(report.get("status")))))
    kind = ASSIGNMENT_KIND_LABELS.get(str(report.get("kind") or ""))
    if kind:
        meta.append(("Soort", escape(kind)))
    if report.get("uri"):
        meta.append(("Kenmerk", escape(str(report["uri"]))))
    refs = [ref for ref in report.get("context_refs") or [] if isinstance(ref, str)]
    if refs:
        meta.append(("Context", "<br>".join(escape(ref) for ref in refs)))
    meta_html = "\n".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in meta)

    sections = "\n\n".join(
        section
        for section in (
            _agreed_section(report),
            _delivered_section(report),
            _cost_section(report),
            _staffing_section(report) if internal else "",
        )
        if section
    )
    version = "interne versie" if internal else "versie voor de opdrachtgever"
    generated = _date(report.get("generated_on"))
    return f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapportage {name}</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<h1>Rapportage</h1>
<p class="lead">{name}</p>
<dl class="meta">
{meta_html}
</dl>

{sections}

<footer>
<p>Opgesteld op {escape(generated)} door {escape(instance_name)}, {version}.
Bedragen zijn berekend per kalendermaand, tegen het tarief van het jaar waarin
de maand valt.</p>
</footer>
</main>
</body>
</html>
"""
