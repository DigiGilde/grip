"""The quote as a document: the thing that leaves the building.

One template, two outputs. ``render_quote_html`` gives the page a browser
shows for "Bekijk"; ``render_quote_pdf`` gives the file that is downloaded,
sent and signed. Both are built from the frozen content of an issued quote
(its canonical form) and from nothing live, so the document shows exactly
what the echtheidskenmerk covers. No name of a member of staff is added here:
the content is on an allow-list (``grip.services.quote_content``) and this
template only adds the sender organisation and the client.

The PDF is made by an HTML-to-PDF engine (WeasyPrint), so the page is laid
out once, in CSS, and the file is a tagged PDF: it has a title, a language,
real text in reading order and table header cells. The same quote gives the
same bytes every time: the creation date is the moment of issue and the
identifier of the file is derived from the echtheidskenmerk.

Head of the page. An organisation that may carry the Rijkslogo configures
the ribbon (``LETTERHEAD_LOGO_PATH``); the page then opens with the Rijkslint
centred at the top and the name of the organisation beside it. Without that
setting the page has a plain head with the name of the organisation. Whether
an organisation may use the logo is not for grip to decide.

Typeface. With ``DOCUMENT_FONT_DIR`` the Rijkshuisstijl typeface is embedded.
Without it the document is set in Verdana, the fallback the huisstijl names,
or the nearest sans-serif the system has.
"""

from __future__ import annotations

import base64
import calendar
import ctypes.util
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

from grip.core.config import Settings, get_settings
from grip.services.errors import DomainError

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

RIBBON_BLUE = "#154273"


class DocumentEngineError(DomainError):
    """The PDF engine is not available on this server."""

    def __init__(self) -> None:
        super().__init__(
            "De pdf kan op deze server niet worden gemaakt: de opmaakbibliotheek "
            "ontbreekt. Bekijk de offerte in de browser, of vraag de beheerder."
        )


@dataclass(frozen=True)
class Letterhead:
    """How the head of a document looks for this instance."""

    # Further lines under the name of the sender: what it is part of.
    lines: tuple[str, ...] = ()
    # The Rijkslint with the coat of arms as an SVG data URI; None for the
    # plain head.
    ribbon_data_uri: str | None = None
    # Directory with the huisstijl typeface, or None.
    font_dir: Path | None = None


def letterhead_from_settings(settings: Settings | None = None) -> Letterhead:
    settings = settings or get_settings()
    lines = tuple(
        part.strip() for part in settings.LETTERHEAD_LINES.split("|") if part.strip()
    )
    ribbon = None
    logo_path = settings.LETTERHEAD_LOGO_PATH.strip()
    if logo_path:
        path = Path(logo_path)
        if path.is_file() and path.suffix.lower() == ".svg":
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            ribbon = f"data:image/svg+xml;base64,{encoded}"
    font_dir = None
    if settings.DOCUMENT_FONT_DIR.strip():
        candidate = Path(settings.DOCUMENT_FONT_DIR.strip())
        if (candidate / "RijksSansWeb-Regular.woff2").is_file():
            font_dir = candidate
    return Letterhead(lines=lines, ribbon_data_uri=ribbon, font_dir=font_dir)


@dataclass(frozen=True)
class QuoteDocumentContext:
    """What the document shows besides the frozen content itself."""

    quote_uri: str
    snapshot_hash: str
    issued_at: datetime
    # The sender when the content does not name one (a quote from before the
    # sender was part of the content).
    contractor_name: str
    client_name: str | None = None
    client_contact: str | None = None
    # The reference when the content does not carry one (an older quote).
    reference: str | None = None
    letterhead: Letterhead = field(default_factory=Letterhead)


def format_euro(cents: int) -> str:
    """Amount in cents as Dutch currency text, for example ``€ 172.800,00``."""
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"{sign}€ {grouped},{fraction:02d}"


