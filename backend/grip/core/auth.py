"""OIDC authentication and the authorization dependencies for routes.

Users log in through Keycloak, which brokers SSO Rijk. Only ``sub``,
``email``, ``email_verified`` and ``name`` are read from the claims; what a
person may do is decided locally.

Access to an instance is pre-provisioned. A login succeeds only for an active
:class:`Person` that a beheerder created beforehand: matched on
``oidc_subject``, or on verified email for a person that is not bound to a
subject yet. There is no self-registration.

Without ``OIDC_ISSUER`` (local development with ``DEV_NO_AUTH``) there is no
login; requests run as the person picked with the dev cookie, or as the first
active beheerder.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx
from authlib.integrations.starlette_client import OAuth
from authlib.jose import JsonWebKey
from authlib.jose import jwt as authlib_jwt
from authlib.jose.errors import JoseError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.async_cache import AsyncTTLCache
from grip.core.audit import UPDATE, record_audit
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.events import stream
from grip.models.person import Person
from grip.models.role import BEHEERDER
from grip.repositories.person import PersonRepository, normalize_email

logger = logging.getLogger(__name__)

# Revalidate the access token against the identity provider at most this often.
_TOKEN_REVALIDATION_INTERVAL = 300

# If the identity provider is unreachable, allow sessions validated within
# this many seconds.
_NETWORK_ERROR_GRACE_SECONDS = 120

# Cookie set by the frontend's person picker in local development. Only read
# when no identity provider is configured, which Settings refuses outside
# local development.
DEV_PERSON_COOKIE = "grip_dev_person"

_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient, creating it on first call."""
    global _http_client  # noqa: PLW0603
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10)
    return _http_client


async def close_http_client() -> None:
    """Close the shared httpx client (called during app shutdown)."""
    global _http_client  # noqa: PLW0603
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def require_https(url: str, label: str, settings: Settings | None = None) -> bool:
    """Return True if credentials may be sent to this URL.

    That is https, or anything when the instance explicitly accepts a local
    identity provider over http (``OIDC_ALLOW_INSECURE_HTTP``, refused when
    deployed). Otherwise logs and returns False.
    """
    if url.startswith("https://"):
        return True
    if (settings or get_settings()).OIDC_ALLOW_INSECURE_HTTP:
        return True
    logger.warning("%s is not HTTPS, refusing to send credentials: %s", label, url)
    return False


class InsecureOidcEndpointError(RuntimeError):
    """The identity provider publishes endpoints over plain http."""


# The endpoints of the discovery document the application sends tokens to.
_OIDC_ENDPOINTS = (
    "jwks_uri",
    "userinfo_endpoint",
    "token_endpoint",
    "revocation_endpoint",
    "end_session_endpoint",
    "authorization_endpoint",
)


def insecure_oidc_endpoints(metadata: dict[str, Any]) -> list[str]:
    """Names of the endpoints in a discovery document that are not https."""
    return [
        name
        for name in _OIDC_ENDPOINTS
        if isinstance(metadata.get(name), str)
        and not metadata[name].lower().startswith("https://")
    ]


async def check_oidc_transport(settings: Settings) -> None:
    """Refuse to start when the provider's own endpoints are plain http.

    The issuer can be https while the discovery document points at http
    endpoints (a provider behind a proxy that does not know its public
    scheme). The login through the library would then work and every
    session check afterwards would fail, with only a warning in the log.

    A provider that cannot be reached at startup does not stop the
    application: that is an outage, not a configuration error, and the
    check runs again with every token validation.
    """
    if not settings.OIDC_ISSUER or settings.OIDC_ALLOW_INSECURE_HTTP:
        return
    metadata = await get_oidc_metadata(settings)
    if metadata is None:
        logger.warning("OIDC discovery document not reachable at startup")
        return
    insecure = insecure_oidc_endpoints(metadata)
    if insecure:
        raise InsecureOidcEndpointError(
            "De identiteitsprovider publiceert adressen zonder https ("
            + ", ".join(insecure)
            + "). Inloggen lijkt dan te lukken, maar geen enkele sessie is "
            "daarna geldig. Laat de provider zijn adressen met https "
            "publiceren, of zet voor lokale ontwikkeling met een eigen "
            "identiteitsprovider OIDC_ALLOW_INSECURE_HTTP=1."
        )


