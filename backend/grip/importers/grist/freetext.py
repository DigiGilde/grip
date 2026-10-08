"""Turn free text from the Grist document into proposed fields.

Two kinds of text hide data in the document: the note on a team member
("Schaal 11, maar rekent met 12") and the description of a budget line
("Developer #2 (vanaf Q2, schaal 10/11)"). The parsers here only propose.
Every proposal carries a confidence and the original text, goes onto the
confirmation list, and is applied only after a person has confirmed it.
Text that cannot be read stays text, with a flag.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

HIGH = "hoog"
MEDIUM = "middel"
LOW = "laag"

PERSONNEL = "personnel"
FIXED = "fixed"

_MONTHS = {
    "januari": 1,
    "jan": 1,
    "februari": 2,
    "feb": 2,
    "maart": 3,
    "mrt": 3,
    "april": 4,
    "apr": 4,
    "mei": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "augustus": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_BAND = re.compile(r"schaal\s*(?P<low>\d{1,2})\s*/\s*(?P<high>\d{1,2})", re.I)
_SINGLE = re.compile(r"schaal\s*(?P<scale>\d{1,2})(?!\s*/|\d)", re.I)
_BILLS_AT = re.compile(r"reken(?:t|en)?\s+met\s+(?:schaal\s*)?(?P<scale>\d{1,2})", re.I)
_UNSURE = re.compile(r"(niet\s+(?:100\s*%\s+)?zeker|onbekend|\?)", re.I)
_FTE = re.compile(r"(?P<fte>\d+(?:[.,]\d+)?)\s*fte\b", re.I)
_PCT_FTE = re.compile(r"(?P<pct>\d{1,3})\s*%", re.I)
_FROM_QUARTER = re.compile(r"(?:vanaf\s+)?\bQ(?P<q>[1-4])\b", re.I)
_UNTIL_QUARTER = re.compile(r"(?:t/m|tot en met|tot)\s+Q(?P<q>[1-4])\b", re.I)
_FROM_MONTH = re.compile(
    rf"(?:vanaf|start(?:\s+per)?|per)\s+(?:(?P<day>\d{{1,2}})\s+)?(?P<month>{_MONTH_ALT})\b",
    re.I,
)
_UNTIL_MONTH = re.compile(
    rf"(?:t/m|tot en met|tot)\s+(?:(?P<day>\d{{1,2}})\s+)?(?P<month>{_MONTH_ALT})\b",
    re.I,
)
_AMOUNT_K = re.compile(r"(?<![\w.,])(?P<n>\d+(?:[.,]\d+)?)\s*k\b", re.I)
_AMOUNT_EURO = re.compile(r"€\s*(?P<n>\d[\d.]*(?:,\d{1,2})?)")
_FIXED_WORD = re.compile(r"\bstelpost\b", re.I)
_YEAR_SUFFIX = re.compile(r"^(?P<base>.+?)[\s\-_]+(?P<year>20\d{2})\s*$")


@dataclass(frozen=True)
class ScaleProposal:
    source: str
    billing_scale: int | None
    valid_from: date | None
    confidence: str
    remarks: tuple[str, ...] = ()

    @property
    def parsed(self) -> bool:
        return self.billing_scale is not None


@dataclass(frozen=True)
class LineProposal:
    source: str
    kind: str
    confidence: str
    role: str | None = None
    fte: Decimal | None = None
    scale_low: int | None = None
    scale_high: int | None = None
    rate_category: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount_cents: int | None = None
    year: int | None = None
    remarks: tuple[str, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        """Whether the proposal has every field its kind of line needs."""
        if self.kind == PERSONNEL:
            return None not in (
                self.fte,
                self.rate_category,
                self.start_date,
                self.end_date,
            )
        return self.amount_cents is not None and self.year is not None


def assignment_year(name: str) -> tuple[str, int | None]:
    """Split "Opdracht Alfa 2026" into the base name and the year."""
    match = _YEAR_SUFFIX.match(name.strip())
    if match is None:
        return name.strip(), None
    return match.group("base").strip(), int(match.group("year"))


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _month_start(year: int, month: int, day: int | None = None) -> date:
    return date(year, month, min(day or 1, calendar.monthrange(year, month)[1]))


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_amount_cents(text: str) -> int | None:
    """An amount written into text: "60k" or "€ 5.000"."""
    if match := _AMOUNT_K.search(text):
        value = _decimal(match.group("n"))
        return None if value is None else int(value * 1000 * 100)
    if match := _AMOUNT_EURO.search(text):
        value = _decimal(match.group("n").replace(".", ""))
        return None if value is None else int((value * 100).to_integral_value())
    return None


def parse_scale_note(
    note: str | None, scale_column: int | None, year: int
) -> ScaleProposal:
    """Propose the billing scale of a person from the scale column and note.

    The salary scale is never proposed for storage: grip keeps only the
    scale a person bills at (ADR 0014).
    """
    text = (note or "").strip()
    remarks: list[str] = []
    valid_from = date(year, 1, 1)

    if match := _FROM_MONTH.search(text):
        valid_from = _month_start(
            year, _MONTHS[match.group("month").lower()], int(match.group("day") or 1)
        )
        remarks.append("Begindatum uit de notitie gelezen.")

    bills_at = _BILLS_AT.search(text)
    singles = [int(m.group("scale")) for m in _SINGLE.finditer(text)]
    band = _BAND.search(text)
    unsure = bool(_UNSURE.search(text))

    if bills_at:
        billing = int(bills_at.group("scale"))
        others = sorted({s for s in [*singles, scale_column] if s and s != billing})
        if others:
            remarks.append(
                f"De notitie noemt ook schaal {', '.join(map(str, others))}; die "
                "wordt niet opgeslagen."
            )
        confidence = LOW if unsure else HIGH
        if unsure:
            remarks.append("De notitie drukt twijfel uit.")
        return ScaleProposal(text, billing, valid_from, confidence, tuple(remarks))

    if band:
        low, high = int(band.group("low")), int(band.group("high"))
        remarks.append(
            f"De notitie noemt een bereik ({low}/{high}); de laagste is voorgesteld."
        )
        return ScaleProposal(text, low, valid_from, LOW, tuple(remarks))

    distinct = sorted(set(singles))
    if len(distinct) > 1:
        remarks.append(
            f"De notitie noemt meerdere schalen ({', '.join(map(str, distinct))}) "
            "zonder te zeggen waarmee wordt gerekend."
        )
        proposal = scale_column if scale_column in distinct else distinct[-1]
        return ScaleProposal(text, proposal, valid_from, LOW, tuple(remarks))

    if len(distinct) == 1:
        billing = distinct[0]
        if scale_column and scale_column != billing:
            remarks.append(
                f"De kolom zegt schaal {scale_column}, de notitie schaal {billing}; "
                "de notitie is voorgesteld."
            )
            return ScaleProposal(text, billing, valid_from, MEDIUM, tuple(remarks))
        confidence = LOW if unsure else HIGH
        if unsure:
            remarks.append("De notitie drukt twijfel uit.")
        return ScaleProposal(text, billing, valid_from, confidence, tuple(remarks))

    if scale_column:
        if unsure:
            remarks.append("De notitie drukt twijfel uit.")
            return ScaleProposal(text, scale_column, valid_from, LOW, tuple(remarks))
        if text:
            remarks.append("De notitie noemt geen schaal; de kolom is voorgesteld.")
            return ScaleProposal(text, scale_column, valid_from, MEDIUM, tuple(remarks))
        return ScaleProposal(text, scale_column, valid_from, HIGH, ("Uit de kolom.",))

    remarks.append("Geen schaal gevonden in kolom of notitie.")
    return ScaleProposal(text, None, None, LOW, tuple(remarks))


def _strip_role(text: str) -> str:
    without = re.sub(r"\([^)]*\)", " ", text)
    without = _AMOUNT_K.sub(" ", _AMOUNT_EURO.sub(" ", without))
    without = _FIXED_WORD.sub(" ", without)
    return re.sub(r"\s+", " ", without).strip(" ,-:")


def parse_budget_line(
    description: str,
    *,
    year: int,
    budgeted_cents: int | None,
    scale_to_category: dict[int, str],
    column_fte: Decimal | None = None,
    column_scale: int | None = None,
    column_start: date | None = None,
    column_end: date | None = None,
    column_is_person: bool | None = None,
) -> LineProposal:
    """Propose the fields of a budget line from its description.

    Structured columns, when the document has them, win over the text.
    """
    text = (description or "").strip()
    remarks: list[str] = []
    assumed = False

    band = _BAND.search(text)
    single = _SINGLE.search(text)
    low = high = None
    if column_scale:
        low = high = column_scale
    elif band:
        low, high = int(band.group("low")), int(band.group("high"))
    elif single:
        low = high = int(single.group("scale"))

    fte = column_fte
    if fte is None and (match := _FTE.search(text)):
        fte = _decimal(match.group("fte"))
    if fte is None and (match := _PCT_FTE.search(text)):
        pct = _decimal(match.group("pct"))
        if pct is not None and 0 < pct <= 100:
            fte = pct / 100
            remarks.append("Omvang gelezen uit een percentage.")

    fixed_word = bool(_FIXED_WORD.search(text))
    text_amount = parse_amount_cents(text)

    if column_is_person is not None:
        is_personnel = column_is_person
    else:
        is_personnel = (low is not None or fte is not None) and not fixed_word

    if not is_personnel:
        amount = budgeted_cents if budgeted_cents is not None else text_amount
        if (
            budgeted_cents is not None
            and text_amount is not None
            and abs(budgeted_cents - text_amount) >= 100
        ):
            remarks.append(
                "Het bedrag in de omschrijving wijkt af van de kolom Begroot; de "
                "kolom is voorgesteld."
            )
        if amount is None:
            remarks.append("Geen bedrag gevonden.")
            return LineProposal(text, FIXED, LOW, year=year, remarks=tuple(remarks))
        confidence = HIGH if (fixed_word or text_amount is not None) else MEDIUM
        if confidence == MEDIUM:
            remarks.append(
                "Geen rol, schaal of FTE in de omschrijving; als vaste post "
                "voorgesteld."
            )
        return LineProposal(
            text,
            FIXED,
            confidence,
            amount_cents=amount,
            year=year,
            remarks=tuple(remarks),
        )

    # A personnel line.
    start = column_start
    if start is None:
        if match := _FROM_MONTH.search(text):
            start = _month_start(
                year,
                _MONTHS[match.group("month").lower()],
                int(match.group("day") or 1),
            )
        elif match := _FROM_QUARTER.search(text):
            start = date(year, (int(match.group("q")) - 1) * 3 + 1, 1)
    if start is None:
        start = date(year, 1, 1)
    end = column_end
    if end is None:
        if match := _UNTIL_MONTH.search(text):
            end = _month_end(year, _MONTHS[match.group("month").lower()])
        elif match := _UNTIL_QUARTER.search(text):
            end = _month_end(year, int(match.group("q")) * 3)
    if end is None:
        end = date(year, 12, 31)

    if fte is None:
        fte = Decimal(1)
        assumed = True
        remarks.append("Geen FTE genoemd; 1 FTE aangenomen.")

    category = None
    if low is None:
        remarks.append("Geen schaal genoemd; de tariefcategorie is niet te bepalen.")
    else:
        category = scale_to_category.get(low)
        upper = scale_to_category.get(high) if high is not None else category
        if category is None:
            remarks.append(f"Schaal {low} staat niet in de tarievenkaart.")
        elif upper is not None and upper != category:
            remarks.append(
                f"Schaal {low} en {high} vallen in verschillende categorieën "
                f"({category} en {upper}); de laagste is voorgesteld."
            )
            assumed = True

    role = _strip_role(text) or None
    if category is None:
        confidence = LOW
    elif assumed:
        confidence = MEDIUM
    else:
        confidence = HIGH
    return LineProposal(
        source=text,
        kind=PERSONNEL,
        confidence=confidence,
        role=role,
        fte=fte,
        scale_low=low,
        scale_high=high,
        rate_category=category,
        start_date=start,
        end_date=end,
        remarks=tuple(remarks),
    )
