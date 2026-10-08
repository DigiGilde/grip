"""The quote as a document: a print-ready page rendered from the snapshot.

The document is always built from the frozen snapshot of an issued quote,
never from live data, so it shows exactly what the hash covers. It is plain
HTML with a print stylesheet: opened in a browser it prints or saves as pdf
on A4. A generated pdf file is a later step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from typing import Any

_MONTHS = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)


@dataclass(frozen=True)
class QuoteDocumentContext:
    """What the document shows besides the snapshot itself."""

    quote_uri: str
    snapshot_hash: str
    issued_at: datetime
    contractor_name: str
    client_name: str | None = None
    client_contact: str | None = None


def format_euro(cents: int) -> str:
    """Amount in cents as Dutch currency text, for example ``€ 172.800,00``."""
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"{sign}€ {grouped},{fraction:02d}"


def format_date(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _iso_date(text: str | None) -> str:
    if not text:
        return ""
    try:
        return format_date(date.fromisoformat(text))
    except ValueError:
        return text


def _decimal_nl(text: str | None) -> str:
    return (text or "").replace(".", ",")


def _cents(money: Any) -> int:
    if isinstance(money, dict):
        value = money.get("amount_cents")
        if isinstance(value, int):
            return value
    return 0


def _rate_cell(line: dict[str, Any]) -> str:
    if "monthly_rate" in line:
        return escape(format_euro(_cents(line["monthly_rate"])))
    per_year = line.get("monthly_rates_per_year") or []
    parts = [
        f"{escape(str(entry.get('year')))}: "
        f"{escape(format_euro(_cents(entry.get('monthly_rate'))))}"
        for entry in per_year
    ]
    return "<br>".join(parts)


def _period_cell(line: dict[str, Any]) -> str:
    period = line.get("period")
    if isinstance(period, dict):
        start = _iso_date(period.get("start_date"))
        end = _iso_date(period.get("end_date"))
        return f"{escape(start)} t/m {escape(end)}"
    if line.get("year") is not None:
        return escape(str(line["year"]))
    return ""


def _line_row(line: dict[str, Any]) -> str:
    description = escape(str(line.get("description") or ""))
    role = line.get("role")
    if role and role != line.get("description"):
        description += f'<br><span class="sub">{escape(str(role))}</span>'
    personnel = line.get("kind") == "personnel"
    fte = escape(_decimal_nl(line.get("fte"))) if personnel else ""
    category = escape(str(line.get("rate_category") or "")) if personnel else ""
    rate = _rate_cell(line) if personnel else ""
    amount = escape(format_euro(_cents(line.get("amount"))))
    return (
        "<tr>"
        f"<td>{description}</td>"
        f'<td class="num">{fte}</td>'
        f"<td>{_period_cell(line)}</td>"
        f'<td class="center">{category}</td>'
        f'<td class="num">{rate}</td>'
        f'<td class="num">{amount}</td>'
        "</tr>"
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
  h1 { font-size: 20pt; margin: 0 0 1.5rem; }
  h2 { font-size: 13pt; margin: 2rem 0 0.5rem; }
  dl.meta { display: grid; grid-template-columns: 10rem 1fr; gap: 0.2rem 1rem;
    margin: 0 0 1.5rem; }
  dl.meta dt { color: #444; }
  dl.meta dd { margin: 0; }
  table { border-collapse: collapse; width: 100%; font-size: 10pt; }
  th, td { text-align: left; vertical-align: top; padding: 0.35rem 0.5rem;
    border-bottom: 1px solid #999; }
  th { border-bottom: 2px solid #111; }
  td.num, th.num { text-align: right; white-space: nowrap;
    font-variant-numeric: tabular-nums; }
  td.center, th.center { text-align: center; }
  tr.total td { font-weight: bold; border-top: 2px solid #111; border-bottom: 0; }
  .sub { color: #444; font-size: 9pt; }
  .conditions { white-space: pre-wrap; }
  .sign { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-top: 1rem; }
  .sign dl { display: grid; grid-template-columns: 7rem 1fr; gap: 1.6rem 0.5rem;
    margin: 0; }
  .sign dd { margin: 0; border-bottom: 1px solid #111; min-height: 1.4rem; }
  footer { margin-top: 2.5rem; padding-top: 0.75rem; border-top: 1px solid #999;
    font-size: 8.5pt; color: #333; }
  footer code { font-family: ui-monospace, Menlo, Consolas, monospace;
    word-break: break-all; }
  @page { size: A4; margin: 20mm 18mm; }
  @media print {
    body { padding: 0; }
    main { max-width: none; }
    h2, thead { break-after: avoid; }
    tr, .sign { break-inside: avoid; }
    thead { display: table-header-group; }
  }
"""


