"""The document of a delivery: a factuurverzoek for the financial administration.

One page a person can make an invoice from without asking anything: to whom
the invoice goes and which reference it must carry, for which agreement and
period, the lines that make up the amount, and the total. It is laid out
once, when the period is delivered, and kept; a later change in rates or in
the letterhead does not change it.

The page shares the head, the type and the table style of the quote.
"""

from __future__ import annotations

import os
from datetime import datetime
from html import escape
from typing import Any

from grip.services.quote_document import (
    _STYLE,
    RIBBON_BLUE,
    DocumentEngineError,
    Letterhead,
    _find_homebrew_libraries,
    _font_faces,
    _head,
    _render_lock,
    format_date,
    format_euro,
    letterhead_from_settings,
)

RHYTHM_WORDS = {"month": "per maand", "quarter": "per kwartaal"}

_EXTRA_STYLE = """
  .columns { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12mm;
    margin: 0 0 6mm; }
  .columns h2 { margin-top: 5mm; }
  .columns h2:first-child { margin-top: 0; }
  dl.facts { display: grid; grid-template-columns: 30mm 1fr; gap: 1mm 4mm;
    margin: 0; }
  dl.facts dt { color: #444; }
  dl.facts dd { margin: 0; }
  .missing { color: #444; font-style: italic; }
  .amount-due { margin: 0 0 8mm; padding: 3mm 0; border-top: 0.9pt solid #111;
    border-bottom: 0.9pt solid #111; display: grid;
    grid-template-columns: 1fr auto; align-items: baseline; }
  .amount-due .figure { font-size: 16pt; font-variant-numeric: tabular-nums; }
  tr.month-head th { font-weight: bold; padding-top: 3mm; border-bottom: 0; }
  /* A month's name stays with its first line. */
  tr.month-head { break-after: avoid; }
"""

_DETAIL_ROWS = (
    ("organisation", "Organisatie"),
    ("attention_of", "Ten name van"),
    ("address", "Adres of postbus"),
    ("postcode_city", "Postcode en plaats"),
    ("reference", "Kenmerk klant"),
)
_CONTACT_ROWS = (
    ("contact_name", "Naam"),
    ("contact_phone", "Telefoon"),
    ("contact_email", "E-mail"),
)


def _percent(text: str) -> str:
    return f"{text.replace('.', ',')}%"


def _facts(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in rows)


def _detail_rows(
    details: dict[str, str], rows: tuple[tuple[str, str], ...], *, required: set[str]
) -> list[tuple[str, str]]:
    found = []
    for key, label in rows:
        value = details.get(key)
        if value:
            found.append((label, escape(value)))
        elif key in required:
            found.append((label, '<span class="missing">niet opgegeven</span>'))
    return found


def _lines_table(content: dict[str, Any]) -> str:
    with_names = bool(content.get("with_names"))
    head = ["Omschrijving"]
    if with_names:
        head.append("Naam")
    head += ["Inzet", "Maandtarief", "Bedrag"]
    numeric = {"Inzet", "Maandtarief", "Bedrag"}
    header = "".join(
        f'<th scope="col"{' class="num"' if cell in numeric else ""}>{cell}</th>'
        for cell in head
    )
    span = len(head)
    body: list[str] = []
    current = None
    for line in content["lines"]:
        if line["month"] != current:
            current = line["month"]
            body.append(
                f'<tr class="month-head"><th scope="rowgroup" colspan="{span}">'
                f"{escape(line['month_label'].capitalize())}</th></tr>"
            )
        description = escape(line["description"])
        cells = [f"<td>{description}</td>"]
        if with_names:
            cells.append(f"<td>{escape(line['person_name'])}</td>")
        cells += [
            f'<td class="num">{escape(_percent(line["fte_pct"]))}</td>',
            f'<td class="num">{format_euro(line["monthly_rate_cents"])}</td>',
            f'<td class="num">{format_euro(line["amount_cents"])}</td>',
        ]
        body.append("<tr>" + "".join(cells) + "</tr>")
    total = (
        f'<tr class="total"><th scope="row" colspan="{span - 1}">Totaal</th>'
        f'<td class="num">{format_euro(content["total_cents"])}</td></tr>'
    )
    return (
        "<table>\n<thead><tr>"
        + header
        + "</tr></thead>\n<tbody>\n"
        + "\n".join(body)
        + "\n"
        + total
        + "\n</tbody>\n</table>"
    )