def format_date(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _parse_date(text: Any) -> date | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _iso_date(text: Any) -> str:
    parsed = _parse_date(text)
    if parsed is not None:
        return format_date(parsed)
    return text if isinstance(text, str) else ""


def _decimal_nl(text: Any) -> str:
    return text.replace(".", ",") if isinstance(text, str) else ""


def _cents(money: Any) -> int:
    if isinstance(money, dict):
        value = money.get("amount_cents")
        if isinstance(value, int):
            return value
    return 0


def _join_nl(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} en {parts[-1]}"


def scale_text(line: dict[str, Any]) -> str:
    """What a client reads on the rate leaflet: the scales, then the category."""
    category = line.get("rate_category")
    scales = [str(s) for s in line.get("scales") or [] if isinstance(s, int)]
    if scales and category:
        return f"{_join_nl(scales)} (categorie {category})"
    if scales:
        return _join_nl(scales)
    return f"Categorie {category}" if category else ""


def part_month_note(lines: list[dict[str, Any]]) -> str:
    """One clause on a part month, with the first one as the example.

    A line that starts after the first or ends before the last day of a
    month counts that month in proportion to its days. Empty when no line
    has a part month.
    """
    for line in lines:
        period = line.get("period")
        if line.get("kind") != "personnel" or not isinstance(period, dict):
            continue
        start = _parse_date(period.get("start_date"))
        end = _parse_date(period.get("end_date"))
        if start is None or end is None:
            continue
        days_in_start = calendar.monthrange(start.year, start.month)[1]
        days_in_end = calendar.monthrange(end.year, end.month)[1]
        same_month = (start.year, start.month) == (end.year, end.month)
        if same_month and (start.day > 1 or end.day < days_in_end):
            counted, of, month = end.day - start.day + 1, days_in_end, end
        elif start.day > 1:
            counted, of, month = days_in_start - start.day + 1, days_in_start, start
        elif end.day < days_in_end:
            counted, of, month = end.day, days_in_end, end
        else:
            continue
        name = f"{_MONTHS[month.month - 1]} {month.year}"
        return (
            " Een maand die maar deels in de periode valt, telt naar rato van het "
            f"aantal dagen: {name} telt voor {counted} van de {of} dagen."
        )
    return ""


def _rate_periods(line: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in line.get("monthly_rate_periods") or []
        if isinstance(entry, dict)
    ]


def _rate_cell(line: dict[str, Any]) -> str:
    if "monthly_rate" in line:
        return escape(format_euro(_cents(line["monthly_rate"])))
    if _rate_periods(line):
        # The rates stand per period on their own lines under the line.
        return "per periode"
    parts = [
        f"{escape(str(entry.get('year')))}: "
        f"{escape(format_euro(_cents(entry.get('monthly_rate'))))}"
        for entry in line.get("monthly_rates_per_year") or []
        if isinstance(entry, dict)
    ]
    return "<br>".join(parts)


def _rate_period_row(line: dict[str, Any]) -> str:
    """One small line per rate, for a line whose rate changes inside a year."""
    periods = _rate_periods(line)
    if not periods:
        return ""
    parts = [
        f"{escape(_iso_date(entry.get('start_date')))} t/m "
        f"{escape(_iso_date(entry.get('end_date')))}: "
        f"{escape(format_euro(_cents(entry.get('monthly_rate'))))} per maand"
        for entry in periods
    ]
    return f'<tr class="rates"><td colspan="6">{"<br>".join(parts)}</td></tr>'


def rate_change_note(lines: list[dict[str, Any]]) -> str:
    """One clause on a rate that changes inside the period, with the first date."""
    for line in lines:
        periods = _rate_periods(line)
        if len(periods) > 1:
            changes = _iso_date(periods[1].get("start_date"))
            return f" Het tarief wijzigt per {changes}."
    return ""


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
        description += f'<br><span class="quiet">{escape(str(role))}</span>'
    personnel = line.get("kind") == "personnel"
    fte = escape(_decimal_nl(line.get("fte"))) if personnel else ""
    scale = escape(scale_text(line)) if personnel else ""
    rate = _rate_cell(line) if personnel else ""
    amount = escape(format_euro(_cents(line.get("amount"))))
    rates = _rate_period_row(line) if personnel else ""
    opening = '<tr class="has-rates">' if rates else "<tr>"
    return (
        f"{opening}"
        f'<th scope="row">{description}</th>'
        f'<td class="num">{fte}</td>'
        f'<td class="keep">{_period_cell(line)}</td>'
        f'<td class="keep">{scale}</td>'
        f'<td class="num">{rate}</td>'
        f'<td class="num">{amount}</td>'
        "</tr>"
        f"{rates}"
    )


def code_lines(code: str) -> list[str]:
    """A code in blocks of eight, four to a line, so it reads and wraps."""
    blocks = [code[i : i + 8] for i in range(0, len(code), 8)]
    return [" ".join(blocks[i : i + 4]) for i in range(0, len(blocks), 4)]


def _font_faces(letterhead: Letterhead) -> str:
    if letterhead.font_dir is None:
        return ""
    regular = (letterhead.font_dir / "RijksSansWeb-Regular.woff2").as_uri()
    rules = [
        '@font-face { font-family: "RijksSans"; font-style: normal; '
        f'src: url("{regular}") format("woff2"); }}'
    ]
    italic = letterhead.font_dir / "RijksSansWeb-Italic.woff2"
    if italic.is_file():
        rules.append(
            '@font-face { font-family: "RijksSans"; font-style: italic; '
            f'src: url("{italic.as_uri()}") format("woff2"); }}'
        )
    return "\n".join(rules)


# Measurements. A4 with the margins and the logo height of the Rijkshuisstijl
# as other government sites apply them to their PDFs: the ribbon centred at
# the top, 23 mm high from the edge of the page; side margins 18 mm.
_STYLE = """
  @page {
    size: A4;
    margin: 24mm 18mm 24mm 18mm;
    @bottom-left {
      content: string(reference);
      font-family: "RijksSans", Verdana, "DejaVu Sans", Arial, sans-serif;
      font-size: 8pt; color: #444;
    }
    @bottom-right {
      content: "pagina " counter(page) " van " counter(pages);
      font-family: "RijksSans", Verdana, "DejaVu Sans", Arial, sans-serif;
      font-size: 8pt; color: #444;
    }
  }
  @page :first { margin-top: __FIRST_TOP__; }
  * { box-sizing: border-box; }
  html { color-scheme: light; }
  body {
    font-family: "RijksSans", Verdana, "DejaVu Sans", Arial, sans-serif;
    font-size: 9.5pt; line-height: 1.45; color: #111; background: #fff; margin: 0;
  }
  h1 { font-size: 18pt; font-weight: normal; margin: 0 0 6mm; }
  h2 { font-size: 11pt; margin: 8mm 0 2mm; break-after: avoid; }
  p { margin: 0 0 2mm; }
  .quiet { color: #444; font-size: 8pt; }
  .reference { string-set: reference content(); }

  /* Head with the Rijkslint: the ribbon hangs from the top edge of the first
     page, centred; the name of the sender stands beside its lower half. */
  .ribbon-head { position: absolute; top: -40mm; left: 0; right: 0; height: 34mm; }
  .ribbon {
    position: absolute; top: 0; left: 50%; width: 11.5mm; margin-left: -5.75mm;
    height: 23mm; background: __BLUE__; overflow: hidden;
  }
  /* The mark is a square with the ribbon as its middle half; show that half,
     with the coat of arms at the foot of the ribbon. */
  .ribbon img { position: absolute; left: -5.75mm; bottom: -5.75mm; width: 23mm;
    height: 23mm; }
  .wordmark { position: absolute; left: 50%; margin-left: 9.25mm; top: 12.5mm;
    font-size: 9.5pt; line-height: 1.2; }
  .wordmark .sub { font-style: italic; }
  /* Plain head: the name of the organisation, nothing else. */
  .plain-head { border-bottom: 0.5pt solid #111; padding-bottom: 3mm;
    margin-bottom: 9mm; font-size: 10.5pt; line-height: 1.25; }
  .plain-head .name { font-weight: bold; }

  dl.letter { display: grid; grid-template-columns: 34mm 1fr; gap: 1mm 4mm;
    margin: 0 0 8mm; }
  dl.letter dt { color: #444; }
  dl.letter dd { margin: 0; }

  table { border-collapse: collapse; width: 100%; font-size: 8.5pt; }
  thead { display: table-header-group; }
  th, td { text-align: left; vertical-align: top; padding: 1.4mm 1.5mm;
    border-bottom: 0.4pt solid #999; font-weight: normal; }
  thead th { border-bottom: 0.9pt solid #111; font-weight: bold; }
  th:first-child, td:first-child { padding-left: 0; }
  th:last-child, td:last-child { padding-right: 0; }
  .num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .keep { white-space: nowrap; }
  tr { break-inside: avoid; }
  tr.subtotal th, tr.subtotal td { border-bottom: 0; }
  tr.has-rates th, tr.has-rates td { border-bottom: 0; padding-bottom: 0.4mm; }
  tr.has-rates { break-after: avoid; }
  tr.rates td { font-size: 7.5pt; color: #444; padding-top: 0;
    font-variant-numeric: tabular-nums; }
  tr.total th, tr.total td { font-weight: bold; border-top: 0.9pt solid #111;
    border-bottom: 0; }
  .note { margin-top: 2mm; }
  .conditions { white-space: pre-wrap; }

  .sign { break-inside: avoid; }
  .sign-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12mm;
    margin-top: 3mm; }
  .sign-grid div { border-bottom: 0.5pt solid #111; height: 13mm; padding-top: 1mm;
    color: #444; font-size: 8pt; }
  .colophon { margin-top: 8mm; padding-top: 2mm; border-top: 0.4pt solid #999;
    break-inside: avoid; }
  .colophon code { font-family: "DejaVu Sans Mono", Menlo, Consolas, monospace;
    font-size: 7pt; }

  /* The quote as a letter: the addressee on the left, the sender's details
     in a narrow column on the right, then the text over the full measure. */
  .letter-top { display: grid; grid-template-columns: 1fr 46mm; gap: 0 10mm;
    margin-bottom: 9mm; }
  .addressee { padding-top: 6mm; }
  .addressee div { line-height: 1.35; }
  .sender-column { font-size: 7pt; line-height: 1.5; }
  .sender-column .org { font-weight: bold; }
  .sender-column .group { margin-top: 2.5mm; }
  .sender-column .label { font-weight: bold; }
  h1.subject-title { font-size: 9.5pt; font-weight: bold; margin: 0 0 6mm; }
  .letter-body { max-width: 150mm; }
  .letter-body p { margin: 0 0 3mm; }
  .letter-body h2 { font-size: 9.5pt; margin: 6mm 0 2mm; break-after: avoid; }
  .letter-body h3 { font-size: 9.5pt; font-weight: bold; margin: 4mm 0 1.5mm;
    break-after: avoid; }
  .letter-body ul, .letter-body ol { margin: 0 0 3mm; padding-left: 5mm; }
  .letter-body li { margin: 0 0 1mm; break-inside: avoid; }
  .letter-body p { orphans: 2; widows: 2; }
  .letter-body table { margin-top: 2mm; break-before: avoid; }
  .letter-body h2 + p { break-before: avoid; }
  .closing { margin-top: 6mm; }
  .signatures { break-inside: avoid; margin-top: 8mm; }
  .signature-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12mm; }
  .signature-grid .space { height: 18mm; }
  .annex { break-before: page; }
  .annex table { margin: 2mm 0 6mm; max-width: 120mm; }
  .annex th, .annex td { border: 0.4pt solid #666; padding: 2mm; height: 9mm; }
  .annex th { width: 45%; font-weight: normal; }

  @media screen {
    body { background: #eee; padding: 8mm 4mm; }
    main { background: #fff; max-width: 210mm; margin: 0 auto;
      padding: 44mm 18mm 20mm; position: relative; }
    main.plain { padding-top: 20mm; }
    .ribbon-head { top: 0; }
  }
"""


def _head(sender: str, letterhead: Letterhead) -> str:
    lines = "".join(
        f'<div class="sub">{escape(line)}</div>' for line in letterhead.lines
    )
    if letterhead.ribbon_data_uri:
        return (
            '<div class="ribbon-head">'
            f'<div class="ribbon"><img src="{letterhead.ribbon_data_uri}" '
            'alt="Logo Rijksoverheid"></div>'
            f'<div class="wordmark"><div>{escape(sender)}</div>{lines}</div>'
            "</div>"
        )
    return (
        f'<div class="plain-head"><div class="name">{escape(sender)}</div>{lines}</div>'
    )


def cost_table(snapshot: dict[str, Any]) -> str:
    """The lines of the quote with subtotals, the total and the note on how
    the amounts were calculated."""
    lines = [line for line in snapshot.get("lines") or [] if isinstance(line, dict)]
    rows = "\n".join(_line_row(line) for line in lines)

    subtotals = [
        entry
        for entry in snapshot.get("subtotals_per_year") or []
        if isinstance(entry, dict)
    ]
    subtotal_rows = ""
    if len(subtotals) > 1:
        subtotal_rows = "\n".join(
            '<tr class="subtotal">'
            f'<th scope="row" colspan="5">Subtotaal {escape(str(entry.get("year")))}'
            f'</th><td class="num">'
            f"{escape(format_euro(_cents(entry.get('amount'))))}</td></tr>"
            for entry in subtotals
        )
    total = escape(format_euro(_cents(snapshot.get("total"))))
    note = (
        "Bedragen zijn berekend per kalendermaand, tegen het tarief dat in die "
        "maand geldt." + part_month_note(lines) + rate_change_note(lines)
    )
    return f"""<table>
<thead>
<tr>
<th scope="col">Omschrijving</th>
<th scope="col" class="num">FTE</th>
<th scope="col">Periode</th>
<th scope="col">Schaal</th>
<th scope="col" class="num">Maandtarief</th>
<th scope="col" class="num">Bedrag</th>
</tr>
</thead>
<tbody>
{rows}
{subtotal_rows}
<tr class="total"><th scope="row" colspan="5">Totaal</th>
<td class="num">{total}</td></tr>
</tbody>
</table>
<p class="quiet note">{escape(note)}</p>"""


def document_title(snapshot: dict[str, Any], context: QuoteDocumentContext) -> str:
    reference = snapshot.get("reference") or context.reference
    name = str(snapshot.get("name") or "")
    return f"Offerte {reference} {name}".strip() if reference else f"Offerte {name}"


def render_quote_html(snapshot: dict[str, Any], context: QuoteDocumentContext) -> str:
    """The quote as one self-contained HTML page.

    Every value from the content is escaped. Nothing is loaded from outside
    the page except the configured typeface: no scripts, no remote images.
    """
    if isinstance(snapshot.get("letter"), dict):
        return render_letter_html(snapshot, context)
    letterhead = context.letterhead
    ribbon = letterhead.ribbon_data_uri is not None
    sender = str(snapshot.get("sender") or context.contractor_name)
    reference = str(snapshot.get("reference") or context.reference or "")
    name = escape(str(snapshot.get("name") or ""))
    facts: list[tuple[str, str]] = []
    if context.client_name:
        to = escape(context.client_name)
        if context.client_contact:
            to += f"<br>{escape(context.client_contact)}"
        facts.append(("Aan", to))
    facts.append(("Datum", escape(format_date(context.issued_at.date()))))
    if reference:
        facts.append(("Kenmerk", f'<span class="reference">{escape(reference)}</span>'))
    if snapshot.get("client_reference"):
        facts.append(("Uw kenmerk", escape(str(snapshot["client_reference"]))))
    facts.append(("Betreft", name))
    if snapshot.get("valid_until"):
        facts.append(("Geldig tot en met", escape(_iso_date(snapshot["valid_until"]))))
    letter = "\n".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in facts)

    conditions = ""
    if snapshot.get("conditions"):
        conditions = (
            "<h2>Voorwaarden</h2>\n"
            f'<p class="conditions">{escape(str(snapshot["conditions"]))}</p>'
        )
    client = escape(context.client_name or "de opdrachtgever")
    issued = context.issued_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    style = (
        _STYLE.replace("__FIRST_TOP__", "40mm" if ribbon else "24mm")
        .replace("__BLUE__", RIBBON_BLUE)
        .strip()
    )
    title = escape(document_title(snapshot, context))
    code = escape(" ".join(code_lines(context.snapshot_hash)))
    return f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="author" content="{escape(sender)}">
