"""The statement of a decision: one canonical document, signed by the instance.

A statement says what was decided about which quote, by whom, when, how the
person was authenticated for it, and on which right or invitation grip
relied. It is canonical JSON (RFC 8785), like a quote, so it has one form
and one hash. The instance signs it as a compact JWS.

The statement is the decision. The columns grip keeps next to it (who
signed, for which organisation, when, through which channel) are read from
it, and so is the page a person reads. There is no second representation
that could say something else.

The statement is written in Dutch terms, like everything that leaves an
instance (ADR 0019).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import rfc8785

from grip.proof.jose import Jws, JwsError, b64url, sha256_hex, verify
from grip.proof.nonce import DECISION_CODES, DECISION_TERMS

STATEMENT_TYPE = "grip.akkoordverklaring"
STATEMENT_VERSION = 1

# Through which channel the decision reached grip.
CHANNEL_TERMS = {
    "signing_link": "tekenlink",
    "own_instance": "eigen_instantie",
    "internal": "intern",
    "uploaded_pdf": "document",
}
CHANNEL_CODES = {term: code for code, term in CHANNEL_TERMS.items()}

TIME_SOURCE_INSTANCE = "klok van de instantie"

MANDATE_NOTE = (
    "Grip legt vast op welk recht of welke uitnodiging het zich baseerde. Of "
    "deze persoon namens de organisatie mocht beslissen (het mandaat) is "
    "buiten grip vastgelegd en wordt hiermee niet bewezen."
)


class StatementError(Exception):
    """A statement is malformed or its signature does not verify."""


def canonical(value: Any) -> bytes:
    return rfc8785.dumps(value)


@dataclass(frozen=True)
class Authentication:
    """How the person was authenticated for this decision."""

    # What grip asked the provider for; None when no provider was involved.
    requested: dict[str, Any] | None
    client_id: str | None
    # None when the provider did not say, or there was no provider.
    auth_time: datetime | None
    fresh: bool | None
    age_seconds: int | None
    acr: str | None = None
    amr: tuple[str, ...] = ()
    id_token_sha256: str | None = None
    nonce_inputs: dict[str, Any] | None = None
    # Why there is no token, when there is none.
    absent_reason: str | None = None


@dataclass(frozen=True)
class Authority:
    """What grip relied on to let this person decide."""

    # "uitnodiging", "recht" or "functie".
    basis: str
    # The right or function, by its key in this instance.
    right: str | None = None
    since: str | None = None
    granted_by: str | None = None
    # The signer declared to be authorised to sign for the organisation.
    declared_by_signer: bool | None = None


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def build_statement(
    *,
    statement_id: str,
    action: str,
    channel: str,
    quote_fingerprint: str,
    quote_reference: str | None,
    quote_uri: str,
    quote_total_cents: int | None,
    document_sha256: str | None = None,
    document_fixed: str | None = None,
    subject: str | None,
    issuer: str | None,
    name: str,
    email: str,
    email_verified: bool | None,
    function: str | None,
    organisation_claimed: dict[str, Any] | None,
    on_behalf_of: dict[str, Any] | None,
    received_at: datetime,
    authentication: Authentication,
    authority: Authority,
    instance_name: str,
    instance_base_uri: str,
    note: str | None = None,
) -> dict[str, Any]:
    """The statement as a plain structure, ready to be made canonical."""
    how: dict[str, Any] = {
        "kanaal": CHANNEL_TERMS[channel],
        "aanmelding": {
            "gevraagd": authentication.requested,
            "client_id": authentication.client_id,
            "vers": authentication.fresh,
            "leeftijd_seconden": authentication.age_seconds,
            "acr": authentication.acr,
            "amr": list(authentication.amr),
            "ontbreekt_omdat": authentication.absent_reason,
        },
        "id_token_sha256": authentication.id_token_sha256,
        "nonce": authentication.nonce_inputs,
    }
    return {
        "soort": STATEMENT_TYPE,
        "versie": STATEMENT_VERSION,
        "id": statement_id,
        "besluit": DECISION_TERMS[action],
        "offerte": {
            "vingerafdruk": quote_fingerprint,
            "kenmerk": quote_reference,
            "uri": quote_uri,
            "totaal_centen": quote_total_cents,
            # The file the decision is about: the fingerprint above proves
            # the content, this hash the document as it was laid out.
            "bestand_sha256": document_sha256,
            "bestand_vastgelegd": document_fixed,
        },
        "wie": {
            "subject": subject,
            "uitgever": issuer,
            "naam": name,
            "email": email,
            "email_bevestigd": email_verified,
            "functie": function,
            "organisatie_volgens_provider": organisation_claimed,
        },
        "namens": on_behalf_of,
        "wanneer": {
            "aangemeld_op": _iso(authentication.auth_time),
            "ontvangen_op": received_at.isoformat(),
            "tijdbron": TIME_SOURCE_INSTANCE,
        },
        "hoe": how,
        "bevoegdheid": {
            "grondslag": authority.basis,
            "recht": authority.right,
            "sinds": authority.since,
            "toegekend_door": authority.granted_by,
            "verklaring_ondertekenaar": authority.declared_by_signer,
            "toelichting": MANDATE_NOTE,
        },
        "toelichting": note,
        "instantie": {"naam": instance_name, "basis_uri": instance_base_uri},
    }


@dataclass(frozen=True)
class SignedStatement:
    canonical: bytes
    hash: str
    jws: str


def sign_statement(
    statement: dict[str, Any], *, private_key: Any, kid: str
) -> SignedStatement:
    """Make the statement canonical and sign it (ES256) with the instance key.

    ``private_key`` is an EC P-256 private key of ``cryptography``. The
    caller supplies it, so this module needs no settings.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    body = canonical(statement)
    header = b64url(
        json.dumps(
            {"alg": "ES256", "kid": kid, "typ": "grip-akkoordverklaring+jws"},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{b64url(body)}".encode("ascii")
    der = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return SignedStatement(
        canonical=body,
        hash=sha256_hex(body),
        jws=f"{signing_input.decode('ascii')}.{b64url(signature)}",
    )


def read_statement(jws: str, jwks: dict[str, Any] | None) -> tuple[dict[str, Any], Jws]:
    """Verify the JWS of a statement and return the statement.

    Raises ``StatementError`` when the signature does not verify, the
    payload is not the canonical form of what it says, or it is not a
    statement of a known version.
    """
    try:
        verified = verify(jws, jwks)
    except JwsError as exc:
        raise StatementError(
            f"De verklaring is niet geldig ondertekend: {exc}"
        ) from exc
    return parse_statement(verified.payload), verified


def parse_statement(payload: bytes) -> dict[str, Any]:
    """The statement in a payload, without checking any signature."""
    try:
        statement = json.loads(payload)
    except ValueError as exc:
        raise StatementError("De verklaring bevat geen JSON.") from exc
    if not isinstance(statement, dict) or statement.get("soort") != STATEMENT_TYPE:
        raise StatementError("Dit is geen akkoordverklaring van grip.")
    if statement.get("versie") != STATEMENT_VERSION:
        raise StatementError(
            f"Onbekende versie van de verklaring: {statement.get('versie')!r}."
        )
    if canonical(statement) != payload:
        raise StatementError("De verklaring staat niet in haar canonieke vorm.")
    if statement.get("besluit") not in DECISION_CODES:
        raise StatementError("De verklaring noemt geen bekend besluit.")
    return statement


def columns(statement: dict[str, Any]) -> dict[str, Any]:
    """The values grip keeps in columns next to a statement, read from it.

    One function, so the columns cannot be filled from anywhere else.
    """
    who = statement["wie"]
    return {
        "action": DECISION_CODES[statement["besluit"]],
        "channel": CHANNEL_CODES[statement["hoe"]["kanaal"]],
        "quote_hash": statement["offerte"]["vingerafdruk"],
        "document_sha256": statement["offerte"].get("bestand_sha256"),
        "signer_name": who["naam"],
        "signer_email": who["email"],
        "signer_function": who.get("functie"),
        "organisation": statement.get("namens"),
        "decided_at": datetime.fromisoformat(statement["wanneer"]["ontvangen_op"]),
        "note": statement.get("toelichting"),
    }
