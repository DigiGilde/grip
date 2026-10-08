"""Deciding with proof: from the button to the stored evidence.

1. ``create_intent``: someone is about to decide. Grip stores what they are
   deciding and a random value, and computes the nonce from them.
2. The person is sent to the identity provider with that nonce and a demand
   to authenticate again (``authorization_params``).
3. ``complete_intent``: the provider sent them back with an ID token. Grip
   checks that the token is for this decision and this person, writes the
   statement, signs it, stores the evidence and only then carries out the
   decision, with the values read from the statement.

Without an identity provider (local development) step 2 is skipped and the
statement says truthfully that nobody vouched for the identity.

This module sits above the service layer and the federation module: it is
the one place that knows both, so the domain still knows nothing of
transport or keys (ADR 0015).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, record_audit
from grip.core.config import Settings
from grip.models.decision_proof import DecisionEvidence, SigningIntent
from grip.models.person import Person
from grip.models.quote import Quote, QuoteInvitation
from grip.models.role import PersonRole
from grip.proof import timestamp as timestamps
from grip.proof.bundle import build_bundle
from grip.proof.idtoken import IdTokenError, IdTokenFacts, check_id_token
from grip.proof.jose import sha256_hex
from grip.proof.nonce import compute_nonce, new_salt, nonce_inputs
from grip.proof.statement import (
    Authentication,
    Authority,
    build_statement,
    columns,
    parse_statement,
    sign_statement,
)
from grip.services import instance_settings, quote_files
from grip.services.errors import DomainValidationError, NotFoundError

logger = logging.getLogger(__name__)

INTENT_TTL = timedelta(minutes=10)

# What the provider is asked for: authenticate now, whatever session exists.
REAUTHENTICATION = {"prompt": "login", "max_age": 0}

STALE_RECORD = "record"
STALE_REFUSE = "refuse"

STALE_AUTHENTICATION = instance_settings.declare(
    "proof.stale_authentication",
    STALE_RECORD,
    instance_settings.one_of(STALE_RECORD, STALE_REFUSE),
    "Wat er gebeurt als de identiteitsprovider iemand bij een besluit niet "
    "opnieuw laat inloggen: het besluit vastleggen met de vermelding dat de "
    "aanmelding niet vers was (record), of het besluit weigeren (refuse).",
)


def _authority_url(value: Any) -> str:
    text = str(value or "").strip()
    if text and not text.lower().startswith(("https://", "http://")):
        raise DomainValidationError(
            "Het adres van een tijdstempelautoriteit begint met https://."
        )
    return text


TIMESTAMP_AUTHORITY = instance_settings.declare(
    "proof.timestamp_authority_url",
    "",
    _authority_url,
    "Het adres van een tijdstempelautoriteit (RFC 3161) die bij elk besluit "
    "een onafhankelijk tijdstip zet. Leeg: het tijdstip is de klok van de "
    "instantie, en dat staat dan in het bewijs.",
)

# Channel and action decide which right grip relies on.
RIGHT_TEKENBEVOEGDE = "tekenbevoegde"
RIGHT_OFFERTEGOEDKEURDER = "offertegoedkeurder"

NO_PROVIDER = (
    "deze instantie draait zonder identiteitsprovider (lokale ontwikkeling); "
    "niemand staat in voor wie dit was"
)


class ProofRefusedError(Exception):
    """The decision is not carried out. ``code`` tells the screen why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class IdentityProvider:
    """What grip keeps of the provider with a token it issued."""

    issuer: str
    client_id: str
    jwks: dict[str, Any]
    discovery: dict[str, Any]


def reauthentication_required(settings: Settings) -> bool:
    """Whether a decision goes through the identity provider."""
    return bool(settings.OIDC_ISSUER)


def authorization_params(intent: SigningIntent) -> dict[str, Any]:
    """Extra parameters of the authorization request for this intent."""
    return {**REAUTHENTICATION, "nonce": intent.nonce}


