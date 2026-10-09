"""An event in words, for people.

The stream speaks in kinds, fields and code values; a reader gets Dutch:
what happened to what, and from what to what when that may be seen. This is
the one place where an event is put into words, so a screen never shows a
code name. A field without a Dutch name is left out, and so is a code value
without a label: the line then says only that the field changed.

Nothing here decides what may be seen. It is given the changes as the
reader may see them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Protocol

from grip.services.reports.labels import (
    ACCEPTANCE_FORM_LABELS,
    ASSIGNMENT_KIND_LABELS,
    ASSIGNMENT_STATUS_LABELS,
    MONTH_NAMES,
)

KIND_LABELS: dict[str, str] = {
    "assignment": "Opdracht",
    "assignment_request": "Aanvraag",
    "assignment_role": "Rol op de opdracht",
    "task": "Taak",
    "budget_line": "Begrotingsregel",
    "budget_usage_requested": "Inzage in het budget",
    "quote": "Offerte",
    "quote_draft": "Concept van de offerte",
    "quote_offer": "Aanbieding van de offerte",
    "quote_invitation": "Uitnodiging om te tekenen",
    "quote_acceptance": "Akkoord op de offerte",
    "quote_rejection": "Afwijzing van de offerte",
    "quote_approval": "Interne goedkeuring",
    "decision_evidence": "Bewijs van het besluit",
    "mail_outbox": "Uitgaande mail",
    "final_report": "Eindrapport",
    "final_report_received": "Ontvangen eindrapport",
    "month_close": "Maandafsluiting",
    "billing_export": "Factuurgegevens",
    "billing_correction": "Correctie op factuurgegevens",
    "outgoing_invoice": "Factuur",
    "invoice_line": "Factuurregel",
    "invoice_attachment": "Bijlage bij de factuur",
    "cost_item": "Kostenpost",
    "cost_coverage": "Dekking van de kosten",
    "allocation": "Inzet",
    "person": "Persoon",
    "person_standing": "Dienstverband",
    "person_role": "Recht in grip",
    "person_roles": "Rollen",
    "colleague_proposal": "Voorstel voor een collega",
    "person_scale": "Schaal",
    "hire": "Inhuur",
    "billability_target": "Norm voor declarabiliteit",
    "vacancy": "Vacature",
    "vacancy_text": "Vacaturetekst",
    "vacancy_step": "Stap van de procedure",
    "vacancy_decision": "Advies of akkoord",
    "vacancy_recruitment_ref": "Verwijzing naar de werving",
    "vacancy_offer_received": "Aangeboden kandidaat",
    "vacancy_hire": "Invulling van de vacature",
    "rate_card": "Tarievenkaart",
    "rate_band": "Tarief",
    "scale_band": "Indeling van een schaal",
    "organisation": "Organisatie",
    "organisation_sync": "Ophalen van organisaties",
    "catalogue_role": "Rol",
    "catalogue_role_sync": "Ophalen van rollen",
    "function_framework": "Functiegebouw",
    "function_family": "Functiefamilie",
    "function_group": "Functiegroep",
    "form_template": "Aanvraagformulier",
    "instance_setting": "Instelling",
    "peer": "Koppeling",
    "billing_delivery": "Aanlevering van factuurgegevens",
    "billing_terms": "Afspraken over facturering",
    "login": "Aanmelding",
    "passkey_credential": "Passkey",
    "vacancy_publication": "Openstelling van de vacature",
    "vacancy_text_library": "Bibliotheek met standaardteksten",
    "vacancy_text_remark": "Opmerking bij de vacaturetekst",
    "vacancy_text_review": "Beoordeling van de vacaturetekst",
    "vacancy_text_shared_section": "Gedeeld onderdeel van vacatureteksten",
    "vacancy_text_template": "Standaardtekst",
    "push_subscription": "Apparaat voor meldingen",
    "notification_preference": "Voorkeur voor meldingen",
    "stream": "Geschiedenis",
    "data": "Gegevens",
}

_VERBS = {"created": "toegevoegd", "updated": "gewijzigd", "deleted": "verwijderd"}

# Events that are more than a change of fields have a sentence of their own.
TYPE_SENTENCES: dict[str, str] = {
    "login.succeeded": "Ingelogd",
    "login.refused": "Inloggen geweigerd",
    "login.guest": "Ingelogd als genodigde",
    "login.switched": "Voorbeeldpersoon gekozen",
    "assignment_request.created": "Offerte aangevraagd",
    "assignment.status_changed": "Status van de opdracht gewijzigd",
    "quote.issued": "Offerte gemaakt",
    "quote.offered": "Offerte aangeboden",
    "quote.accepted": "Offerte aanvaard",
    "quote.rejected": "Offerte afgewezen",
    "quote_approval.requested": "Interne goedkeuring gevraagd",
    "quote_approval.approved": "Offerte intern goedgekeurd",
    "quote_approval.sent_back": "Offerte teruggestuurd naar de maker",
    "quote_approval.withdrawn": "Vraag om goedkeuring ingetrokken",
    "final_report.issued": "Eindrapport uitgebracht",
    "vacancy.published": "Vacature opengesteld",
    "invoice.recorded": "Factuur vastgelegd",
    "invoice.withdrawn": "Factuur ingetrokken",
    "person_scale.changed": "Schaal gewijzigd",
    "billing_correction.arose": "Correctie op factuurgegevens ontstaan",
    "data.read": "Gegevens ingezien",
    "stream.erased": "Waarden uit de geschiedenis gewist",
}

FIELD_LABELS: dict[str, str] = {
    "name": "Naam",
    "kind": "Soort",
    "status": "Status",
    "new_status": "Status",
    "start_date": "Begindatum",
    "end_date": "Einddatum",
    "started_on": "Begonnen op",
    "ended_on": "Afgerond op",
    "valid_from": "Ingangsdatum",
    "valid_to": "Einddatum",
    "billing_scale": "Schaal",
    "scale": "Schaal",
    "fte": "Fte",
    "fte_pct": "Inzet",
    "description": "Omschrijving",
    "role": "Rol",
    "amount_cents": "Bedrag",
    "quoted_amount_cents": "Offertebedrag",
    "total_cents": "Totaal",
    "monthly_rate_cents": "Maandtarief",
    "target": "Norm",
    "reason": "Reden",
    "function_title": "Functie",
    "stage": "Fase",
    "channel": "Kanaal",
    "form": "Vorm",
    "source": "Herkomst",
    "period_source": "Periode volgt",
    "invoice_number": "Factuurnummer",
    "invoice_date": "Factuurdatum",
}

_STATUS = {
    **ASSIGNMENT_STATUS_LABELS,
    "issued": "Gemaakt",
    "superseded": "Vervangen",
    "approved": "Goedgekeurd",
    "sent_back": "Teruggestuurd",
    "withdrawn": "Ingetrokken",
    "open": "Opengesteld",
    "filled": "Vervuld",
    "active": "Vastgesteld",
    "closed": "Gesloten",
    "todo": "Te doen",
    "doing": "Bezig",
    "waiting": "Wacht op een ander",
    "done": "Klaar",
    "obsolete": "Vervallen",
    "queued": "Klaargezet",
    "sent": "Verstuurd",
    "failed": "Niet gelukt",
}

# The label of a code value, per field. A value that is not here and looks
# like a code is not shown.
VALUE_LABELS: dict[str, dict[str, str]] = {
    "status": _STATUS,
    "new_status": _STATUS,
    "kind": {
        **ASSIGNMENT_KIND_LABELS,
        "personnel": "Personeel",
        "fixed": "Vast bedrag",
        "hr_advice": "Advies van HR",
        "control_advice": "Advies van control",
        "approval": "Akkoord",
        "vacancy": "Vacaturetekst",
        "motivation": "Aanleiding en motivatie",
    },
    "stage": {
        "prospective": "Komt in dienst",
        "colleague": "Collega",
        "left": "Uit dienst",
    },
    "channel": {
        "signing_link": "Tekenlink",
        "document": "Document",
        "client_instance": "Het grip van de opdrachtgever",
        "internal": "Intern",
        "federated": "Andere instanties van grip",
        "recruitment": "Werving",
    },
    "form": ACCEPTANCE_FORM_LABELS,
    "source": {
        "human": "Door een persoon geschreven",
        "model": "Opgesteld met een taalmodel",
        "standard_text": "Standaardtekst",
        "grip": "Grip",
        "wies": "Wies",
    },
    "period_source": {
        "assignment": "De opdracht",
        "line": "De begrotingsregel",
        "own": "Eigen periode",
    },
    "reason": {
        "onbekend": "Niet bekend in deze omgeving",
        "emailadres_niet_bevestigd": "Adres niet bevestigd door de provider",
        "geen_emailadres": "De provider gaf geen adres door",
        "geen_subject": "De provider gaf geen kenmerk van de persoon door",
        "inactief": "De persoon is inactief",
        "andere_aanmelding": "De persoon is aan een andere aanmelding gebonden",
        "standard_text": "Standaardtekst gebruikt",
        "retention": "Bewaartermijn verstreken",
        "read_retention": "Bewaartermijn van inzage verstreken",
        "retention_after_withdrawn_hire": (
            "Bewaartermijn na een ingetrokken aanstelling"
        ),
    },
}

_CLASS_LABELS = {
    "person_rate": "schaal en tarief",
    "person_cost": "kostentarief en marge",
    "person_kpi": "declarabiliteit",
}

# A code name: lower-case words joined by underscores.
CODE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_BARE_CODE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


class Seen(Protocol):
    """A change as the reader may see it (``reading.Change``)."""

    field: str
    visible: bool
    old: Any
    new: Any


def _euro(cents: int) -> str:
    whole, rest = divmod(abs(cents), 100)
    text = f"{whole:,}".replace(",", ".")
    if rest:
        text += f",{rest:02d}"
    return f"{'-' if cents < 0 else ''}€ {text}"


def _date(value: str) -> str | None:
    match = _ISO_DATE.match(value)
    if match is None:
        return None
    try:
        day = date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None
    return f"{day.day} {MONTH_NAMES[day.month - 1]} {day.year}"


def value_text(field: str, value: Any) -> str | None:
    """A value in words, or None when there is nothing to say."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "ja" if value else "nee"
    if isinstance(value, int):
        return _euro(value) if field.endswith("_cents") else str(value)
    if isinstance(value, float):
        return str(value).replace(".", ",")
    if not isinstance(value, str):
        return None
    labels = VALUE_LABELS.get(field)
    if labels and value in labels:
        return labels[value]
    as_date = _date(value)
    if as_date:
        return as_date
    if labels is not None and _BARE_CODE.match(value):
        # A code value nobody gave a label: not for a reader.
        return None
    if CODE.search(value):
        return None
    return f"{value}%" if field == "fte_pct" else value


