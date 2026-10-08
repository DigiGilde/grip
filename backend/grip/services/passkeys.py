"""Passkeys: registering one, logging in with one, confirming a decision.

A passkey is registered by a person who is logged in through the identity
provider; the registration records which login that was. From then on it
serves two purposes:

- logging in again without the identity provider, for a limited time after
  the last login through it (``PASSKEY_LOGIN_MAX_AGE_DAYS``);
- confirming a decision on a quote: the device signs a challenge computed
  from the decision, and the assertion becomes part of the proof
  (``grip.proof.passkey``).

Every ceremony asks the device to verify its user. A passkey that is
withdrawn keeps its row, so what was confirmed with it stays checkable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.core.config import Settings
from grip.models.decision_proof import SigningIntent
from grip.models.passkey import PasskeyCredential
from grip.models.person import Person
from grip.proof.jose import b64url, b64url_decode
from grip.proof.passkey import (
    PasskeyError,
    check_assertion,
    compute_challenge,
    statement_element,
)
from grip.repositories.passkey import PasskeyRepository
from grip.repositories.person import PersonRepository
from grip.services.errors import DomainValidationError, NotFoundError

MAX_PASSKEYS_PER_PERSON = 10
ENTITY = "passkey_credential"
CEREMONY_TIMEOUT_MS = 60_000

REFUSED = "De passkey is niet geaccepteerd."


class PasskeyRefusedError(Exception):
    """A ceremony failed. The message is safe to show; it names no cause
    that would help someone guess which passkeys exist."""

    def __init__(self, message: str = REFUSED) -> None:
        super().__init__(message)
        self.message = message


def configured(settings: Settings) -> bool:
    return bool(settings.PASSKEY_RP_ID and settings.PASSKEY_ORIGIN)


def login_enabled(settings: Settings) -> bool:
    """Whether a passkey alone can start a session in this instance."""
    return (
        configured(settings)
        and bool(settings.OIDC_ISSUER)
        and settings.PASSKEY_LOGIN_MAX_AGE_DAYS > 0
    )


def _parse(credential: str | dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(credential) if isinstance(credential, str) else credential
    except ValueError as exc:
        raise PasskeyRefusedError() from exc
    if not isinstance(value, dict):
        raise PasskeyRefusedError()
    return value


def _credential_id_of(assertion: dict[str, Any]) -> bytes:
    raw = assertion.get("rawId") or assertion.get("id")
    if not isinstance(raw, str) or not raw:
        raise PasskeyRefusedError()
    try:
        return b64url_decode(raw)
    except ValueError as exc:
        raise PasskeyRefusedError() from exc


# -- registering -------------------------------------------------------------


async def registration_options(
    db: AsyncSession, person: Person, settings: Settings
) -> tuple[str, str]:
    """The options for ``navigator.credentials.create`` and the challenge.

    Returns the options as JSON and the challenge as hex; the caller keeps
    the challenge in the session until the device answers.
    """
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    repo = PasskeyRepository(db)
    if await repo.count_of_person(person.id) >= MAX_PASSKEYS_PER_PERSON:
        raise DomainValidationError(
            f"Je hebt al {MAX_PASSKEYS_PER_PERSON} passkeys. Trek er eerst een in."
        )
    existing = await repo.of_person(person.id, include_revoked=True)
    options = generate_registration_options(
        rp_id=settings.PASSKEY_RP_ID,
        rp_name=settings.PASSKEY_RP_NAME,
        user_name=person.email or person.name,
        user_id=person.id.bytes,
        user_display_name=person.name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(c.credential_id)) for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Discoverable: logging in needs no name first, so nothing on the
            # login page says who has a passkey.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        timeout=CEREMONY_TIMEOUT_MS,
    )
    return options_to_json(options), options.challenge.hex()


async def register(
    db: AsyncSession,
    person: Person,
    settings: Settings,
    *,
    credential: str | dict[str, Any],
    challenge_hex: str,
    label: str,
    login: dict[str, Any],
    now: datetime | None = None,
) -> PasskeyCredential:
    """Check what the device made and keep the public key.

    ``login`` describes the login the session rests on (issuer, subject and
    time of authentication, or why there is none). It becomes part of the
    registration record.
    """
    from webauthn import verify_registration_response
    from webauthn.helpers.exceptions import WebAuthnException

    moment = now or datetime.now(UTC)
    try:
        verified = verify_registration_response(
            credential=_parse(credential),
            expected_challenge=bytes.fromhex(challenge_hex),
            expected_rp_id=settings.PASSKEY_RP_ID,
            expected_origin=settings.PASSKEY_ORIGIN,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        raise PasskeyRefusedError(
            "De passkey kon niet worden vastgelegd. Probeer het opnieuw."
        ) from exc

    repo = PasskeyRepository(db)
    if await repo.by_credential_id(verified.credential_id) is not None:
        raise DomainValidationError("Deze passkey is al vastgelegd.")
    name = label.strip() or "Passkey"
    passkey = PasskeyCredential(
        person_id=person.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        label=name[:100],
        aaguid=str(verified.aaguid) if verified.aaguid else None,
        device_type=getattr(verified.credential_device_type, "value", None),
        backed_up=bool(verified.credential_backed_up),
        registration={
            "rp_id": settings.PASSKEY_RP_ID,
            "origin": settings.PASSKEY_ORIGIN,
            "aanmelding": login,
        },
        oidc_seen_at=moment if login.get("uitgever") else None,
    )
    db.add(passkey)
    await db.flush()
    record_audit(
        db,
        actor=person,
        action=CREATE,
        entity=ENTITY,
        entity_id=passkey.id,
        person_id=person.id,
        new_value={
            "label": passkey.label,
            "credential_id": b64url(passkey.credential_id),
            "device_type": passkey.device_type,
            "backed_up": passkey.backed_up,
        },
    )
    return passkey


def login_of_session(session: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """The login a session rests on, for the registration record.

    Read from the ID token the identity provider issued at login. The token
    came straight from the provider over TLS when the session began; it is
    read here, not verified again.
    """
    token = session.get("id_token")
    if isinstance(token, str) and token.count(".") == 2:
        try:
            claims = json.loads(b64url_decode(token.split(".")[1]))
        except ValueError:
            claims = {}
        moment = claims.get("auth_time") or claims.get("iat")
        return {
            "uitgever": claims.get("iss"),
            "subject": claims.get("sub"),
            "aangemeld_op": datetime.fromtimestamp(moment, UTC).isoformat()
            if isinstance(moment, int | float)
            else None,
        }
    return {
        "uitgever": None,
        "subject": None,
        "aangemeld_op": None,
        "ontbreekt_omdat": "deze instantie draait zonder identiteitsprovider "
        "(lokale ontwikkeling)"
        if not settings.OIDC_ISSUER
        else "de sessie berustte niet op een aanmelding bij de identiteitsprovider",
    }


# -- withdrawing --------------------------------------------------------------


async def revoke(
    db: AsyncSession, passkey: PasskeyCredential, *, actor: Person
) -> PasskeyCredential:
    if passkey.revoked_at is not None:
        return passkey
    passkey.revoked_at = datetime.now(UTC)
    passkey.revoked_by_id = actor.id
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity=ENTITY,
        entity_id=passkey.id,
        person_id=passkey.person_id,
        old_value={"revoked": False},
        new_value={
            "revoked": True,
            "label": passkey.label,
            "by_owner": actor.id == passkey.person_id,
        },
    )
    return passkey


async def get_own(
    db: AsyncSession, passkey_id: UUID, person: Person
) -> PasskeyCredential:
    passkey = await PasskeyRepository(db).get(passkey_id)
    if passkey is None or passkey.person_id != person.id or passkey.revoked_at:
        raise NotFoundError("Passkey", passkey_id)
    return passkey


# -- logging in ---------------------------------------------------------------


def login_options(settings: Settings) -> tuple[str, str]:
    """Options for logging in. No credential is named: the device offers
    the passkeys it holds for this host."""
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement

    options = generate_authentication_options(
        rp_id=settings.PASSKEY_RP_ID,
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=CEREMONY_TIMEOUT_MS,
    )
    return options_to_json(options), options.challenge.hex()


async def _assert(
    db: AsyncSession,
    settings: Settings,
    assertion: dict[str, Any],
    challenge: bytes,
    *,
    moment: datetime,
    owner_id: UUID | None = None,
) -> PasskeyCredential:
    """The passkey behind an assertion, after checking the assertion.

    With ``owner_id`` the passkey must be that person's. Nothing is changed
    on the row until every check has passed.
    """
    passkey = await PasskeyRepository(db).by_credential_id(_credential_id_of(assertion))
    if passkey is None or passkey.revoked_at is not None:
        raise PasskeyRefusedError()
    if owner_id is not None and passkey.person_id != owner_id:
        raise PasskeyRefusedError()
    try:
        facts = check_assertion(
            assertion,
            public_key_cose=bytes(passkey.public_key),
            challenge=challenge,
            rp_id=settings.PASSKEY_RP_ID,
            origin=settings.PASSKEY_ORIGIN,
            current_sign_count=passkey.sign_count,
        )
    except PasskeyError as exc:
        raise PasskeyRefusedError() from exc
    passkey.sign_count = facts.sign_count
    passkey.last_used_at = moment
    return passkey


async def login(
    db: AsyncSession,
    settings: Settings,
    *,
    credential: str | dict[str, Any],
    challenge_hex: str,
    now: datetime | None = None,
) -> Person:
    """The person a passkey logs in, or ``PasskeyRefusedError``.

    Refused for an inactive person, and when the person's last login
    through the identity provider is too long ago: the provider decides who
    still belongs, and a key must not outlive that for long.
    """
    if not login_enabled(settings):
        raise PasskeyRefusedError()
    moment = now or datetime.now(UTC)
    passkey = await _assert(
        db, settings, _parse(credential), bytes.fromhex(challenge_hex), moment=moment
    )
    person = await PersonRepository(db).get(passkey.person_id)
    if person is None or not person.is_active:
        raise PasskeyRefusedError()
    limit = timedelta(days=settings.PASSKEY_LOGIN_MAX_AGE_DAYS)
    if passkey.oidc_seen_at is None or moment - passkey.oidc_seen_at > limit:
        raise PasskeyRefusedError(
            "Log eerst in via de gewone weg. Daarna werkt je passkey weer."
        )
    await db.flush()
    record_audit(
        db,
        actor=person,
        action=UPDATE,
        entity=ENTITY,
        entity_id=passkey.id,
        person_id=person.id,
        new_value={"used_for": "login"},
    )
    return person


async def note_oidc_login(
    db: AsyncSession, person: Person, *, now: datetime | None = None
) -> None:
    """The person logged in through the identity provider just now."""
    passkeys = await PasskeyRepository(db).of_person(person.id)
    if not passkeys:
        return
    moment = now or datetime.now(UTC)
    for passkey in passkeys:
        passkey.oidc_seen_at = moment
    await db.flush()
    record_audit(
        db,
        actor=person,
        action=UPDATE,
        entity=ENTITY,
        entity_id=passkeys[0].id,
        person_id=person.id,
        new_value={"oidc_login_seen": True, "passkeys": len(passkeys)},
    )


# -- confirming a decision ------------------------------------------------------


async def available_for(
    db: AsyncSession, person: Person | None, settings: Settings
) -> bool:
    """Whether this person can confirm a decision with a passkey."""
    if person is None or not configured(settings):
        return False
    return await PasskeyRepository(db).count_of_person(person.id) > 0


async def decision_options(
    db: AsyncSession, intent: SigningIntent, person: Person, settings: Settings
) -> str:
    """Options for confirming the decision of ``intent`` with a passkey.

    The challenge is computed from the decision, so what the device signs
    fits this quote, this file and this decision and nothing else.
    """
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )

    passkeys = await PasskeyRepository(db).of_person(person.id)
    if not passkeys or not configured(settings):
        raise DomainValidationError("Je hebt geen passkey om mee te bevestigen.")
    options = generate_authentication_options(
        rp_id=settings.PASSKEY_RP_ID,
        challenge=compute_challenge(intent.nonce_inputs),
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(p.credential_id)) for p in passkeys
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=CEREMONY_TIMEOUT_MS,
    )
    return options_to_json(options)


async def confirm_decision(
    db: AsyncSession,
    intent: SigningIntent,
    person: Person,
    settings: Settings,
    *,
    credential: str | dict[str, Any],
    now: datetime | None = None,
) -> PasskeyCredential:
    """Check the assertion for this decision and keep it with the intent.

    The decision itself is made later, when the person comes back from the
    identity provider (``grip.proof.flow.complete_intent``); the assertion
    then goes into the statement and the evidence.
    """
    moment = now or datetime.now(UTC)
    if intent.completed_at is not None or intent.expires_at < moment:
        raise DomainValidationError(
            "Het duurde te lang tussen de knop en het bevestigen. Begin opnieuw."
        )
    assertion = _parse(credential)
    passkey = await _assert(
        db,
        settings,
        assertion,
        compute_challenge(intent.nonce_inputs),
        moment=moment,
        owner_id=person.id,
    )
    intent.passkey = {
        "passkey_id": str(passkey.id),
        "assertion": assertion,
        "bevestigd_op": moment.isoformat(),
    }
    await db.flush()
    record_audit(
        db,
        actor=person,
        action=UPDATE,
        entity=ENTITY,
        entity_id=passkey.id,
        person_id=person.id,
        new_value={
            "used_for": "decision",
            "quote_id": str(intent.quote_id),
            "quote_hash": intent.quote_hash,
        },
    )
    return passkey


async def element_for(
    db: AsyncSession, intent: SigningIntent, settings: Settings
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """What the statement says about the passkey of ``intent``, and the
    assertion itself for the evidence. None when no passkey was used."""
    kept = intent.passkey
    if not isinstance(kept, dict) or not kept.get("assertion"):
        return None
    passkey = await PasskeyRepository(db).get(UUID(kept["passkey_id"]))
    if passkey is None:
        return None
    assertion = kept["assertion"]
    element = statement_element(
        credential_id=bytes(passkey.credential_id),
        public_key_cose=bytes(passkey.public_key),
        rp_id=settings.PASSKEY_RP_ID,
        origin=settings.PASSKEY_ORIGIN,
        challenge_inputs=intent.nonce_inputs,
        assertion=assertion,
        registered_at=passkey.created_at,
        registration=dict(passkey.registration.get("aanmelding") or {}),
        confirmed_at=datetime.fromisoformat(kept["bevestigd_op"]),
    )
    return element, assertion
