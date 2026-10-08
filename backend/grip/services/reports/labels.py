"""Dutch names for the codes that appear in printed reports."""

from __future__ import annotations

ASSIGNMENT_STATUS_LABELS: dict[str, str] = {
    "draft": "In voorbereiding",
    "requested": "Aangevraagd",
    "quoted": "Offerte gemaakt",
    "verbally_agreed": "Mondeling akkoord",
    "accepted": "Akkoord",
    "in_progress": "In uitvoering",
    "completed": "Afgerond",
    "accounted": "Verantwoord",
    "rejected": "Afgewezen",
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


def status_label(status: str | None) -> str:
    if not status:
        return ""
    return ASSIGNMENT_STATUS_LABELS.get(status, status)