def _get_discovery_url(settings: Settings) -> str:
    """Prefer OIDC_DISCOVERY_URL (set by ZAD), else derive it from the issuer."""
    if settings.OIDC_DISCOVERY_URL:
        return settings.OIDC_DISCOVERY_URL
    return f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration"


# ---------------------------------------------------------------------------
# Cached OIDC discovery metadata and JWKS keys (1-hour TTL each)
# ---------------------------------------------------------------------------

_oidc_cache: AsyncTTLCache[dict[str, Any]] = AsyncTTLCache(ttl=3600)
_jwks_cache: AsyncTTLCache[Any] = AsyncTTLCache(ttl=3600)


async def get_oidc_metadata(settings: Settings) -> dict[str, Any] | None:
    """Return cached OIDC discovery metadata, fetching if stale."""
    if not settings.OIDC_ISSUER:
        return None

    cached = _oidc_cache.get_if_fresh()
    if cached is not None:
        return cached

    async with _oidc_cache.lock:
        cached = _oidc_cache.get_if_fresh()
        if cached is not None:
            return cached

        url = _get_discovery_url(settings)
        if not require_https(url, "OIDC discovery URL", settings):
            return None
        try:
            resp = await get_http_client().get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch OIDC metadata: %s", exc)
            return _oidc_cache.get_stale()
        metadata: dict[str, Any] = resp.json()
        _oidc_cache.set(metadata)
        return metadata


async def get_jwks(settings: Settings) -> Any | None:
    """Return the cached JWKS key set, fetching if stale."""
    cached = _jwks_cache.get_if_fresh()
    if cached is not None:
        return cached

    async with _jwks_cache.lock:
        cached = _jwks_cache.get_if_fresh()
        if cached is not None:
            return cached

        metadata = await get_oidc_metadata(settings)
        jwks_uri = (metadata or {}).get("jwks_uri")
        if not jwks_uri or not require_https(jwks_uri, "JWKS URI", settings):
            return None

        try:
            resp = await get_http_client().get(jwks_uri)
            resp.raise_for_status()
            document = resp.json()
            keys = JsonWebKey.import_key_set(document)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Failed to fetch JWKS: %s", exc)
            return _jwks_cache.get_stale()
        _jwks_cache.set(keys)
        _jwks_document["keys"] = document
        return keys


# The key set as the provider published it, next to the parsed one above.
# Evidence of a decision keeps these exact keys: they rotate, and a token
# must stay verifiable with the keys of its own moment.
_jwks_document: dict[str, Any] = {}


async def get_jwks_document(settings: Settings) -> dict[str, Any] | None:
    """The provider's key set as published (a JWKS document), or ``None``."""
    if await get_jwks(settings) is None:
        return None
    document = _jwks_document.get("keys")
    return document if isinstance(document, dict) else None


def validate_jwt_locally(
    token: str,
    jwks: Any,
    settings: Settings,
) -> dict[str, Any] | None:
    """Validate a JWT access token against the cached JWKS keys.

    Returns the decoded claims, or ``None`` if validation fails. The token
    must come from our issuer and be meant for our client.
    """
    try:
        claims = authlib_jwt.decode(token, jwks)
        claims.validate()
    except JoseError as exc:
        logger.debug("Local JWT validation failed: %s", exc)
        return None

    if claims.get("iss") != settings.OIDC_ISSUER:
        return None

    # Keycloak puts the client id in ``azp`` for access tokens and in
    # ``aud`` for id tokens. ``aud`` can be a string or a list.
    aud = claims.get("aud")
    aud_list = [aud] if isinstance(aud, str) else (aud or [])
    client_id = settings.OIDC_CLIENT_ID
    if client_id not in aud_list and claims.get("azp") != client_id:
        return None

    return dict(claims)