async def create_intent(
    db: AsyncSession,
    *,
    action: str,
    channel: str,
    quote: Quote,
    quote_hash: str,
    person: Person | None,
    email: str,
    params: dict[str, Any] | None = None,
    return_path: str = "/",
    now: datetime | None = None,
) -> SigningIntent:
    """Record that someone is about to decide, and compute the nonce for it.

    ``quote_hash`` is the hash of what the person saw. A quote that changed
    since is another quote; the decision would be about bytes nobody read.
    """
    if quote_hash != quote.snapshot_hash:
        raise DomainValidationError(
            "De offerte is gewijzigd sinds je haar opende. Open haar opnieuw."
        )
    moment = now or datetime.now(UTC)
    # The decision is about a file as well as about content: the kept PDF,
    # the bytes every reader of this quote is shown.
    kept = await quote_files.file_of(db, quote)
    inputs = nonce_inputs(
        quote_fingerprint=quote.snapshot_hash,
        document_sha256=kept.sha256,
        action=action,
        reference=quote.reference,
        salt=new_salt(),
    )
    intent = SigningIntent(
        id=uuid.uuid4(),
        action=action,
        channel=channel,
        quote_id=quote.id,
        quote_hash=quote.snapshot_hash,
        nonce_inputs=inputs,
        nonce=compute_nonce(inputs),
        person_id=person.id if person is not None else None,
        email=email.strip().lower(),
        params=params or {},
        return_path=return_path or "/",
        expires_at=moment + INTENT_TTL,
    )
    db.add(intent)
    await db.flush()
    return intent


async def get_intent(db: AsyncSession, intent_id: UUID) -> SigningIntent:
    intent = await db.get(SigningIntent, intent_id)
    if intent is None:
        raise NotFoundError("Verzoek om te beslissen", intent_id)
    return intent


def _organisation_claims(claims: dict[str, Any]) -> dict[str, Any] | None:
    """What the provider says about the person's organisation, as given.

    The names differ per provider and per realm; they are copied, not
    interpreted. The platform's Keycloak maps SSO Rijk's organisation name
    and number onto user attributes with these names.
    """
    names = (
        "organizationName",
        "organizationNumber",
        "organization",
        "organisation",
        "organisatie",
        "org_name",
        "org_id",
    )
    found = {name: claims[name] for name in names if claims.get(name) not in (None, "")}
    return found or None


async def _right(
    db: AsyncSession, person: Person, right: str, day: date
) -> tuple[str | None, str | None]:
    """Since when the person holds a right, and who granted it."""
    result = await db.execute(
        select(PersonRole)
        .where(
            PersonRole.person_id == person.id,
            PersonRole.role_id == right,
            PersonRole.start_date <= day,
        )
        .order_by(PersonRole.start_date.desc())
    )
    for held in result.scalars():
        if held.end_date is not None and held.end_date < day:
            continue
        granter = (
            await db.get(Person, held.granted_by_id) if held.granted_by_id else None
        )
        return (
            held.start_date.isoformat(),
            granter.name if granter is not None else "het systeem",
        )
    return None, None


async def _authority(
    db: AsyncSession, intent: SigningIntent, person: Person | None, day: date
) -> Authority:
    if intent.channel == "signing_link":
        invitation = (
            await db.execute(
                select(QuoteInvitation).where(
                    QuoteInvitation.quote_id == intent.quote_id,
                    func.lower(QuoteInvitation.email) == intent.email,
                )
            )
        ).scalar_one_or_none()
        inviter = (
            await db.get(Person, invitation.invited_by_id)
            if invitation is not None and invitation.invited_by_id
            else None
        )
        return Authority(
            basis="uitnodiging",
            since=invitation.created_at.date().isoformat() if invitation else None,
            granted_by=inviter.name if inviter is not None else None,
            declared_by_signer=bool(intent.params.get("confirm_mandate")) or None,
        )
    right = (
        RIGHT_OFFERTEGOEDKEURDER
        if intent.channel == "internal"
        else RIGHT_TEKENBEVOEGDE
    )
    since, granter = (
        await _right(db, person, right, day) if person is not None else (None, None)
    )
    return Authority(basis="recht", right=right, since=since, granted_by=granter)


def _check_identity(
    intent: SigningIntent, person: Person | None, facts: IdTokenFacts
) -> None:
    """The token must be about whoever started the decision."""
    if person is not None:
        if person.oidc_subject != facts.subject:
            raise ProofRefusedError(
                "andere_persoon",
                "Bij het opnieuw inloggen meldde zich iemand anders aan dan "
                "wie het besluit begon.",
            )
        return
    # A guest is known by the address the provider vouches for.
    if not facts.email_verified or facts.email != intent.email:
        raise ProofRefusedError(
            "andere_persoon",
            "Bij het opnieuw inloggen meldde zich iemand anders aan dan "
            "wie voor deze offerte is uitgenodigd.",
        )


