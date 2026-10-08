"""Deciding with proof, and getting the proof out.

A decision (accepting or rejecting a quote, approving it internally or
sending it back) takes three steps for a screen:

1. ``POST .../intents`` with what is decided. The answer holds
   ``authorize_url``.
2. The browser navigates to ``authorize_url`` (a full page load, not a
   fetch). With an identity provider the person logs in again there, for
   this decision; without one (local development) this step is immediate.
3. The browser comes back on ``return_path`` with ``?bewijs=<id>`` when the
   decision was made, or ``?besluit_fout=<code>`` when it was not.

The evidence is then available as a bundle (a file both parties keep), as a
page a person reads, and as a summary with what is proven and what is not.

Two prefixes, because an invited signer without a person record only
reaches ``/api/signing/``:

- ``/api/signing/...``: the signing link, for a person or a guest.
- ``/api/proof/...``: decisions by a person of this instance (accepting a
  received quote, internal approval), and checking any bundle.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, Decider, Resource, Subject
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.access.guest_deps import CurrentSigner, Signer, get_signer
from grip.core.auth import (
    CurrentPerson,
    get_http_client,
    get_jwks_document,
    get_oauth,
    get_oidc_metadata,
    resolve_person,
)
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.federation import signing
from grip.federation.bridge.organisations import own_reference
from grip.models.assignment import Assignment
from grip.models.decision_proof import DecisionEvidence, SigningIntent
from grip.models.person import Person
from grip.models.quote import Quote
from grip.proof import flow
from grip.proof.bundle import BUNDLE_MEDIA_TYPE, render_page
from grip.proof.decisions import execute
from grip.proof.statement import parse_statement
from grip.proof.verify import verify_bundle
from grip.services import passkeys, quote_views
from grip.services.errors import DomainError, DomainValidationError, NotFoundError

logger = logging.getLogger(__name__)

signing_router = APIRouter(prefix="/signing", tags=["proof"])
router = APIRouter(prefix="/proof", tags=["proof"])

# Session key while the person is at the identity provider for a decision:
# {"intent": <id>, "state": <state of the authorization request>}.
PROOF_SESSION_KEY = "proof"
RESULT_PARAM = "bewijs"
ERROR_PARAM = "besluit_fout"

A = DataClass.ASSIGNMENT_BASIC


# --- shapes ------------------------------------------------------------------


class SigningIntentIn(BaseModel):
    """What an invited signer decides about the quote they were shown."""

    decision: Literal["accept", "reject"]
    quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    signer_function: str | None = Field(default=None, max_length=255)
    # The signer declares to be authorised to sign for the client.
    confirm_mandate: bool = False
    organisation_name: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=5000)
    # Where in the application to come back to.
    return_path: str | None = Field(default=None, max_length=500)


class DecisionIntentIn(BaseModel):
    """A decision by a person of this instance."""

    kind: Literal["accept_received", "reject_received", "approve", "send_back"]
    quote_id: UUID
    quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    signer_function: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=5000)
    return_path: str | None = Field(default=None, max_length=500)


def _safe_path(raw: str | None, default: str) -> str:
    """A path inside the application; anything else becomes the default."""
    from grip.api.routes.auth import safe_next_path

    return safe_next_path(raw) or default


def _intent_out(
    intent: SigningIntent, prefix: str, settings: Settings
) -> dict[str, Any]:
    return {
        "id": intent.id,
        # Navigate the browser here; it is not an address to fetch.
        "authorize_url": f"/api/{prefix}/intents/{intent.id}/authorize",
        "expires_at": intent.expires_at,
        # False in an instance without an identity provider: the step is
        # immediate and the evidence says nobody vouched for the identity.
        "reauthentication": flow.reauthentication_required(settings),
        "result_param": RESULT_PARAM,
        "error_param": ERROR_PARAM,
    }


async def _intent_with_passkey(
    db: AsyncSession,
    intent: SigningIntent,
    prefix: str,
    settings: Settings,
    person: Person | None,
) -> dict[str, Any]:
    """The intent, with whether this person can confirm it with a passkey.

    When ``passkey`` is not None the screen asks the device first (options,
    then the assertion) and navigates to ``authorize_url`` afterwards. It is
    an addition: skipping it, or a device that refuses, leaves the decision
    possible exactly as without a passkey.
    """
    out = _intent_out(intent, prefix, settings)
    out["passkey"] = (
        {
            "options_url": f"/api/{prefix}/intents/{intent.id}/passkey/options",
            "verify_url": f"/api/{prefix}/intents/{intent.id}/passkey",
        }
        if await passkeys.available_for(db, person, settings)
        else None
    )
    return out


# --- creating an intent --------------------------------------------------------


@signing_router.post(
    "/quotes/{quote_id}/intents",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def create_signing_intent(
    quote_id: UUID,
    body: SigningIntentIn,
    signer: CurrentSigner,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """An invited signer is about to accept or reject the quote."""
    from grip.api.routes.signing import invited_quote

    quote, resource = await invited_quote(db, decider, signer, quote_id)
    await require(decider, signer.subject, Action.ACCEPT_QUOTE, resource)
    if body.decision == "accept" and not body.confirm_mandate:
        raise DomainValidationError(
            "Bevestig dat je namens de opdrachtgever mag tekenen."
        )
    assignment = await db.get(Assignment, quote.assignment_id)
    if assignment is None:
        raise NotFoundError("Opdracht", quote.assignment_id)
    # On whose behalf: the client of the assignment, as an acceptance
    # through the signing link has always recorded it.
    organisation = await quote_views.client_reference(
        db, assignment, body.organisation_name or signer.name
    )
    person = await db.get(Person, signer.person_id) if signer.person_id else None
    intent = await flow.create_intent(
        db,
        action=body.decision,
        channel="signing_link",
        quote=quote,
        quote_hash=body.quote_hash,
        person=person,
        email=signer.email,
        params={
            "signer_name": signer.name,
            "signer_function": body.signer_function,
            "confirm_mandate": body.confirm_mandate,
            "organisation": organisation,
            "note": body.reason,
        },
        return_path=_safe_path(body.return_path, f"/tekenen/{quote.id}"),
    )
    return await _intent_with_passkey(db, intent, "signing", settings, person)


_KINDS = {
    "accept_received": ("own_instance", "accept"),
    "reject_received": ("own_instance", "reject"),
    "approve": ("internal", "approve"),
    "send_back": ("internal", "send_back"),
}


async def _authorise_person(
    db: AsyncSession, decider: Decider, subject: Subject, quote: Quote, channel: str
) -> None:
    """The same question the direct routes ask before this decision."""
    if channel == "own_instance":
        await require(
            decider,
            subject,
            Action.ACCEPT_QUOTE,
            Resource.quote(quote.id, quote.assignment_id),
            hide_existence=True,
        )
        return
    from grip.api.routes.quote_approvals import approval_resource

    resource = await approval_resource(db, quote)
    await require(decider, subject, Action.READ, resource, A, hide_existence=True)
    await require(decider, subject, Action.DECIDE_QUOTE_APPROVAL, resource)


@router.post("/intents", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_decision_intent(
    body: DecisionIntentIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """A person of this instance is about to decide on a quote."""
    channel, action = _KINDS[body.kind]
    quote = await db.get(Quote, body.quote_id)
    if quote is None:
        raise NotFoundError("Offerte", body.quote_id)
    await _authorise_person(db, decider, subject, quote, channel)
    if action == "send_back" and not (body.note or "").strip():
        raise DomainValidationError(
            "Geef bij terugsturen aan wat er anders moet, zodat de maker verder kan."
        )
    default = (
        f"/ontvangen-offertes/{quote.id}"
        if channel == "own_instance"
        else f"/opdrachten/{quote.assignment_id}/offerte"
    )
    intent = await flow.create_intent(
        db,
        action=action,
        channel=channel,
        quote=quote,
        quote_hash=body.quote_hash,
        person=person,
        email=person.email,
        params={
            "signer_function": body.signer_function,
            "organisation": own_reference(settings),
            "note": body.note,
        },
        return_path=_safe_path(body.return_path, default),
    )
    return await _intent_with_passkey(db, intent, "proof", settings, person)


# --- to the identity provider and back ------------------------------------------


def _redirect(settings: Settings, path: str, **params: str) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    url = f"{settings.FRONTEND_URL.rstrip('/')}{path}{separator}{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


def _undo_and_go_back(settings: Settings, path: str, code: str) -> HTTPException:
    """A refused decision: nothing of it is kept, and the browser goes back.

    Raised rather than returned. An exception ends the request's
    transaction with a rollback, so a decision that was refused halfway
    leaves no statement and no half-made record behind. The response is
    still the redirect into the application, with the reason.
    """
    separator = "&" if "?" in path else "?"
    url = (
        f"{settings.FRONTEND_URL.rstrip('/')}{path}{separator}"
        f"{urlencode({ERROR_PARAM: code})}"
    )
    return HTTPException(status_code=302, detail=code, headers={"Location": url})


def _owns(intent: SigningIntent, person_id: UUID | None, email: str) -> bool:
    if intent.person_id is not None:
        return intent.person_id == person_id
    return person_id is None and intent.email == email.strip().lower()


async def _finish(
    db: AsyncSession,
    intent: SigningIntent,
    settings: Settings,
    *,
    id_token: str | None,
) -> RedirectResponse:
    """Complete the intent and send the browser back to the application."""
    key = signing.get_signing_key(settings)
    if key is None:
        logger.error("No signing key: a decision cannot be stated")
        return _redirect(settings, intent.return_path, **{ERROR_PARAM: "geen_sleutel"})
    provider = None
    if id_token is not None:
        discovery = await get_oidc_metadata(settings)
        jwks = await get_jwks_document(settings)
        if not discovery or not jwks:
            return _redirect(
                settings, intent.return_path, **{ERROR_PARAM: "provider_onbereikbaar"}
            )
        provider = flow.IdentityProvider(
            issuer=settings.OIDC_ISSUER,
            client_id=settings.OIDC_CLIENT_ID,
            jwks=jwks,
            discovery=discovery,
        )
    return_path = intent.return_path
    try:
        completed = await flow.complete_intent(
            db,
            intent,
            settings=settings,
            signing_key=key,
            instance_jwks=signing.own_jwks(settings),
            execute=execute,
            id_token=id_token,
            provider=provider,
            http_client=get_http_client(),
        )
    except flow.ProofRefusedError as exc:
        logger.info("Decision refused: %s", exc.code)
        raise _undo_and_go_back(settings, return_path, exc.code) from exc
    except DomainError as exc:
        logger.info("Decision refused by the domain: %s", type(exc).__name__)
        raise _undo_and_go_back(settings, return_path, "geweigerd") from exc
    return _redirect(
        settings, return_path, **{RESULT_PARAM: str(completed.evidence.id)}
    )


async def _authorize(
    request: Request,
    intent: SigningIntent,
    db: AsyncSession,
    settings: Settings,
) -> Response:
    if intent.completed_at is not None or intent.expires_at < datetime.now(
        intent.expires_at.tzinfo
    ):
        return _redirect(settings, intent.return_path, **{ERROR_PARAM: "verlopen"})
    if not flow.reauthentication_required(settings):
        return await _finish(db, intent, settings, id_token=None)

    from grip.api.routes.auth import _callback_url

    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(status_code=501, detail="Inloggen is niet geconfigureerd")
    state = secrets.token_urlsafe(24)
    request.session[PROOF_SESSION_KEY] = {"intent": str(intent.id), "state": state}
    return await oauth.keycloak.authorize_redirect(
        request,
        _callback_url(request, settings),
        state=state,
        **flow.authorization_params(intent),
    )


@signing_router.get("/intents/{intent_id}/authorize", response_model=None)
async def authorize_signing_intent(
    intent_id: UUID,
    request: Request,
    signer: CurrentSigner,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Send the signer to the identity provider for this decision."""
    intent = await flow.get_intent(db, intent_id)
    if intent.channel != "signing_link" or not _owns(
        intent, signer.person_id, signer.email
    ):
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return await _authorize(request, intent, db, settings)