def render_quote_html(snapshot: dict[str, Any], context: QuoteDocumentContext) -> str:
    """The quote as one self-contained HTML page.

    Every value from the snapshot is escaped. Nothing is loaded from outside
    the page: no scripts, no fonts, no images.
    """
    name = escape(str(snapshot.get("name") or ""))
    lines = [line for line in snapshot.get("lines") or [] if isinstance(line, dict)]
    rows = "\n".join(_line_row(line) for line in lines)

    subtotals = snapshot.get("subtotals_per_year") or []
    subtotal_rows = ""
    if len(subtotals) > 1:
        subtotal_rows = "\n".join(
            "<tr>"
            f'<td colspan="5">Subtotaal {escape(str(entry.get("year")))}</td>'
            f'<td class="num">{escape(format_euro(_cents(entry.get("amount"))))}</td>'
            "</tr>"
            for entry in subtotals
            if isinstance(entry, dict)
        )
    total = escape(format_euro(_cents(snapshot.get("total"))))

    meta = [
        ("Van", escape(context.contractor_name)),
    ]
    if context.client_name:
        meta.append(("Aan", escape(context.client_name)))
    if context.client_contact:
        meta.append(("Ter attentie van", escape(context.client_contact)))
    meta.append(("Datum", escape(format_date(context.issued_at.date()))))
    meta.append(("Kenmerk", escape(context.quote_uri)))
    meta.append(("Betreft", name))
    if snapshot.get("valid_until"):
        meta.append(("Geldig tot en met", escape(_iso_date(snapshot["valid_until"]))))
    meta_html = "\n".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in meta)

    context_refs = [
        ref for ref in snapshot.get("context_refs") or [] if isinstance(ref, str)
    ]
    context_html = ""
    if context_refs:
        items = "\n".join(f"<li>{escape(ref)}</li>" for ref in context_refs)
        context_html = f"<h2>Context</h2>\n<ul>\n{items}\n</ul>"

    conditions_html = ""
    if snapshot.get("conditions"):
        conditions_html = (
            "<h2>Voorwaarden</h2>\n"
            f'<p class="conditions">{escape(str(snapshot["conditions"]))}</p>'
        )

    client = escape(context.client_name or "opdrachtgever")
    return f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offerte {name}</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<h1>Offerte</h1>
<dl class="meta">
{meta_html}
</dl>

<h2>Begroting</h2>
<table>
<thead>
<tr>
<th scope="col">Omschrijving</th>
<th scope="col" class="num">FTE</th>
<th scope="col">Periode</th>
<th scope="col" class="center">Categorie</th>
<th scope="col" class="num">Maandtarief</th>
<th scope="col" class="num">Bedrag</th>
</tr>
</thead>
<tbody>
{rows}
{subtotal_rows}
<tr class="total"><td colspan="5">Totaal</td><td class="num">{total}</td></tr>
</tbody>
</table>
<p class="sub">Bedragen zijn berekend per kalendermaand, tegen het tarief van het
jaar waarin de maand valt.</p>

{context_html}
{conditions_html}

<h2>Akkoord</h2>
<p>Voor akkoord namens {client}:</p>
<div class="sign">
<dl>
<dt>Naam</dt><dd></dd>
<dt>Functie</dt><dd></dd>
</dl>
<dl>
<dt>Datum</dt><dd></dd>
<dt>Handtekening</dt><dd></dd>
</dl>
</div>

<footer>
<p>Deze offerte is uitgegeven op {escape(format_date(context.issued_at.date()))}
en daarna niet meer gewijzigd. Controlegetal (SHA-256) van de inhoud:<br>
<code>{escape(context.snapshot_hash)}</code></p>
</footer>
</main>
</body>
</html>
"""