def change_text(field: str, old: Any, new: Any) -> str | None:
    """ "Schaal van 11 naar 12"; None for a field without a Dutch name."""
    label = FIELD_LABELS.get(field)
    if label is None:
        return None
    before, after = value_text(field, old), value_text(field, new)
    if before and after:
        return None if before == after else f"{label} van {before} naar {after}"
    if after:
        return f"{label} {after}"
    if before:
        return f"{label} {before} vervalt"
    if old != new:
        return f"{label} gewijzigd"
    return None


# The rights a person can hold in grip and the roles on an assignment, as they
# read inside a sentence.
_RIGHT_LABELS = {
    "beheerder": "beheerder",
    "planner": "planner",
    "lezer": "lezer",
    "aanvrager": "aanvrager",
    "tekenbevoegde": "tekenbevoegde",
    "offertegoedkeurder": "interne goedkeurder van offertes",
}
_ASSIGNMENT_ROLE_LABELS = {"owner": "eigenaar", "manager": "manager"}


def _seen_value(changes: Sequence[Seen], *fields: str) -> Any:
    """The value of the first of these fields the reader may see."""
    for change in changes:
        if change.visible and change.field in fields:
            value = change.new if change.new is not None else change.old
            if value is not None:
                return value
    return None


def _right_title(
    event_type: str, person_name: str | None, changes: Sequence[Seen]
) -> str | None:
    """ "Recht lezer van Lot Lid ingetrokken": which right, and what happened."""
    right = _RIGHT_LABELS.get(_seen_value(changes, "function", "role_id"))
    ended = _seen_value(changes, "ended", "end_date") is not None
    if event_type.endswith(".created"):
        verb = "toegekend"
    elif ended or event_type.endswith(".deleted"):
        verb = "ingetrokken"
    else:
        return None
    link = "aan" if verb == "toegekend" else "van"
    subject = f"Recht {right}" if right else "Recht in grip"
    return (
        f"{subject} {link} {person_name} {verb}" if person_name else f"{subject} {verb}"
    )