async def _timestamp(
    db: AsyncSession, message: bytes, http_client: Any | None
) -> tuple[bytes | None, str | None]:
    url = await instance_settings.get(db, TIMESTAMP_AUTHORITY.key)
    if not url:
        return None, None
    if not timestamps.available() or http_client is None:
        logger.warning("Timestamp authority configured but no client available")
        return None, None
    try:
        return await timestamps.request_timestamp(
            message, url, http_client=http_client
        ), url
    except timestamps.TimestampError as exc:
        # The decision stands without it; the bundle then says that the
        # time is the instance's own.
        logger.warning("No timestamp obtained: %s", exc)
        return None, None


@dataclass(frozen=True)
class Completed:
    evidence: DecisionEvidence
    statement: dict[str, Any]


Executor = Any  # async (db, intent, quote, person, values, evidence) -> None


async def complete_intent(
    db: AsyncSession,
    intent: SigningIntent,
    *,
    settings: Settings,
    signing_key: Any,
    instance_jwks: dict[str, Any],
    execute: Executor,
    id_token: str | None = None,
    provider: IdentityProvider | None = None,
    http_client: Any | None = None,
    now: datetime | None = None,
) -> Completed:
    """Check the authentication, write and sign the statement, then decide.

    ``id_token`` and ``provider`` are given when the person came back from
    the identity provider. Without them the instance must be one without a
    provider; with a provider configured a decision without a token is
    refused.

    ``execute`` carries out the decision in the domain. It gets the values
    read from the statement, so what is recorded in columns is what the
    statement says.
    """
    moment = now or datetime.now(UTC)
    if intent.completed_at is not None:
        raise ProofRefusedError(
            "al_gebruikt", "Dit verzoek om te beslissen is al afgehandeld."
        )
    if intent.expires_at < moment:
        intent.failure = "verlopen"
        raise ProofRefusedError(
            "verlopen",
            "Het duurde te lang tussen de knop en het inloggen. Begin opnieuw.",
        )
    quote = await db.get(Quote, intent.quote_id)
    if quote is None:
        raise NotFoundError("Offerte", intent.quote_id)
    if quote.snapshot_hash != intent.quote_hash:
        raise ProofRefusedError(
            "offerte_gewijzigd", "De offerte is intussen gewijzigd."
        )
    person = await db.get(Person, intent.person_id) if intent.person_id else None

    facts: IdTokenFacts | None = None
    if reauthentication_required(settings):
        if not id_token or provider is None:
            raise ProofRefusedError(
                "geen_aanmelding",
                "Zonder aanmelding bij de identiteitsprovider wordt een besluit "
                "niet vastgelegd.",
            )
        try:
            facts = check_id_token(
                id_token,
                provider.jwks,
                issuer=provider.issuer,
                client_id=provider.client_id,
                nonce=compute_nonce(intent.nonce_inputs),
            )
        except IdTokenError as exc:
            intent.failure = "token_ongeldig"
            raise ProofRefusedError("token_ongeldig", str(exc)) from exc
        _check_identity(intent, person, facts)
        fresh = facts.fresh_at(moment)
        if not fresh and (
            await instance_settings.get(db, STALE_AUTHENTICATION.key) == STALE_REFUSE
        ):
            intent.failure = "aanmelding_niet_vers"
            raise ProofRefusedError(
                "aanmelding_niet_vers",
                "De identiteitsprovider heeft je niet opnieuw laten inloggen. "
                "Deze instantie legt een besluit dan niet vast.",
            )
        authentication = Authentication(
            requested=dict(REAUTHENTICATION),
            client_id=provider.client_id,
            auth_time=facts.auth_time,
            fresh=fresh,
            age_seconds=facts.age_at(moment),
            acr=facts.acr,
            amr=facts.amr,
            id_token_sha256=sha256_hex(id_token.encode("ascii")),
            nonce_inputs=dict(intent.nonce_inputs),
        )
    else:
        id_token = None
        provider = None
        authentication = Authentication(
            requested=None,
            client_id=None,
            auth_time=None,
            fresh=None,
            age_seconds=None,
            absent_reason=NO_PROVIDER,
        )

    kept = await quote_files.file_of(db, quote)
    if kept.sha256 != (intent.nonce_inputs.get("bestand_sha256") or ""):
        raise ProofRefusedError(
            "offerte_gewijzigd", "Het document van de offerte is intussen gewijzigd."
        )
    authority = await _authority(db, intent, person, moment.date())
    if authority.basis == "recht" and authority.since is None:
        intent.failure = "geen_recht"
        raise ProofRefusedError(
            "geen_recht",
            f"Je hebt het recht {authority.right} niet (meer) in deze instantie.",
        )
    on_behalf_of = intent.params.get("organisation")
    statement = build_statement(
        statement_id=str(uuid.uuid4()),
        action=intent.action,
        channel=intent.channel,
        quote_fingerprint=quote.snapshot_hash,
        quote_reference=quote.reference,
        quote_uri=quote.uri,
        quote_total_cents=quote.total_cents,
        document_sha256=kept.sha256,
        document_fixed=kept.origin_text,
        subject=facts.subject if facts else None,
        issuer=facts.issuer if facts else None,
        name=(person.name if person is not None else None)
        or (facts.name if facts else None)
        or intent.params.get("signer_name")
        or intent.email,
        email=intent.email,
        email_verified=facts.email_verified if facts else None,
        function=(intent.params.get("signer_function") or "").strip() or None,
        organisation_claimed=_organisation_claims(facts.claims) if facts else None,
        on_behalf_of=on_behalf_of if isinstance(on_behalf_of, dict) else None,
        received_at=moment,
        authentication=authentication,
        authority=authority,
        instance_name=settings.INSTANCE_NAME,
        instance_base_uri=settings.INSTANCE_BASE_URI,
        note=(intent.params.get("note") or "").strip() or None,
    )
    signed = sign_statement(
        statement, private_key=signing_key.private_key, kid=signing_key.kid
    )
    reply, authority_url = await _timestamp(db, signed.canonical, http_client)

    evidence = DecisionEvidence(
        id=uuid.uuid4(),
        action=intent.action,
        channel=intent.channel,
        quote_id=quote.id,
        quote_hash=quote.snapshot_hash,
        statement=signed.canonical,
        statement_hash=signed.hash,
        statement_jws=signed.jws,
        id_token=id_token,
        idp_jwks=provider.jwks if provider else None,
        idp_discovery=provider.discovery if provider else None,
        instance_jwks=instance_jwks,
        timestamp_reply=reply,
        timestamp_authority=authority_url,
        person_id=person.id if person is not None else None,
        email=intent.email,
    )
    db.add(evidence)
    await db.flush()
    # The stream of events can point at the proof: the statement is named by
    # its hash. Nothing of its content goes in, and no personal value.
    record_audit(
        db,
        actor=person,
        action=CREATE,
        entity="decision_evidence",
        entity_id=evidence.id,
        new_value={
            "statement_hash": signed.hash,
            "decision": intent.action,
            "channel": intent.channel,
            "quote_id": str(quote.id),
            "quote_hash": quote.snapshot_hash,
            "document_sha256": kept.sha256,
            "identity_statement": id_token is not None,
            "timestamp": reply is not None,
        },
    )

    # The decision is carried out with what the statement says, read back
    # from the bytes that were signed.
    values = columns(parse_statement(signed.canonical))
    await execute(db, intent, quote, person, values, evidence)

    intent.completed_at = moment
    intent.evidence_id = evidence.id
    await db.flush()
    return Completed(evidence=evidence, statement=statement)


