"""Contract terms and code names: the one place where the two meet.

This is a document format, not transport. The interface that grip shares
with other organisations is Dutch, as the NL GOV API Design Rules ask; the
code of grip is English. The same Dutch form is also the canonical form of
an issued quote: the document that is hashed, signed, printed and sent (see
:mod:`grip.services.canonical` and ADR 0020). That is why this module lives
with the domain services and knows nothing of FSC, peers or messages; the
federation module uses it at its boundary:

- ``to_contract`` right before a message or an answer is validated and sent;
- ``from_contract`` right after a received message or answer is validated.

The translation is a renaming of keys plus, for a few keys, of the values of
a code list. It is reversible: every contract term has exactly one code name.
Terms that are equal on both sides (id, uri, type, status as a key, jws, fte,
email, peildatum) are not listed. Nothing is translated inside
``type_details`` of a node (already domain vocabulary) or inside ``keys`` of
a key set (JWK members).

Something that is already in contract terms, such as the stored canonical
form of a quote, is wrapped in :class:`Verbatim` so that it passes through
``to_contract`` untouched: it must never be translated back and forth.

The tables mirror docs/termen.md of the contract repo. A test checks them
against the vendored schemas, so a term that is added to the contract and
forgotten here fails the build.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Code name to contract term, for property names.
PROPERTIES: dict[str, str] = {
    "agreed": "afgesproken",
    "amount": "bedrag",
    "amount_cents": "bedrag_centen",
    "as_of": "peilmoment",
    "assignment": "opdracht",
    "assignment_uri": "opdracht_uri",
    "available": "beschikbaar",
    "available_from": "beschikbaar_vanaf",
    "available_fte": "beschikbare_fte",
    "basis": "grondslag",
    "budget_indication": "budgetindicatie",
    "budget_line": "begrotingsregel",
    "budgeted": "begroot",
    "candidate_reference": "kandidaat_referentie",
    "canonicalization": "canonicalisatie",
    "client": "opdrachtgever",
    "closed_at": "afgesloten_op",
    "complete": "volledig",
    "conditions": "voorwaarden",
    "content_base64": "inhoud_base64",
    "context_refs": "context_uris",
    "contract_version": "contractversie",
    "contractor": "opdrachtnemer",
    "coverage": "kostendekking",
    "covered": "gedekt",
    "currency": "valuta",
    "custom": "eigen",
    "delivered": "geleverd",
    "deployed_fte": "ingezette_fte",
    "description": "omschrijving",
    "desired_period": "gewenste_periode",
    "due_date": "streefdatum",
    "edge_types": "edge_typen",
    "end_date": "einddatum",
    "external_node_uris": "externe_node_uris",
    "forecast": "prognose",
    "form": "vorm",
    "from": "van",
    "function": "functie",
    "hash_algorithm": "hash_algoritme",
    "headcount": "aantal",
    "instance_uri": "instantie_uri",
    "issued_at": "uitgegeven_op",
    "kind": "soort",
    "lines": "regels",
    "managing_organisation": "beherende_organisatie",
    "media_type": "mediatype",
    "message_id": "bericht_id",
    "milestones": "mijlpalen",
    "month": "maand",
    "monthly_rate": "maandtarief",
    "monthly_rates_per_year": "maandtarieven_per_jaar",
    "monthly_rate_periods": "maandtarieven_per_periode",
    "name": "naam",
    "namespace": "naamruimte",
    "node_types": "node_typen",
    "not_delivered": "niet_geleverd",
    "offered_at": "aangeboden_op",
    "open_roles": "open_rollen",
    "organisation": "organisatie",
    "outcome": "uitkomst",
    "parent_assignment_uri": "bovenliggende_opdracht_uri",
    "period": "periode",
    "person": "persoon",
    "position": "positie",
    "profile": "profiel",
    "published_at": "gepubliceerd_op",
    "quote_hash": "offerte_hash",
    "quote_id": "offerte_id",
    "quoted_amount": "offertebedrag",
    "rate_category": "tariefcategorie",
    "reason": "reden",
    "received_at": "ontvangen_op",
    "rejected_at": "afgewezen_op",
    "request_id": "aanvraag_id",
    "respond_by": "reageren_voor",
    "results": "resultaten",
    "role": "rol",
    "sent_at": "verzonden_op",
    "signed_at": "getekend_op",
    "signer": "ondertekenaar",
    "snapshot": "momentopname",
    "snapshot_hash": "momentopname_hash",
    "sought_fte": "gezochte_fte",
    "spending": "besteding",
    "start_date": "begindatum",
    "state": "stand",
    "subtotals_per_year": "subtotalen_per_jaar",
    "summary": "samenvatting",
    "title": "titel",
    "to": "naar",
    "total": "totaal",
    "total_cost": "totale_kosten",
    "unit_key": "eenheid_kenmerk",
    "used": "uitputting",
    "vacancy_id": "vacature_id",
    "valid_until": "geldig_tot_en_met",
    "validity": "geldigheid",
    "year": "jaar",
    # A quote: its reference, sender and scales.
    "reference": "kenmerk",
    "client_reference": "uw_kenmerk",
    "sender": "afzender",
    "scales": "schalen",
    # The text of a quote as a letter (grip.services.quote_drafts).
    "letter": "brief",
    "subject": "betreft",
    "addressee": "geadresseerde",
    "salutation": "aanhef",
    "closing": "afsluiting",
    "sections": "onderdelen",
    "key": "sleutel",
    "heading": "kop",
    "body": "tekst",
    "with_costs": "met_kosten",
    "numbered": "genummerd",
    "sender_details": "afzendergegevens",
    "part_of": "valt_onder",
    "unit": "eenheid",
    "visiting_address": "bezoekadres",
    "postal_address": "postadres",
    "signatures": "ondertekening",
    "on_behalf_of": "namens",
    "billing_annex": "bijlage_factuurinformatie",
    # Where a vacancy can be read by anyone.
    "publications": "publicaties",
    "place": "plek",
}

_ALL_PROPERTIES: dict[str, str] = PROPERTIES

# Per code name of a property: code value to contract value of its code list.
VALUES: dict[str, dict[str, str]] = {
    "form": {
        "own_instance": "eigen_instantie",
        "signing_link": "tekenlink",
        "uploaded_pdf": "geuploade_pdf",
    },
    "kind": {
        "external": "extern",
        "internal": "intern",
        "personnel": "personeel",
        "fixed": "vast",
    },
    "status": {
        "draft": "concept",
        "requested": "aangevraagd",
        "quoted": "offerte_uitgegeven",
        "accepted": "akkoord",
        "in_progress": "in_uitvoering",
        "completed": "afgerond",
        "accounted": "verantwoord",
        "rejected": "afgewezen",
        "cancelled": "geannuleerd",
        "open": "open",
        "filled": "ingevuld",
        "withdrawn": "ingetrokken",
    },
    "place": {
        "internal": "intern",
        "government_wide": "rijksbreed",
        "external": "extern",
    },
    "basis": {
        "actual_allocation": "werkelijke_inzet",
        "fixed_amount": "vast_bedrag",
        "actual_costs": "werkelijke_kosten",
    },
    "state": {
        "planned": "gepland",
        "done": "gereed",
        "dropped": "vervallen",
    },
    "outcome": {
        "accepted": "aanvaard",
        "duplicate": "duplicaat",
    },
}

# Code name to contract term, for path and query parameters.
PARAMETERS: dict[str, str] = {
    "quoteId": "offerteId",
    "assignmentId": "opdrachtId",
    "vacancyId": "vacatureId",
    "month": "maand",
    "year": "jaar",
    "maxDepth": "maxDiepte",
}

# Code name to the name of the schema in the contract.
SCHEMAS: dict[str, str] = {
    "acceptance": "akkoord",
    "assignment-page": "opdracht-pagina",
    "assignment-request": "opdrachtaanvraag",
    "assignment": "opdracht",
    "billing-data": "factuurgegevens",
    "budget-usage": "uitputting",
    "chain": "keten",
    "corpus-info": "corpus-info",
    "edge": "edge",
    "final-report": "eindrapport",
    "handover-assignments": "doorgifte-opdrachten",
    "handover-billing-data": "doorgifte-factuurgegevens",
    "handover-capacity": "doorgifte-capaciteit",
    "handover-costs": "doorgifte-kosten",
    "handover-staffing": "doorgifte-bemensing",
    "jwks": "jwks",
    "money": "bedrag",
    "node-page": "node-pagina",
    "node": "node",
    "organisation-ref": "organisatie-ref",
    "period": "periode",
    "problem": "problem",
    "progress": "voortgang",
    "quote": "offerte",
    "receipt": "ontvangstbevestiging",
    "rejection": "afwijzing",
    "vacancy-offer": "aanbod",
    "vacancy": "vacature",
    "vocabulary": "woordenlijst",
}

# Keys whose value is passed on untouched.
OPAQUE: frozenset[str] = frozenset({"type_details", "keys"})

_PROPERTIES_BACK = {term: name for name, term in _ALL_PROPERTIES.items()}

# Terms that only occur in content frozen before the contract settled them.
# A quote keeps the bytes it was issued with (ADR 0020), so its old term is
# still read; nothing is ever written with it again.
#   onderdeel_van: what an organisation is part of, in the sender's details
#   of a quote as a letter. The contract names it valt_onder, because a
#   property may not carry the name of a vocabulary type.
_READ_ONLY_TERMS: dict[str, str] = {"onderdeel_van": "part_of"}
_VALUES_BACK = {
    name: {term: value for value, term in values.items()}
    for name, values in VALUES.items()
}
_PARAMETERS_BACK = {term: name for name, term in PARAMETERS.items()}

assert len(_PROPERTIES_BACK) == len(_ALL_PROPERTIES), (
    "a contract term has two code names"
)
assert not set(_PROPERTIES_BACK) & set(_ALL_PROPERTIES), (
    "a term is both code and contract"
)


# Terms grip uses that the contract does not describe yet. Empty: the
# contract has every term. A term grip needs ahead of the contract goes here
# (and into PROPERTIES), so the test that compares the two says so.
PENDING_CONTRACT_TERMS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Verbatim:
    """A value that is already in contract terms and must stay exactly so."""

    value: Any


def _forward(value: Any, key: str | None) -> Any:
    if isinstance(value, Verbatim):
        return value.value
    if isinstance(value, dict):
        return {
            _ALL_PROPERTIES.get(name, name): (
                item if name in OPAQUE else _forward(item, name)
            )
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [_forward(item, key) for item in value]
    if isinstance(value, str) and key in VALUES:
        return VALUES[key].get(value, value)
    return value


def _backward(value: Any, key: str | None) -> Any:
    if isinstance(value, dict):
        result = {}
        for term, item in value.items():
            name = _PROPERTIES_BACK.get(term) or _READ_ONLY_TERMS.get(term, term)
            result[name] = item if name in OPAQUE else _backward(item, name)
        return result
    if isinstance(value, list):
        return [_backward(item, key) for item in value]
    if isinstance(value, str) and key in _VALUES_BACK:
        return _VALUES_BACK[key].get(value, value)
    return value


def to_contract(value: Any) -> Any:
    """A message in code names, as the contract spells it."""
    return _forward(value, None)


def from_contract(value: Any) -> Any:
    """A message as the contract spells it, in code names."""
    return _backward(value, None)


def term(name: str) -> str:
    """The contract term for the code name of one property."""
    return PROPERTIES.get(name, name)


def contract_value(key: str, value: str) -> str:
    """One value of a code list, as the contract spells it. ``key`` is the code name."""
    return VALUES.get(key, {}).get(value, value)


def code_value(key: str, value: str) -> str:
    """One value of a code list, in code. ``key`` is the code name."""
    return _VALUES_BACK.get(key, {}).get(value, value)


def contract_parameter(name: str) -> str:
    return PARAMETERS.get(name, name)


def code_parameter(term: str) -> str:
    return _PARAMETERS_BACK.get(term, term)


def schema(name: str) -> str:
    """The name of a schema in the contract, given its code name."""
    return SCHEMAS.get(name, name)