def _assignment_role_title(
    event_type: str,
    person_name: str | None,
    changes: Sequence[Seen],
    case_name: str | None,
) -> str | None:
    """ "Lot Lid is manager van Opdracht Alfa": who, what and on which one."""
    role = _ASSIGNMENT_ROLE_LABELS.get(_seen_value(changes, "role"))
    if role is None or person_name is None:
        return None
    where = f"van {case_name}" if case_name else "van de opdracht"
    if event_type.endswith(".deleted"):
        return f"{person_name} is geen {role} meer {where}"
    return f"{person_name} is {role} {where}"


def title(
    event_type: str,
    subject_kind: str,
    person_name: str | None,
    payload: Any = None,
    *,
    changes: Sequence[Seen] = (),
    case_name: str | None = None,
) -> str:
    """What happened, in one line. Names the person when the reader may know."""
    told = None
    if subject_kind == "person_role":
        told = _right_title(event_type, person_name, changes)
    elif subject_kind == "assignment_role":
        told = _assignment_role_title(event_type, person_name, changes, case_name)
    if told is not None:
        return told
    sentence = TYPE_SENTENCES.get(event_type)
    if sentence is not None:
        if event_type == "person_scale.changed" and person_name:
            return f"Schaal van {person_name} gewijzigd"
        if event_type == "data.read" and person_name:
            return f"Gegevens van {person_name} ingezien"
        if event_type == "login.succeeded" and person_name:
            return f"{person_name} ingelogd"
        if event_type == "login.switched" and person_name:
            return f"Voorbeeldpersoon {person_name} gekozen"
        return sentence
    kind = KIND_LABELS.get(subject_kind, "Gegevens")
    verb = _VERBS.get(event_type.partition(".")[2], "gewijzigd")
    if person_name and subject_kind == "person":
        return f"{person_name} {verb}"
    if person_name:
        return f"{kind} van {person_name} {verb}"
    return f"{kind} {verb}"