# ---------------------------------------------------------------------------
# OAuth / OIDC client singleton
# ---------------------------------------------------------------------------

_oauth: OAuth | None = None


def get_oauth(settings: Settings) -> OAuth | None:
    """Return the global OAuth instance, or ``None`` without OIDC."""
    global _oauth  # noqa: PLW0603
    if _oauth is not None:
        return _oauth
    if not settings.OIDC_ISSUER:
        return None

    _oauth = OAuth()
    _oauth.register(
        name="keycloak",
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        server_metadata_url=_get_discovery_url(settings),
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",
        },
    )
    return _oauth


# ---------------------------------------------------------------------------
# Login: match the identity to a pre-provisioned person
# ---------------------------------------------------------------------------


# Why a login was refused. The codes are stable: they are stored with the
# refusal, so a beheerder can see what stopped someone and act on it.
REFUSED_NO_SUBJECT = "geen_subject"
REFUSED_NO_EMAIL = "geen_emailadres"
# The provider did not vouch for the address: the claim is false or absent.
# This check is the defence against someone changing their own address at
# the provider to that of a colleague; it is never relaxed.
REFUSED_EMAIL_UNVERIFIED = "emailadres_niet_bevestigd"
REFUSED_UNKNOWN = "onbekend"
REFUSED_INACTIVE = "inactief"
# The person exists, but was bound to another identity at the provider.
REFUSED_OTHER_SUBJECT = "andere_aanmelding"

MATCHED_BY_SUBJECT = "subject"
MATCHED_BY_EMAIL = "emailadres_eerste_aanmelding"


@dataclass(frozen=True)
class LoginMatch:
    """What a login led to: a person and the rule that found them, or why not.

    ``candidate`` is the person a refusal is about, when there is one (an
    inactive person, a person bound to another identity).
    """

    person: Person | None = None
    rule: str | None = None
    refusal: str | None = None
    candidate: Person | None = None


def email_verified_claim(claims: Mapping[str, Any]) -> bool | None:
    """The claim as sent: True, False, or ``None`` when it is absent."""
    value = claims.get("email_verified")
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def display_name_from_claims(claims: Mapping[str, Any]) -> str:
    """A name to show. Never the provider's user id.

    In the platform realm ``preferred_username`` is overridden with the
    SSO Rijk user id (a urn), so it only serves as a name when it does not
    look like an identifier.
    """
    name = str(claims.get("name") or "").strip()
    if name:
        return name
    given = str(claims.get("given_name") or "").strip()
    family = str(claims.get("family_name") or "").strip()
    if given or family:
        return f"{given} {family}".strip()
    fallback = str(claims.get("preferred_username") or "").strip()
    if fallback.lower().startswith("urn:") or "@" in fallback:
        return ""
    return fallback


def organisation_from_claims(claims: Mapping[str, Any]) -> dict[str, str]:
    """Name and number of the person's organisation, as the provider says.

    The platform's realms pass them on as ``organization.name`` and
    ``organization.number``; a dotted claim name arrives as a nested object
    unless the mapper escapes the dot, so both shapes are read. A claim,
    not a fact grip checked: it says what SSO Rijk has on record.
    """
    nested = claims.get("organization")
    found: dict[str, str] = {}
    for key in ("name", "number"):
        value = nested.get(key) if isinstance(nested, Mapping) else None
        if value is None:
            value = claims.get(f"organization.{key}")
        if value is not None and str(value).strip():
            found[key] = str(value).strip()
    return found