def render_html(content: dict[str, Any], letterhead: Letterhead | None = None) -> str:
    """The factuurverzoek as one self-contained page; every value is escaped."""
    letterhead = letterhead or letterhead_from_settings()
    ribbon = letterhead.ribbon_data_uri is not None
    delivered = datetime.fromisoformat(content["delivered_at"])
    sender = str(content["sender"])
    details: dict[str, str] = content.get("details") or {}

    agreement: list[tuple[str, str]] = [
        ("Opdracht", escape(str(content["assignment_name"]))),
    ]
    if content.get("client_name"):
        agreement.append(("Opdrachtgever", escape(str(content["client_name"]))))
    if content.get("quote_reference"):
        agreement.append(("Offerte", escape(str(content["quote_reference"]))))
    if content.get("client_reference"):
        agreement.append(("Kenmerk klant", escape(str(content["client_reference"]))))
    agreement.append(("Periode", escape(str(content["period_label"]))))
    agreement.append(
        ("Factureren", RHYTHM_WORDS.get(str(content["rhythm"]), str(content["rhythm"])))
    )

    invoice_to = _detail_rows(
        details,
        _DETAIL_ROWS,
        required={"organisation", "address", "postcode_city", "reference"},
    )
    contact = _detail_rows(details, _CONTACT_ROWS, required=set())
    contact_block = (
        f'<h2>Contact bij de opdrachtgever</h2>\n<dl class="facts">\n'
        f"{_facts(contact)}\n</dl>"
        if contact
        else ""
    )
    by = (
        f" door {escape(str(content['delivered_by_name']))}"
        if content.get("delivered_by_name")
        else ""
    )
    corrections = any(line["correction"] for line in content["lines"])
    basis = (
        "De bedragen volgen uit de inzet die per maand is vastgesteld, tegen het "
        "tarief dat in die maand gold."
    )
    if corrections:
        basis += (
            " Een regel met Naverrekening is het verschil dat na een eerdere "
            "aanlevering is ontstaan."
        )
    style = (
        (_STYLE + _EXTRA_STYLE)
        .replace("__FIRST_TOP__", "40mm" if ribbon else "24mm")
        .replace("__BLUE__", RIBBON_BLUE)
        .strip()
    )
    reference = escape(str(content["reference"]))
    stamp = delivered.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>Factuurverzoek {reference}</title>
<meta name="author" content="{escape(sender)}">
<meta name="dcterms.created" content="{stamp}">
<meta name="dcterms.modified" content="{stamp}">
<style>
{_font_faces(letterhead)}
{style}
</style>
</head>
<body>
<main class="{"ribboned" if ribbon else "plain"}">
{_head(sender, letterhead)}
<h1>Factuurverzoek</h1>
<dl class="letter">
<dt>Aan</dt><dd>Financiële administratie</dd>
<dt>Datum</dt><dd>{escape(format_date(delivered.date()))}</dd>
<dt>Kenmerk</dt><dd><span class="reference">{reference}</span></dd>
</dl>

<div class="amount-due">
<div>Te factureren over {escape(str(content["period_label"]))}</div>
<div class="figure">{format_euro(content["total_cents"])}</div>
</div>

<div class="columns">
<div>
<h2>Factuur aan</h2>
<dl class="facts">
{_facts(invoice_to)}
</dl>
{contact_block}
</div>
<div>
<h2>Afspraak</h2>
<dl class="facts">
{_facts(agreement)}
</dl>
</div>
</div>

<h2>Specificatie</h2>
{_lines_table(content)}
<p class="quiet note">{basis}</p>

<div class="colophon quiet">
<p>Aangeleverd op {escape(format_date(delivered.date()))}{by}. Dit is geen factuur.
Adres van de opdracht voor systemen: {escape(str(content["assignment_uri"]))}</p>
</div>
</main>
</body>
</html>
"""


def render_pdf(content: dict[str, Any], letterhead: Letterhead | None = None) -> bytes:
    """The factuurverzoek as a tagged PDF; the same content gives the same bytes."""
    _find_homebrew_libraries()
    try:
        from weasyprint import HTML
    except (OSError, ImportError) as exc:
        raise DocumentEngineError() from exc
    html = render_html(content, letterhead)
    delivered = datetime.fromisoformat(content["delivered_at"])
    with _render_lock:
        previous = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = str(int(delivered.timestamp()))
        try:
            pdf: bytes = HTML(string=html, base_url=None).write_pdf(
                pdf_variant="pdf/ua-1",
                pdf_identifier=str(content["reference"]).encode("utf-8")[:32],
            )
        finally:
            if previous is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = previous
    return pdf