def _read_line(values: Mapping[str, Any]) -> str | None:
    classes = [
        _CLASS_LABELS[name]
        for name in values.get("classes") or []
        if name in _CLASS_LABELS
    ]
    if not classes:
        return None
    text = " en ".join(classes).capitalize()
    persons = values.get("persons")
    if isinstance(persons, int) and persons > 1:
        text += f" van {persons} personen"
    return text


def lines(
    event_type: str,
    subject_kind: str,
    changes: Sequence[Seen],
    *,
    payload: Mapping[str, Any] | None = None,
    note: str | None = None,
    erased: bool = False,
) -> list[str]:
    """The change in words, for who may see it. Empty for a reader who may
    only know that it happened."""
    if erased:
        return ["De waarden zijn gewist"]
    seen = {change.field: change for change in changes if change.visible}
    if event_type == "data.read":
        line = _read_line({name: change.new for name, change in seen.items()})
        return [line] if line else []
    result = []
    for name, change in seen.items():
        if name == "valid_from" and subject_kind == "person_scale":
            continue
        text = change_text(name, change.old, change.new)
        if text:
            result.append(text)
    since = seen.get("valid_from")
    if subject_kind == "person_scale" and since is not None and result:
        when = value_text("valid_from", since.new)
        if when:
            result[-1] += f" per {when}"
    if event_type.startswith("login."):
        # The address that was offered: a beheerder needs it to know who to
        # add or unbind.
        address = (payload or {}).get("email")
        if isinstance(address, str) and address:
            result.append(f"Adres {address}")
    for name in ("new_status", "reason"):
        text = value_text(name, (payload or {}).get(name))
        if text and name not in seen:
            result.append(f"{FIELD_LABELS[name]} {text}")
    if note and not CODE.search(note):
        result.append(note)
    return result