<meta name="dcterms.created" content="{issued}">
<meta name="dcterms.modified" content="{issued}">
<style>
{_font_faces(letterhead)}
{style}
</style>
</head>
<body>
<main class="{"ribboned" if ribbon else "plain"}">
{_head(sender, letterhead)}
<h1>Offerte</h1>
<dl class="letter">
{letter}
</dl>

{cost_table(snapshot)}

{conditions}

<div class="sign">
<h2>Akkoord</h2>
<p>Voor akkoord namens {client}:</p>
<div class="sign-grid">
<div>Naam</div><div>Datum</div>
<div>Functie</div><div>Handtekening</div>
</div>
</div>

<div class="colophon quiet">
<p>Echtheidskenmerk: <code>{code}</code><br>
Een code die uit de inhoud van deze offerte is berekend. Dezelfde code staat in het
akkoord, zodat vaststaat dat er voor precies deze offerte is getekend.
Adres voor systemen: {escape(context.quote_uri)}</p>
</div>
</main>
</body>
</html>
"""


def _letter_head(details: dict[str, Any], sender: str, letterhead: Letterhead) -> str:
    """The head of a letter: the ribbon with what the sender is part of beside
    it, as the Rijkshuisstijl sets a letter of an organisation of a ministry."""
    part_of = [str(line) for line in details.get("part_of") or []] or list(
        letterhead.lines
    )
    name = part_of[0] if part_of else str(details.get("organisation") or sender)
    rest = "".join(f'<div class="sub">{escape(line)}</div>' for line in part_of[1:])
    if letterhead.ribbon_data_uri:
        return (
            '<div class="ribbon-head">'
            f'<div class="ribbon"><img src="{letterhead.ribbon_data_uri}" '
            'alt="Logo Rijksoverheid"></div>'
            f'<div class="wordmark"><div>{escape(name)}</div>{rest}</div>'
            "</div>"
        )
    return f'<div class="plain-head"><div class="name">{escape(name)}</div>{rest}</div>'


def _sender_column(
    details: dict[str, Any], sender: str, facts: list[tuple[str, str]]
) -> str:
    organisation = str(details.get("organisation") or sender)
    parts = [f'<div class="org">{escape(organisation)}</div>']
    if details.get("unit"):
        parts.append(f"<div>{escape(str(details['unit']))}</div>")
    for field_name in ("visiting_address", "postal_address"):
        lines = [str(line) for line in details.get(field_name) or []]
        if lines:
            parts.append(
                '<div class="group">'
                + "".join(f"<div>{escape(line)}</div>" for line in lines)
                + "</div>"
            )
    if details.get("website"):
        parts.append(f'<div class="group">{escape(str(details["website"]))}</div>')
    for label, value in facts:
        parts.append(
            f'<div class="group"><div class="label">{escape(label)}</div>'
            f"<div>{value}</div></div>"
        )
    return '<div class="sender-column">' + "".join(parts) + "</div>"


def _signature_block(signature: dict[str, Any]) -> str:
    on_behalf_of = str(signature.get("on_behalf_of") or "")
    lines = [
        f"<div>namens {escape(on_behalf_of)},</div>" if on_behalf_of else "<div></div>",
        '<div class="space"></div>',
    ]
    for field_name in ("name", "function", "organisation"):
        value = str(signature.get(field_name) or "")
        if value:
            lines.append(f"<div>{escape(value)}</div>")
    return "<div>" + "".join(lines) + "</div>"


_BILLING_ANNEX = """<section class="annex">
<h2>Factuurinformatie</h2>
<p>Uw factuuradres:</p>
<table>
<tbody>
<tr><th scope="row">Organisatie</th><td></td></tr>
<tr><th scope="row">Ten name van</th><td></td></tr>
<tr><th scope="row">Adres of postbus</th><td></td></tr>
<tr><th scope="row">Postcode en plaats</th><td></td></tr>
<tr><th scope="row">Een kenmerk, verplichtingennummer of vorderingsnummer dat wij
op de factuur kunnen vermelden</th><td></td></tr>
</tbody>
</table>
<p>Contactpersoon financiële afdeling:</p>
<table>
<tbody>
<tr><th scope="row">Naam</th><td></td></tr>
<tr><th scope="row">Telefoonnummer</th><td></td></tr>
<tr><th scope="row">E-mail</th><td></td></tr>
</tbody>
</table>
</section>"""


def render_letter_html(snapshot: dict[str, Any], context: QuoteDocumentContext) -> str:
    """A quote with text, laid out as a letter in the Rijkshuisstijl.

    The order follows the letter an organisation of the Rijk sends: the
    addressee and the sender's details, date and reference, subject,
    salutation, the numbered sections with the amounts where the quote puts
    them, the closing, the signatures of both parties, and the annex for
    the billing details. Every value is escaped; the text of a section is
    turned into paragraphs and lists by ``quote_prose``.
    """
    from grip.services import quote_prose

    letter = snapshot["letter"]
    letterhead = context.letterhead
    ribbon = letterhead.ribbon_data_uri is not None
    sender = str(snapshot.get("sender") or context.contractor_name)
    details = letter.get("sender_details") or {}
    reference = str(snapshot.get("reference") or context.reference or "")

    facts: list[tuple[str, str]] = [
        ("Datum", escape(format_date(context.issued_at.date())))
    ]
    if reference:
        facts.append(("Kenmerk", f'<span class="reference">{escape(reference)}</span>'))
    if snapshot.get("client_reference"):
        facts.append(("Uw kenmerk", escape(str(snapshot["client_reference"]))))
    if snapshot.get("valid_until"):
        facts.append(("Geldig tot en met", escape(_iso_date(snapshot["valid_until"]))))

    addressee = [str(line) for line in letter.get("addressee") or []]
    if not addressee and context.client_name:
        addressee = [context.client_name]
    addressee_html = "".join(f"<div>{escape(line)}</div>" for line in addressee)
    subject = escape(str(letter.get("subject") or snapshot.get("name") or ""))

    body: list[str] = []
    if letter.get("salutation"):
        body.append(f"<p>{escape(str(letter['salutation']))}</p>")
    if letter.get("opening"):
        body.append(quote_prose.to_html(str(letter["opening"])))
    number = 0
    costs_placed = False
    for section in letter.get("sections") or []:
        heading = escape(str(section.get("heading") or ""))
        if section.get("numbered", True):
            number += 1
            heading = f"{number}. {heading}"
        body.append(f"<h2>{heading}</h2>")
        if section.get("body"):
            body.append(quote_prose.to_html(str(section["body"])))
        if section.get("with_costs"):
            body.append(cost_table(snapshot))
            costs_placed = True
    if not costs_placed:
        number += 1
        body.append(f"<h2>{number}. Kosten</h2>")
        body.append(cost_table(snapshot))
    if snapshot.get("conditions"):
        number += 1
        body.append(f"<h2>{number}. Voorwaarden</h2>")
        body.append(f'<p class="conditions">{escape(str(snapshot["conditions"]))}</p>')
    if letter.get("closing"):
        body.append(
            '<div class="closing">'
            + quote_prose.to_html(str(letter["closing"]))
            + "</div>"
        )

    signatures = [
        entry for entry in letter.get("signatures") or [] if isinstance(entry, dict)
    ]
    signature_html = ""
    if signatures:
        signature_html = (
            '<div class="signatures"><p>Voor akkoord</p><div class="signature-grid">'
            + "".join(_signature_block(entry) for entry in signatures[:2])
            + "</div></div>"
        )
    annex = _BILLING_ANNEX if letter.get("billing_annex") else ""

    issued = context.issued_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    style = (
        _STYLE.replace("__FIRST_TOP__", "40mm" if ribbon else "24mm")
        .replace("__BLUE__", RIBBON_BLUE)
        .strip()
    )
    title = escape(document_title(snapshot, context))
    code = escape(" ".join(code_lines(context.snapshot_hash)))
    return f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="author" content="{escape(sender)}">
<meta name="dcterms.created" content="{issued}">
<meta name="dcterms.modified" content="{issued}">
<style>
{_font_faces(letterhead)}
{style}
</style>
</head>
<body>
<main class="{"ribboned" if ribbon else "plain"}">
{_letter_head(details, sender, letterhead)}
<div class="letter-top">
<div class="addressee">{addressee_html}</div>
{_sender_column(details, sender, facts)}
</div>
<h1 class="subject-title">{subject}</h1>
<div class="letter-body">
{chr(10).join(body)}
{signature_html}
</div>

<div class="colophon quiet">
<p>Echtheidskenmerk: <code>{code}</code><br>
Een code die uit de inhoud van deze offerte is berekend. Dezelfde code staat in het
akkoord, zodat vaststaat dat er voor precies deze offerte is getekend.
Adres voor systemen: {escape(context.quote_uri)}</p>
</div>
{annex}
</main>
</body>
</html>
"""


