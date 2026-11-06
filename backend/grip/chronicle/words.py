"""A fact in words, in the form the fact has.

Not "the quote is signed" but who established what: someone who records that
a client signed is another sentence than someone who signs. Nothing here
decides what may be seen; a route gives these words to who may read the
values of a fact (class B), and the title of the fact to who may only know it
happened.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any

from grip.chronicle.facts import received_from, title_of
from grip.core import clock
from grip.events.words import FIELD_LABELS
from grip.models.assignment import line_display_name
from grip.services.reports.labels import MONTH_NAMES

Fields = Mapping[str, Any]


def day_words(value: date | datetime | str | None) -> str | None:
    """A day on the calendar of the instance: "3 november 2026"."""
    if value is None:
        return None
    if isinstance(value, str):
        value = (
            datetime.fromisoformat(value)
            if len(value) > 10
            else date.fromisoformat(value)
        )
    if isinstance(value, datetime):
        value = clock.local_date(value)
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def euro_words(cents: int) -> str:
    whole, fraction = divmod(abs(cents), 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"€ {grouped}" if fraction == 0 else f"€ {grouped},{fraction:02d}"


def _organisation(values: Fields | None, fallback: str = "de opdrachtgever") -> str:
    name = (values or {}).get("name")
    return str(name) if name else fallback


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _accepted(fields: Fields, actor: str | None) -> str:
    acceptance = fields["acceptance"]
    signer = acceptance.get("signer_name") or "De opdrachtgever"
    on = day_words(acceptance.get("signed_at"))
    organisation = _organisation(acceptance.get("organisation"))
    if fields.get("received"):
        return f"Ontvangen van {organisation}: {signer} tekende op {on}."
    if acceptance.get("form") == "uploaded_pdf":
        who = actor or "Een medewerker"
        return f"{who} legde vast dat {signer} op {on} tekende, met een getekende pdf."
    if acceptance.get("form") == "signing_link":
        if fields.get("declared_mandate"):
            return (
                f"{signer} tekende via de tekenlink en verklaarde namens "
                f"{organisation} te mogen tekenen."
            )
        return f"{signer} tekende via de tekenlink."
    return f"{signer} tekende namens {organisation}."


def _rejected(fields: Fields, actor: str | None) -> str:
    rejection = fields["rejection"]
    organisation = _organisation(rejection.get("organisation"))
    if fields.get("received"):
        return f"Ontvangen van {organisation}: de offerte is afgewezen."
    if rejection.get("recorded_by_id"):
        who = actor or "Een medewerker"
        return f"{who} legde vast dat {organisation} de offerte afwees."
    return f"{_capital(organisation)} wees de offerte af."


def _offered(fields: Fields, actor: str | None) -> str:
    offer = fields["offer"]
    channel = offer.get("channel")
    if channel == "signing_link":
        recipient = offer.get("recipient")
        if recipient is None:
            return "Offerte aangeboden met een tekenlink."
        return f"Offerte aangeboden met een tekenlink aan {recipient}."
    if channel == "client_instance":
        return "Offerte aangeboden in de eigen omgeving van de opdrachtgever."
    return "Offerte aangeboden als document."


def _issued(fields: Fields, actor: str | None) -> str:
    quote = fields["quote"]
    named = f"Offerte {quote['reference']}" if quote.get("reference") else "Offerte"
    return f"{named} gemaakt, {euro_words(int(quote['total_cents']))}."


def _received(fields: Fields, actor: str | None) -> str:
    quote = fields["quote"]
    named = f"Offerte {quote['reference']}" if quote.get("reference") else "Offerte"
    sender = received_from(fields)
    source = f" van {sender}" if sender else ""
    return f"{named} ontvangen{source}, {euro_words(int(quote['total_cents']))}."


def _line_added(fields: Fields, actor: str | None) -> str:
    line = fields["line"]
    name = line_display_name(line.get("role"), line.get("detail"))
    return (
        f"Begrotingsregel {name} toegevoegd." if name else "Begrotingsregel toegevoegd."
    )


def _line_named(verb: str) -> Callable[[Fields, str | None], str]:
    def told(fields: Fields, actor: str | None) -> str:
        name = str(fields.get("name") or "").strip()
        return f"Begrotingsregel {name} {verb}." if name else f"Begrotingsregel {verb}."

    return told


def _assignment_changed(fields: Fields, actor: str | None) -> str:
    changed = fields.get("changes") or {}
    # In the order of the labels: a stored fact keeps no order of its keys.
    named = [label.lower() for key, label in FIELD_LABELS.items() if key in changed]
    if not named or len(named) < len(changed):
        # Naming only part of what changed would say less than what happened.
        return f"{title_of('assignment_changed', fields)}."
    what = f"{', '.join(named[:-1])} en {named[-1]}" if named[1:] else named[0]
    return f"{_capital(what)} van de opdracht gewijzigd."


def _corrected(fields: Fields, actor: str | None) -> str:
    who = actor or "Een medewerker"
    was, now = day_words(fields.get("was")), day_words(fields.get("signed_at"))
    return f"{who} corrigeerde de datum van tekenen van {was} naar {now}."


def _approved(fields: Fields, actor: str | None) -> str:
    if not fields.get("self_approved"):
        return "Offerte intern goedgekeurd."
    if fields.get("asked_it"):
        return "Offerte intern goedgekeurd door wie de goedkeuring zelf vroeg."
    return "Offerte intern goedgekeurd door wie haar maakte."


_STATEMENTS = {
    "quote_issued": _issued,
    "quote_received": _received,
    "quote_offered": _offered,
    "quote_accepted": _accepted,
    "quote_rejected": _rejected,
    "acceptance_date_corrected": _corrected,
    "budget_line_added": _line_added,
    "budget_line_changed": _line_named("gewijzigd"),
    "budget_line_removed": _line_named("verwijderd"),
    "assignment_changed": _assignment_changed,
    "approval_approved": _approved,
}


def statement(fact: str, fields: Fields | None, *, actor: str | None) -> str:
    """The fact as one sentence, in the form it was established."""
    if fields is not None and fact in _STATEMENTS:
        return _STATEMENTS[fact](fields, actor)
    title = title_of(fact, fields)
    # A title can end in the name of an organisation: "Voorbeeld B.V.".
    return title if title.endswith(".") else f"{title}."


# Where the free words of a fact are, when no row of the stand draws them: the
# notes of an approval and the reason of a rejection stand on their own row.
_NOTES: dict[str, tuple[str, ...]] = {
    "assignment_status_changed": ("reason",),
    "acceptance_date_corrected": ("reason",),
}


def lines(fact: str, fields: Fields | None) -> tuple[str, ...]:
    """What was written down with the fact, in the words of who wrote it."""
    if fields is None:
        return ()
    found = [fields.get(name) for name in _NOTES.get(fact, ())]
    return tuple(str(text) for text in found if text)
