"""Dutch names for the codes that appear in printed reports."""

from __future__ import annotations

from datetime import date

ASSIGNMENT_STATUS_LABELS: dict[str, str] = {
    "draft": "In voorbereiding",
    "requested": "Aangevraagd",
    "quoted": "Offerte gemaakt",
    "verbally_agreed": "Mondeling akkoord",
    "accepted": "Akkoord",
    "in_progress": "In uitvoering",
    "completed": "Afgerond",
    "accounted": "Verantwoord",
    "rejected": "Offerte afgewezen",
    "cancelled": "Geannuleerd",
}

ASSIGNMENT_KIND_LABELS: dict[str, str] = {
    "external": "Extern",
    "internal": "Intern",
}

ACCEPTANCE_FORM_LABELS: dict[str, str] = {
    "own_instance": "Akkoord in de eigen omgeving van de opdrachtgever",
    "signing_link": "Akkoord via een tekenlink",
    "uploaded_pdf": "Getekend document",
}

MONTH_NAMES: tuple[str, ...] = (
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

MONTH_NAMES_SHORT: tuple[str, ...] = (
    "jan",
    "feb",
    "mrt",
    "apr",
    "mei",
    "jun",
    "jul",
    "aug",
    "sep",
    "okt",
    "nov",
    "dec",
)


def day(value: date) -> str:
    """A date in a sentence: "3 mrt 2026"."""
    return f"{value.day} {MONTH_NAMES_SHORT[value.month - 1]} {value.year}"


def status_label(status: str | None) -> str:
    if not status:
        return ""
    return ASSIGNMENT_STATUS_LABELS.get(status, status)