# -- PDF ----------------------------------------------------------------------

_library_lookup_patched = False
_render_lock = threading.Lock()


def _find_homebrew_libraries() -> None:
    """Let the PDF engine find its libraries on a Mac with Homebrew.

    The engine loads pango and friends by name. On macOS a process only
    looks in Homebrew's directory when an environment variable was set
    before it started, which a development server usually was not. This
    adds that directory to the lookup the loader falls back on. It does
    nothing on Linux, where the libraries are on the normal path.
    """
    global _library_lookup_patched
    if _library_lookup_patched or sys.platform != "darwin":
        return
    _library_lookup_patched = True
    original = ctypes.util.find_library

    def find_library(name: str) -> str | None:
        found = original(name)
        if found:
            return found
        stem = name[3:] if name.startswith("lib") else name
        for directory in ("/opt/homebrew/lib", "/usr/local/lib"):
            for candidate in (
                f"lib{stem}.dylib",
                f"lib{stem.rsplit('-', 1)[0]}.dylib",
            ):
                path = os.path.join(directory, candidate)
                if os.path.exists(path):
                    return path
        return None

    ctypes.util.find_library = find_library


def render_quote_pdf(snapshot: dict[str, Any], context: QuoteDocumentContext) -> bytes:
    """The quote as a tagged PDF (PDF/UA), from the same template as the page.

    The same quote gives the same bytes: the dates in the file are the
    moment of issue and its identifier comes from the echtheidskenmerk.
    """
    _find_homebrew_libraries()
    try:
        from weasyprint import HTML
    except (OSError, ImportError) as exc:
        raise DocumentEngineError() from exc
    html = render_quote_html(snapshot, context)
    # An embedded typeface is written with "now" as its modification time
    # unless this variable says otherwise; with it the file is the same on
    # every run. The variable belongs to the process, hence the lock.
    with _render_lock:
        previous = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = str(int(context.issued_at.timestamp()))
        try:
            pdf: bytes = HTML(string=html, base_url=None).write_pdf(
                pdf_variant="pdf/ua-1",
                pdf_identifier=context.snapshot_hash.encode("ascii")[:32],
            )
        finally:
            if previous is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = previous
    return pdf
