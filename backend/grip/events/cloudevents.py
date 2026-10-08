"""Events as CloudEvents in the NL GOV profile, for other systems.

The stream is English inside; what another system reads is Dutch, as the
interface of grip is everywhere at its edge. The translation happens here
and nowhere else.

An event in the feed is thin on purpose. It says what happened to what, and
nothing of the values: no amounts, no scales, no names. A system that needs
more asks grip for the thing itself and is then decided on by the access
model like any other reader. Context attributes never carry personal data.
"""

from __future__ import annotations

import re
from typing import Any

from grip.core.config import Settings
from grip.events import chain
from grip.models.stream_event import StreamEvent

SPECVERSION = "1.0"
TYPE_PREFIX = "nl.grip"
CONTENT_TYPE = "application/json"

# Kind of subject, in the Dutch of the interface.
KINDS: dict[str, str] = {
    "assignment": "opdracht",
    "assignment_request": "opdrachtaanvraag",
    "assignment_role": "opdrachtrol",
    "task": "taak",
    "budget_line": "begrotingsregel",
    "budget_usage_requested": "begrotingsgebruik",
    "quote": "offerte",
    "quote_draft": "offerteconcept",
    "quote_offer": "offerteaanbieding",
    "quote_invitation": "tekenuitnodiging",
    "quote_acceptance": "offerteakkoord",
    "quote_rejection": "offerteafwijzing",
    "quote_approval": "offertegoedkeuring",
    "decision_evidence": "besluitbewijs",
    "mail_outbox": "uitgaande-mail",
    "final_report": "eindrapport",
    "final_report_received": "eindrapport-ontvangen",
    "month_close": "maandafsluiting",
    "billing_export": "factuurgegevens",
    "billing_correction": "factuurcorrectie",
    "outgoing_invoice": "factuur",
    "invoice": "factuur",
    "invoice_line": "factuurregel",
    "invoice_attachment": "factuurbijlage",
    "cost_item": "kostenpost",
    "cost_coverage": "kostendekking",
    "allocation": "inzet",
    "person": "persoon",
    "person_standing": "dienstverband",
    "person_role": "persoonsrol",
    "person_roles": "persoonsrollen",
    "colleague_proposal": "collegavoorstel",
    "person_scale": "inzetschaal",
    "hire": "inhuur",
    "billability_target": "declarabiliteitsnorm",
    "vacancy": "vacature",
    "vacancy_text": "vacaturetekst",
    "vacancy_step": "vacaturestap",
    "vacancy_decision": "vacaturebesluit",
    "vacancy_recruitment_ref": "wervingsverwijzing",
    "vacancy_offer_received": "vacatureaanbod",
    "vacancy_hire": "vacature-invulling",
    "rate_card": "tarievenkaart",
    "rate_band": "tariefregel",
    "scale_band": "schaalindeling",
    "organisation": "organisatie",
    "organisation_sync": "organisatiesynchronisatie",
    "catalogue_role": "rol",
    "catalogue_role_sync": "rollensynchronisatie",
    "function_framework": "functiegebouw",
    "function_family": "functiefamilie",
    "function_group": "functiegroep",
    "form_template": "formulier",
    "instance_setting": "instelling",
    "peer": "koppeling",
    "stream": "stroom",
    "data": "gegevens",
}

# What happened, in the Dutch of the interface.
VERBS: dict[str, str] = {
    "created": "aangemaakt",
    "updated": "gewijzigd",
    "deleted": "verwijderd",
    "changed": "gewijzigd",
    "status_changed": "status-gewijzigd",
    "issued": "uitgebracht",
    "offered": "aangeboden",
    "accepted": "aanvaard",
    "rejected": "afgewezen",
    "requested": "gevraagd",
    "approved": "goedgekeurd",
    "sent_back": "teruggestuurd",
    "withdrawn": "ingetrokken",
    "published": "gepubliceerd",
    "recorded": "vastgelegd",
    "arose": "ontstaan",
    "read": "ingezien",
    "erased": "gewist",
}

_CASES = {"assignment": "opdracht", "vacancy": "vacature"}
_ACTORS = {
    "person": "persoon",
    "guest": "gast",
    "peer": "instantie",
    "system": "systeem",
}
_ORIGINS = {"local": "eigen", "remote": "ontvangen"}
_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SLUG.sub("-", value.lower()).strip("-")


def event_type(internal: str) -> str:
    """``quote.accepted`` becomes ``nl.grip.offerte.aanvaard``."""
    kind, _, verb = internal.partition(".")
    return ".".join(
        [
            TYPE_PREFIX,
            KINDS.get(kind, _slug(kind)),
            VERBS.get(verb, _slug(verb)) or "gebeurd",
        ]
    )


def source(settings: Settings) -> str:
    """The source of every event of this instance.

    A URN in the ``nld`` namespace when the OIN of the organisation is
    configured, as the profile asks. Without it the base address of the
    instance, which CloudEvents allows but the profile does not.
    """
    system = f"grip-{_slug(settings.INSTANCE_KEY)}"
    if settings.INSTANCE_OIN:
        return f"urn:nld:oin:{settings.INSTANCE_OIN}:systeem:{system}"
    return settings.INSTANCE_BASE_URI.rstrip("/")


def to_cloudevent(event: StreamEvent, settings: Settings) -> dict[str, Any]:
    kind = KINDS.get(event.subject_kind, _slug(event.subject_kind))
    data: dict[str, Any] = {
        "onderwerp": {"soort": kind, "id": event.subject_id},
        "actor": {"soort": _ACTORS.get(event.actor_kind, event.actor_kind)},
        "herkomst": _ORIGINS.get(event.origin, event.origin),
        "correlatie": event.correlation_id,
        "hash": event.hash,
        "vorige_hash": event.prev_hash,
    }
    if event.case_kind and event.case_id:
        data["zaak"] = {
            "soort": _CASES.get(event.case_kind, event.case_kind),
            "id": str(event.case_id),
        }
    if event.origin_peer:
        data["herkomst_instantie"] = event.origin_peer
    if event.action:
        fields = sorted({*(event.old_value or {}), *(event.new_value or {})})
        data["aantal_gewijzigde_velden"] = len(fields)
    return {
        "specversion": SPECVERSION,
        "id": str(event.id),
        "source": source(settings),
        "type": event_type(event.type),
        # The subject is an id of grip, never a name or a number of a person.
        "subject": event.subject_id,
        "time": chain.timestamp(event.occurred_at),
        "datacontenttype": CONTENT_TYPE,
        "sequence": str(event.seq),
        "sequencetype": "Integer",
        "data": data,
    }
