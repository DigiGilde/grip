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
from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

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
from grip.models.person import Person
from grip.models.role import BEHEERDER
from grip.repositories.person import PersonRepository

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


def require_https(url: str, label: str) -> bool:
    """Return True if the URL uses HTTPS; log and return False otherwise."""
    if url.startswith("https://"):
        return True
    logger.warning("%s is not HTTPS, refusing to send credentials: %s", label, url)
    return False


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
        if not require_https(url, "OIDC discovery URL"):
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
        if not jwks_uri or not require_https(jwks_uri, "JWKS URI"):
            return None

        try:
            resp = await get_http_client().get(jwks_uri)
            resp.raise_for_status()
            keys = JsonWebKey.import_key_set(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Failed to fetch JWKS: %s", exc)
            return _jwks_cache.get_stale()
        _jwks_cache.set(keys)
        return keys


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


async def resolve_person_for_login(
    db: AsyncSession,
    *,
    sub: str,
    email: str,
    email_verified: bool,
    name: str = "",
) -> Person | None:
    """Return the active person this identity may log in as, or ``None``.

    1. A person already bound to ``sub``.
    2. Otherwise a person with this email that is not bound to any subject
       yet, and only when the identity provider vouches for the email. The
       subject is bound on this first login.

    Nobody is created here: an unknown identity gets no access.
    """
    if not sub:
        return None
    repo = PersonRepository(db)

    person = await repo.get_by_oidc_subject(sub)
    if person is not None:
        return person if person.is_active else None

    if not email or not email_verified:
        return None

    person = await repo.get_by_email(email)
    if person is None or not person.is_active or person.oidc_subject is not None:
        return None

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
    return person


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
    if not token_url or not require_https(token_url, "Token endpoint"):
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
    if not userinfo_url or not require_https(userinfo_url, "Userinfo endpoint"):
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
    if not require_https(revocation_url, "Revocation endpoint"):
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
                detail="Je hebt hiervoor niet de juiste functie",
            )
        return person

    return _check