@router.get("/intents/{intent_id}/authorize", response_model=None)
async def authorize_decision_intent(
    intent_id: UUID,
    request: Request,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Send the person to the identity provider for this decision."""
    intent = await flow.get_intent(db, intent_id)
    if intent.channel == "signing_link" or not _owns(intent, person.id, person.email):
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return await _authorize(request, intent, db, settings)


# --- confirming with a passkey, before going to the identity provider -----------


class PasskeyAssertionIn(BaseModel):
    # What navigator.credentials.get returned, as JSON.
    credential: str = Field(max_length=20000)


async def _own_intent(
    db: AsyncSession, intent_id: UUID, person: Person, *, signing_link: bool
) -> SigningIntent:
    intent = await flow.get_intent(db, intent_id)
    if (intent.channel == "signing_link") != signing_link or not _owns(
        intent, person.id, person.email
    ):
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return intent


async def _passkey_options(
    db: AsyncSession, intent: SigningIntent, person: Person, settings: Settings
) -> dict[str, str]:
    return {
        "options_json": await passkeys.decision_options(db, intent, person, settings)
    }


async def _passkey_confirm(
    db: AsyncSession,
    intent: SigningIntent,
    person: Person,
    settings: Settings,
    body: PasskeyAssertionIn,
) -> dict[str, bool]:
    try:
        await passkeys.confirm_decision(
            db, intent, person, settings, credential=body.credential
        )
    except passkeys.PasskeyRefusedError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return {"confirmed": True}


@router.post("/intents/{intent_id}/passkey/options", response_model=None)
async def decision_passkey_options(
    intent_id: UUID,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """The challenge a passkey signs for this decision."""
    intent = await _own_intent(db, intent_id, person, signing_link=False)
    return await _passkey_options(db, intent, person, settings)


@router.post("/intents/{intent_id}/passkey", response_model=None)
async def decision_passkey_confirm(
    intent_id: UUID,
    body: PasskeyAssertionIn,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    """Check what the passkey signed and keep it with the decision."""
    intent = await _own_intent(db, intent_id, person, signing_link=False)
    return await _passkey_confirm(db, intent, person, settings, body)


async def _signer_person(db: AsyncSession, signer: Signer) -> Person:
    """A passkey belongs to a person of this instance; a guest has none."""
    person = await db.get(Person, signer.person_id) if signer.person_id else None
    if person is None:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return person


@signing_router.post("/intents/{intent_id}/passkey/options", response_model=None)
async def signing_passkey_options(
    intent_id: UUID,
    signer: CurrentSigner,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    person = await _signer_person(db, signer)
    intent = await _own_intent(db, intent_id, person, signing_link=True)
    return await _passkey_options(db, intent, person, settings)


@signing_router.post("/intents/{intent_id}/passkey", response_model=None)
async def signing_passkey_confirm(
    intent_id: UUID,
    body: PasskeyAssertionIn,
    signer: CurrentSigner,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    person = await _signer_person(db, signer)
    intent = await _own_intent(db, intent_id, person, signing_link=True)
    return await _passkey_confirm(db, intent, person, settings, body)


def pending_intent(request: Request) -> dict[str, str] | None:
    """The decision this callback belongs to, or None for a normal login.

    Only when the state of the request is the state stored with the intent:
    a decision that was abandoned at the provider must not capture a later,
    ordinary login.
    """
    pending = request.session.get(PROOF_SESSION_KEY)
    if not isinstance(pending, dict):
        return None
    state = request.query_params.get("state")
    if not state or pending.get("state") != state:
        return None
    return pending


async def finish_after_login(
    request: Request,
    db: AsyncSession,
    settings: Settings,
    pending: dict[str, str],
) -> RedirectResponse:
    """The identity provider sent the person back for a decision.

    Called by the login callback. The session stays as it was: this is not
    a login, and whoever comes back must be whoever left.
    """
    session = request.session
    session.pop(PROOF_SESSION_KEY, None)
    intent = await db.get(SigningIntent, UUID(pending["intent"]))
    if intent is None:
        return _redirect(settings, "/", **{ERROR_PARAM: "verlopen"})

    oauth = get_oauth(settings)
    assert oauth is not None
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except OAuthError as exc:
        logger.warning("Re-authentication for a decision failed: %s", exc.error)
        intent.failure = "aanmelding_mislukt"
        await db.flush()
        return _redirect(
            settings, intent.return_path, **{ERROR_PARAM: "aanmelding_mislukt"}
        )

    # Whoever holds the session now must be whoever started the decision.
    try:
        signer: Signer = await get_signer(request, db, settings)
    except HTTPException:
        return _redirect(settings, intent.return_path, **{ERROR_PARAM: "niet_ingelogd"})
    person = await resolve_person(request, db, settings)
    if not _owns(intent, person.id if person else None, signer.email):
        return _redirect(
            settings, intent.return_path, **{ERROR_PARAM: "andere_persoon"}
        )

    id_token = token.get("id_token")
    if not isinstance(id_token, str):
        return _redirect(
            settings, intent.return_path, **{ERROR_PARAM: "token_ongeldig"}
        )
    return await _finish(db, intent, settings, id_token=id_token)


# --- the evidence ------------------------------------------------------------------


async def _evidence(db: AsyncSession, evidence_id: UUID) -> DecisionEvidence:
    evidence = await db.get(DecisionEvidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return evidence


async def _evidence_for_signer(
    db: AsyncSession, evidence_id: UUID, signer: Signer
) -> DecisionEvidence:
    """The evidence of a decision this signer made themselves."""
    evidence = await _evidence(db, evidence_id)
    own = (
        evidence.person_id == signer.person_id
        if evidence.person_id is not None
        else signer.person_id is None and evidence.email == signer.email
    )
    if evidence.channel != "signing_link" or not own:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return evidence


async def _evidence_for_person(
    db: AsyncSession,
    evidence_id: UUID,
    person: Person,
    decider: Decider,
    subject: Subject,
) -> DecisionEvidence:
    """The evidence, for who decided or who may read the quote it is about."""
    evidence = await _evidence(db, evidence_id)
    if evidence.person_id == person.id:
        return evidence
    quote = await db.get(Quote, evidence.quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    # An internal approval is knowledge of whoever may read the quote in
    # full; the names in it are of colleagues.
    await require(
        decider,
        subject,
        Action.READ,
        Resource.quote(quote.id, quote.assignment_id),
        DataClass.ASSIGNMENT_FINANCIAL,
        hide_existence=True,
    )
    return evidence


async def _summary(
    db: AsyncSession, evidence: DecisionEvidence, settings: Settings
) -> dict[str, Any]:
    bundle = await flow.bundle_of(db, evidence, settings)
    report = verify_bundle(bundle)
    statement = parse_statement(bytes(evidence.statement))
    return {
        "id": evidence.id,
        "statement_hash": evidence.statement_hash,
        "decision": evidence.action,
        "channel": evidence.channel,
        "quote_id": evidence.quote_id,
        "statement": statement,
        "sound": report.sound,
        "proven": report.of("bewezen"),
        "not_proven": report.of("niet_bewezen"),
        "wrong": report.of("fout"),
        "has_identity_statement": evidence.id_token is not None,
        "has_timestamp": evidence.timestamp_reply is not None,
    }


def _download(bundle: dict[str, Any], evidence: DecisionEvidence) -> Response:
    import json

    name = f"bewijs-{evidence.statement_hash[:12]}.json"
    return Response(
        content=json.dumps(bundle, ensure_ascii=False, indent=2),
        media_type=BUNDLE_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


def _page(bundle: dict[str, Any], evidence: DecisionEvidence) -> HTMLResponse:
    report = verify_bundle(bundle)
    statement = parse_statement(bytes(evidence.statement))
    return HTMLResponse(
        render_page(statement, report.findings),
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "Cache-Control": "private, no-store",
        },
    )


@signing_router.get("/evidence/{evidence_id}", response_model=None)
async def signing_evidence(
    evidence_id: UUID,
    signer: CurrentSigner,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """What the signer's decision rests on, and what that proves."""
    return await _summary(
        db, await _evidence_for_signer(db, evidence_id, signer), settings
    )


@signing_router.get("/evidence/{evidence_id}/bundle")
async def signing_bundle(
    evidence_id: UUID,
    signer: CurrentSigner,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """The bundle, for the signer to keep: the same one this instance keeps."""
    evidence = await _evidence_for_signer(db, evidence_id, signer)
    return _download(await flow.bundle_of(db, evidence, settings), evidence)


@signing_router.get("/evidence/{evidence_id}/page")
async def signing_page(
    evidence_id: UUID,
    signer: CurrentSigner,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """The "Akkoordverklaring": the statement as a page to read and print."""
    evidence = await _evidence_for_signer(db, evidence_id, signer)
    return _page(await flow.bundle_of(db, evidence, settings), evidence)


@router.get("/evidence/{evidence_id}", response_model=None)
async def decision_evidence(
    evidence_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    evidence = await _evidence_for_person(db, evidence_id, person, decider, subject)
    return await _summary(db, evidence, settings)


@router.get("/evidence/{evidence_id}/bundle")
async def decision_bundle(
    evidence_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    evidence = await _evidence_for_person(db, evidence_id, person, decider, subject)
    return _download(await flow.bundle_of(db, evidence, settings), evidence)


@router.get("/evidence/{evidence_id}/page")
async def decision_page(
    evidence_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    evidence = await _evidence_for_person(db, evidence_id, person, decider, subject)
    return _page(await flow.bundle_of(db, evidence, settings), evidence)


@router.get("/quotes/{quote_id}/evidence", response_model=None)
async def quote_evidence(
    quote_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The decisions about a quote that have evidence, newest first."""
    from sqlalchemy import select

    quote = await db.get(Quote, quote_id)
    if quote is None:
        raise NotFoundError("Offerte", quote_id)
    await require(
        decider,
        subject,
        Action.READ,
        Resource.quote(quote.id, quote.assignment_id),
        DataClass.ASSIGNMENT_FINANCIAL,
        hide_existence=True,
    )
    rows = (
        await db.execute(
            select(DecisionEvidence)
            .where(DecisionEvidence.quote_id == quote_id)
            .order_by(DecisionEvidence.created_at.desc())
        )
    ).scalars()
    return {
        "items": [
            {
                "id": row.id,
                "decision": row.action,
                "channel": row.channel,
                "statement_hash": row.statement_hash,
                "created_at": row.created_at,
                "has_identity_statement": row.id_token is not None,
                "has_timestamp": row.timestamp_reply is not None,
            }
            for row in rows
        ]
    }


# A bundle holds a PDF and a quote in base64, a token and some keys: a few
# hundred kilobytes for a long quote. Anything far beyond that is not a
# bundle, and is refused before it is parsed.
MAX_BUNDLE_BYTES = 12 * 1024 * 1024


async def _uploaded_bundle(request: Request) -> dict[str, Any]:
    """The bundle in the request body, read with a limit on its size.

    The body is ``{"bundle": {...}}``. It is read by hand rather than
    through a schema so the limit applies before anything is parsed.
    """
    import json

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="De bundel is te groot.")
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > MAX_BUNDLE_BYTES:
            raise HTTPException(status_code=413, detail="De bundel is te groot.")
    try:
        body = json.loads(bytes(received))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(
            status_code=422, detail="De bundel is geen geldige JSON."
        ) from exc
    bundle = body.get("bundle") if isinstance(body, dict) else None
    if not isinstance(bundle, dict):
        raise HTTPException(
            status_code=422,
            detail="Stuur de bundel mee als het veld 'bundle'.",
        )
    return bundle


def _verified(bundle: dict[str, Any]) -> dict[str, Any]:
    report = verify_bundle(bundle)
    return {
        "sound": report.sound,
        "proven": report.of("bewezen"),
        "not_proven": report.of("niet_bewezen"),
        "wrong": report.of("fout"),
        "statement": report.statement,
    }


@router.post("/verify", response_model=None)
async def verify(request: Request, person: CurrentPerson) -> dict[str, Any]:
    """Check any bundle: the same check as the command, with no database.

    Nothing is looked up in this instance. A bundle of another instance, or
    one that was edited, gets the same treatment as one made here.
    """
    del person
    return _verified(await _uploaded_bundle(request))


@signing_router.post("/verify", response_model=None)
async def verify_as_signer(request: Request, signer: CurrentSigner) -> dict[str, Any]:
    """The same check, for whoever is signing: a person or an invited guest.

    Checking needs no right on anything: only what is in the uploaded
    bundle is looked at. It still asks for a session, and that is a
    decision, not an oversight. An endpoint without one would parse
    megabytes and verify signatures for anyone on the network, and this
    application has no rate limiter in front of it. Everyone who reaches
    the page that calls this has a session, as a person or as a guest; and
    whoever has neither does not need grip at all for this, which is the
    point: ``python -m grip.proof.verify`` checks a bundle on its own.
    """
    del signer
    return _verified(await _uploaded_bundle(request))