async def bundle_of(
    db: AsyncSession, evidence: DecisionEvidence, settings: Settings
) -> dict[str, Any]:
    """The bundle for a stored decision: what both parties keep."""
    quote = await db.get(Quote, evidence.quote_id)
    if quote is None:
        raise NotFoundError("Offerte", evidence.quote_id)
    statement = parse_statement(bytes(evidence.statement))
    # A statement from before files were kept cites none; then none is put
    # in, rather than a file the decision was not about.
    kept = (
        await quote_files.file_of(db, quote)
        if statement["offerte"].get("bestand_sha256")
        else None
    )
    return build_bundle(
        quote_canonical=bytes(quote.canonical),
        quote_fingerprint=quote.snapshot_hash,
        quote_reference=quote.reference,
        quote_uri=quote.uri,
        document=kept.content if kept else None,
        document_sha256=kept.sha256 if kept else None,
        document_fixed=kept.origin_text if kept else None,
        statement_jws=evidence.statement_jws,
        statement_hash=evidence.statement_hash,
        id_token=evidence.id_token,
        idp_jwks=evidence.idp_jwks,
        idp_discovery=evidence.idp_discovery,
        instance_name=settings.INSTANCE_NAME,
        instance_base_uri=settings.INSTANCE_BASE_URI,
        instance_jwks=evidence.instance_jwks,
        timestamp_reply=bytes(evidence.timestamp_reply)
        if evidence.timestamp_reply
        else None,
        timestamp_authority=evidence.timestamp_authority,
    )