async def match_login(
    db: AsyncSession,
    *,
    sub: str,
    email: str,
    email_verified: bool | None,
    name: str = "",
) -> LoginMatch:
    """Match an identity to the active person it may log in as.

    1. A person already bound to ``sub``.
    2. Otherwise a person with this email that is not bound to any subject
       yet, and only when the identity provider vouches for the email. The
       subject is bound on this first login.

    Nobody is created here: an unknown identity gets no access.
    """
    if not sub:
        return LoginMatch(refusal=REFUSED_NO_SUBJECT)
    repo = PersonRepository(db)

    person = await repo.get_by_oidc_subject(sub)
    if person is not None:
        if not person.is_active:
            return LoginMatch(refusal=REFUSED_INACTIVE, candidate=person)
        return LoginMatch(person=person, rule=MATCHED_BY_SUBJECT)

    if not email:
        return LoginMatch(refusal=REFUSED_NO_EMAIL)
    if email_verified is not True:
        return LoginMatch(refusal=REFUSED_EMAIL_UNVERIFIED)

    person = await repo.get_by_email(email)
    if person is None:
        return LoginMatch(refusal=REFUSED_UNKNOWN)
    if not person.is_active:
        return LoginMatch(refusal=REFUSED_INACTIVE, candidate=person)
    if person.oidc_subject is not None:
        # The person exists and the provider vouches for the email, but the
        # login was bound to another subject earlier: the provider was
        # recreated, or the person got a new account there. Nothing is
        # rebound by itself (that would let a second account with the same
        # address take over); the beheerder unbinds the login on the Team
        # screen, after which the next login binds again. The email stays
        # out of the log; the person id says who.
        logger.warning(
            "OIDC login refused: person %s is bound to another subject; "
            "unbind the login of this person to let it bind again",
            person.id,
        )
        return LoginMatch(refusal=REFUSED_OTHER_SUBJECT, candidate=person)

    person.oidc_subject = sub
    # A provisioned person may have been entered with only an email address.
    if name and (not person.name or person.name == person.email):
        person.name = name
    record_audit(
        db,
        actor=person,
        action=UPDATE,
        entity="person",
        entity_id=person.id,
        old_value={"oidc_subject": None},
        new_value={"oidc_subject": sub},
    )
    await db.flush()
    logger.info("Bound OIDC subject to person %s on first login", person.id)
    return LoginMatch(person=person, rule=MATCHED_BY_EMAIL)


async def resolve_person_for_login(
    db: AsyncSession,
    *,
    sub: str,
    email: str,
    email_verified: bool,
    name: str = "",
) -> Person | None:
    """Return the active person this identity may log in as, or ``None``."""
    match = await match_login(
        db, sub=sub, email=email, email_verified=email_verified, name=name
    )
    return match.person


LOGIN_SUBJECT = "login"


def record_login(
    db: AsyncSession,
    match: LoginMatch,
    *,
    email: str,
    as_guest: bool = False,
) -> None:
    """Put a login, or a refused one, in the event stream.

    A refusal names the address that was offered: without it a beheerder
    cannot tell who to add or unbind. The events are for beheer only.
    """
    person = match.person or match.candidate
    address = normalize_email(email) if email else ""
    if match.person is not None:
        event_type, payload = (
            "login.succeeded",
            {"rule": match.rule},
        )
    elif as_guest:
        event_type, payload = (
            "login.guest",
            {"email": address},
        )
    else:
        event_type, payload = (
            "login.refused",
            {"reason": match.refusal, "email": address},
        )
    stream.append(
        db,
        event_type,
        subject=(LOGIN_SUBJECT, uuid4()),
        actor_person_id=match.person.id if match.person else None,
        person_id=person.id if person else None,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Token validation, refresh and revocation
# ---------------------------------------------------------------------------


async def _try_refresh_token(session: dict[str, Any], settings: Settings) -> bool:
    """Refresh the access token with the stored refresh token.

    Updates the session in place and returns ``True`` on success.
    """
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return False

    metadata = await get_oidc_metadata(settings)
    token_url = (metadata or {}).get("token_endpoint")
    if not token_url or not require_https(token_url, "Token endpoint", settings):
        return False

    try:
        resp = await get_http_client().post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
    except httpx.HTTPError as exc:
        logger.warning("Token refresh HTTP error: %s", exc)
        return False
    if resp.status_code != 200:
        logger.info("Token refresh failed with status %d", resp.status_code)
        return False

    tokens = resp.json()
    session["access_token"] = tokens["access_token"]
    if "refresh_token" in tokens:
        session["refresh_token"] = tokens["refresh_token"]
    if "id_token" in tokens:
        session["id_token"] = tokens["id_token"]
    session["token_validated_at"] = time.time()
    return True


async def validate_session_token(session: dict[str, Any], settings: Settings) -> bool:
    """Validate the session's access token against the identity provider.

    A cached validation timestamp avoids a round trip on every request. An
    expired token is refreshed. Returns ``False`` when the session must be
    rejected; the session is cleared in that case.
    """
    access_token = session.get("access_token")
    if not access_token:
        return False

    validated_at = session.get("token_validated_at")
    if validated_at and (time.time() - validated_at) < _TOKEN_REVALIDATION_INTERVAL:
        return True

    # Local JWT validation first (no network call).
    jwks = await get_jwks(settings)
    if jwks and validate_jwt_locally(access_token, jwks, settings):
        session["token_validated_at"] = time.time()
        return True

    # Not valid locally: expired, or keys rotated. Ask the provider.
    metadata = await get_oidc_metadata(settings)
    userinfo_url = (metadata or {}).get("userinfo_endpoint")
    if not userinfo_url or not require_https(
        userinfo_url, "Userinfo endpoint", settings
    ):
        return False

    try:
        resp = await get_http_client().get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except httpx.HTTPError as exc:
        logger.warning("Token validation HTTP error: %s", exc)
        if validated_at and (time.time() - validated_at) < _NETWORK_ERROR_GRACE_SECONDS:
            return True
        return False

    if resp.status_code == 200:
        session["token_validated_at"] = time.time()
        return True

    if await _try_refresh_token(session, settings):
        return True

    logger.info("Token invalid and refresh failed, clearing session")
    session.clear()
    return False


async def revoke_tokens(
    settings: Settings,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> None:
    """Revoke tokens at the identity provider (best effort, for logout)."""
    if not access_token and not refresh_token:
        return

    metadata = await get_oidc_metadata(settings)
    if not metadata:
        return
    revocation_url = metadata.get(
        "revocation_endpoint",
        f"{settings.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/revoke",
    )
    if not require_https(revocation_url, "Revocation endpoint", settings):
        return

    for token_value, token_type in (
        (refresh_token, "refresh_token"),
        (access_token, "access_token"),
    ):
        if not token_value:
            continue
        try:
            await get_http_client().post(
                revocation_url,
                data={
                    "token": token_value,
                    "token_type_hint": token_type,
                    "client_id": settings.OIDC_CLIENT_ID,
                    "client_secret": settings.OIDC_CLIENT_SECRET,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("Token revocation failed for %s: %s", token_type, exc)


# ---------------------------------------------------------------------------
# Who is making this request
# ---------------------------------------------------------------------------


async def _dev_person(request: Request, db: AsyncSession) -> Person | None:
    """The person a request runs as when no identity provider is configured."""
    repo = PersonRepository(db)
    raw = request.cookies.get(DEV_PERSON_COOKIE)
    if raw:
        try:
            person = await repo.get(UUID(raw))
        except ValueError:
            person = None
        if person is not None and person.is_active:
            return person
    return await repo.first_active_with_function(BEHEERDER)


async def resolve_person(
    request: Request,
    db: AsyncSession,
    settings: Settings,
) -> Person | None:
    """Return the active person behind this request, or ``None``.

    With OIDC the session must hold a validated token and the id of the
    person resolved at login. The person is loaded again on every request, so
    deactivating someone takes effect immediately.
    """
    if not settings.OIDC_ISSUER:
        return await _dev_person(request, db)

    session: dict[str, Any] = request.scope.get("session", {})
    person_id = session.get("person_id")
    if is_passkey_session(session):
        # No token to validate: the session lives for a fixed, shorter time,
        # and the person is loaded again below like for any other session.
        if passkey_session_expired(session, settings):
            session.clear()
            return None
    else:
        if not person_id or not session.get("access_token"):
            return None
        if not await validate_session_token(session, settings):
            return None
    try:
        person = await PersonRepository(db).get(UUID(person_id))
    except ValueError:
        return None
    if person is None or not person.is_active:
        session.clear()
        return None
    return person


# A session that began with a passkey holds no tokens of the identity
# provider: {"created_at": <epoch seconds>} next to ``person_id``.
PASSKEY_SESSION_KEY = "passkey_session"


def is_passkey_session(session: dict[str, Any]) -> bool:
    """Whether the session began with a passkey instead of the provider."""
    return isinstance(session.get(PASSKEY_SESSION_KEY), dict) and bool(
        session.get("person_id")
    )


def passkey_session_expired(session: dict[str, Any], settings: Settings) -> bool:
    started = (session.get(PASSKEY_SESSION_KEY) or {}).get("created_at")
    if not isinstance(started, int | float):
        return True
    return time.time() - started > settings.PASSKEY_SESSION_TTL_SECONDS


def start_passkey_session(session: dict[str, Any], person: Person) -> None:
    """Replace whatever the session held by a login of ``person``."""
    session.clear()
    session[PASSKEY_SESSION_KEY] = {"created_at": time.time()}
    session["person_id"] = str(person.id)
    # New session id after login, against session fixation.
    session["_rotate"] = True


# Session key for an invited signer without a person record in this
# instance: {"email": ..., "name": ..., "email_verified": True}. A session
# holds either ``person_id`` or this, never both.
GUEST_SESSION_KEY = "guest"

# The only API prefix a guest session may reach.
GUEST_API_PREFIX = "/api/signing/"


def guest_identity(
    *, email: str, email_verified: bool, name: str
) -> dict[str, Any] | None:
    """The guest identity to store at login, or ``None`` when it does not qualify.

    The invitation is matched on the email address, so only an address the
    identity provider vouches for counts.
    """
    address = email.strip().lower()
    if not address or not email_verified:
        return None
    return {"email": address, "name": name.strip() or address, "email_verified": True}


async def resolve_guest(request: Request, settings: Settings) -> dict[str, Any] | None:
    """The guest identity behind this request, or ``None``.

    Only with an identity provider, a validated token and no person: a guest
    never exists in development mode, where nobody logs in.
    """
    if not settings.OIDC_ISSUER:
        return None
    session: dict[str, Any] = request.scope.get("session", {})
    guest = session.get(GUEST_SESSION_KEY)
    if not isinstance(guest, dict) or session.get("person_id"):
        return None
    if not session.get("access_token"):
        return None
    if guest.get("email_verified") is not True or not guest.get("email"):
        return None
    if not await validate_session_token(session, settings):
        return None
    return guest


async def get_current_person(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Person:
    """Dependency: the logged-in, active person. Raises 401 otherwise."""
    person = await resolve_person(request, db, settings)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Niet ingelogd",
        )
    return person


CurrentPerson = Annotated[Person, Depends(get_current_person)]


def require_function(
    *role_ids: str,
) -> Callable[..., Coroutine[Any, Any, Person]]:
    """Dependency factory: the person must hold one of the given functions.

    Usage::

        @router.post("/rate-cards")
        async def create(person: Person = Depends(require_function(BEHEERDER))):
            ...
    """
    if not role_ids:
        raise ValueError("require_function needs at least one function")

    async def _check(
        person: CurrentPerson,
        db: AsyncSession = Depends(get_db),
    ) -> Person:
        held = await PersonRepository(db).active_function_ids(person.id)
        if not set(held) & set(role_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Je hebt hiervoor niet het juiste recht in grip",
            )
        return person

    return _check
