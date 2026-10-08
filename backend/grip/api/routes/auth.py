"""Auth routes: OIDC login, callback, logout and status."""

from __future__ import annotations

import logging
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.guest_deps import has_open_invitation
from grip.core import oidc_diagnostics as diagnostics
from grip.core.auth import (
    GUEST_SESSION_KEY,
    display_name_from_claims,
    email_verified_claim,
    get_jwks,
    get_oauth,
    get_oidc_metadata,
    guest_identity,
    is_passkey_session,
    match_login,
    record_login,
    resolve_guest,
    resolve_person,
    revoke_tokens,
)
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.core.rate_limit import RateLimiter
from grip.repositories.person import PersonRepository
from grip.schema.auth import AuthStatus, GuestSummary, PersonSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Query parameter the frontend reads to explain a failed login.
LOGIN_ERROR_PARAM = "login_error"
LOGIN_ERROR_NO_ACCESS = "geen_toegang"
# Where an invited signer lands after login: the frontend page with the
# quotes waiting for them.
GUEST_LANDING_PATH = "/tekenen"
LOGIN_ERROR_FAILED = "mislukt"
# The person turned back at the identity provider.
LOGIN_ERROR_CANCELLED = "geannuleerd"

# The login round trip needs no session, so it gets its own brake.
_rate_limiter = RateLimiter(limit=30, window=60)


# Where the visitor wanted to go, kept in the session across the round trip
# to the identity provider.
LOGIN_NEXT_SESSION_KEY = "login_next"
_MAX_NEXT_LENGTH = 1024


def safe_next_path(raw: object) -> str:
    """Return ``raw`` when it is a path within this application, else ``""``.

    The value comes from the query string and ends up in a redirect, so it
    is an open-redirect vector. Only a relative path is accepted: one leading
    slash, no scheme, no host, no backslash (browsers read ``/\\host`` as
    ``//host``) and no control characters. API paths are refused as well: a
    visitor must land on a page.
    """
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_NEXT_LENGTH:
        return ""
    if not raw.startswith("/") or raw.startswith("//") or "\\" in raw:
        return ""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return ""
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        return ""
    if parts.path == "/api" or parts.path.startswith("/api/"):
        return ""
    return raw


def _frontend_redirect(
    settings: Settings, error: str = "", next_path: str = ""
) -> RedirectResponse:
    base = settings.FRONTEND_URL.rstrip("/")
    if error:
        url = f"{base}/?{urlencode({LOGIN_ERROR_PARAM: error})}"
    elif next_path:
        url = f"{base}{next_path}"
    else:
        url = settings.FRONTEND_URL
    return RedirectResponse(url=url, status_code=302)


def _after_login(settings: Settings, response: RedirectResponse) -> RedirectResponse:
    """Where a finished login goes: the application, or the diagnostic report."""
    if settings.OIDC_DIAGNOSTICS:
        return RedirectResponse(url="/api/auth/diagnose", status_code=302)
    return response


def _callback_url(request: Request, settings: Settings) -> str:
    """The redirect URI for the identity provider.

    Never built from the request: it is one of two configured origins. When
    the request reached the API through the frontend origin (nginx or the
    dev server proxies /api), the callback goes back the same way, so the
    session cookie that holds the OIDC state is first-party throughout.
    Otherwise it is BACKEND_URL. Both must be registered as redirect URIs
    of the client. The scheme and host of the request are only believed
    from a trusted proxy (see TrustedProxyMiddleware); a mismatch falls back
    to BACKEND_URL.
    """
    frontend = settings.FRONTEND_URL.rstrip("/")
    host = request.headers.get("host", "")
    request_origin = f"{request.url.scheme}://{host}".lower()
    base = frontend if request_origin == frontend.lower() else settings.BACKEND_URL
    return f"{base.rstrip('/')}/api/auth/callback"


@router.get("/login")
async def login(
    request: Request,
    next: str | None = None,  # noqa: A002 - the query parameter is called next
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect the user to the login page of the identity provider.

    ``next`` is the page to return to afterwards. An invalid value is
    dropped, not refused: the visitor then lands on the start page.
    """
    _rate_limiter.check(request)
    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Inloggen is niet geconfigureerd",
        )
    next_path = safe_next_path(next)
    if next_path:
        request.session[LOGIN_NEXT_SESSION_KEY] = next_path
    else:
        request.session.pop(LOGIN_NEXT_SESSION_KEY, None)
    return await oauth.keycloak.authorize_redirect(
        request, _callback_url(request, settings)
    )


@router.get("/callback")
async def callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle the OIDC redirect after login.

    Exchanges the code for tokens and matches the identity to a
    pre-provisioned person. Without a match nothing is stored in the session.
    """
    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Inloggen is niet geconfigureerd",
        )

    # The provider may be sending someone back who went there to decide on
    # a quote (grip.proof), not to log in. That is recognised by the state
    # of the request, and handled without touching the session.
    from grip.api.routes.proof import finish_after_login, pending_intent

    pending = pending_intent(request)
    if pending is not None:
        return await finish_after_login(request, db, settings, pending)

    _rate_limiter.check(request)
    if _diagnostic_pending(request, settings):
        return await _finish_diagnostic_reauth(request, settings)

    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except OAuthError as exc:
        # access_denied: the person cancelled. Anything else: a stale tab, an
        # expired state, a provider that refused the code.
        logger.warning("OIDC callback failed: %s", exc.error)
        request.session.clear()
        cancelled = exc.error == "access_denied"
        return _frontend_redirect(
            settings, LOGIN_ERROR_CANCELLED if cancelled else LOGIN_ERROR_FAILED
        )
    except httpx.HTTPError as exc:
        # The provider could not be reached for the token exchange.
        logger.warning("OIDC callback: provider unreachable: %s", type(exc).__name__)
        request.session.clear()
        return _frontend_redirect(settings, LOGIN_ERROR_FAILED)

    userinfo = token.get("userinfo") or {}
    email = str(userinfo.get("email") or "")
    name = display_name_from_claims(userinfo)
    match = await match_login(
        db,
        sub=str(userinfo.get("sub") or ""),
        email=email,
        email_verified=email_verified_claim(userinfo),
        name=name,
    )
    person = match.person

    session = request.session
    # Validated again on the way out: the session is not a trusted source
    # for a redirect target.
    next_path = safe_next_path(session.get(LOGIN_NEXT_SESSION_KEY))
    session.clear()

    if person is None:
        # No person record, but perhaps someone a manager invited to sign a
        # quote. Only an address the identity provider vouches for, and only
        # while an invitation that has not expired is waiting for it.
        guest = guest_identity(
            email=email,
            email_verified=email_verified_claim(userinfo) is True,
            name=name,
        )
        if guest is not None and await has_open_invitation(db, guest["email"]):
            session["access_token"] = token.get("access_token")
            session["refresh_token"] = token.get("refresh_token")
            session["id_token"] = token.get("id_token")
            session[GUEST_SESSION_KEY] = guest
            session["_rotate"] = True
            logger.info("OIDC login as invited signer")
            record_login(db, match, email=email, as_guest=True)
            await _keep_diagnostics(request, settings, token, userinfo, "gast")
            # A signing link may point at one quote; anything else in the
            # application is not for a guest.
            landing = (
                next_path
                if next_path == GUEST_LANDING_PATH
                or next_path.startswith(f"{GUEST_LANDING_PATH}/")
                else GUEST_LANDING_PATH
            )
            return _after_login(
                settings, _frontend_redirect(settings, next_path=landing)
            )

        # The reason goes to the log and to the event stream, where a
        # beheerder reads it; the visitor only learns that there is no access.
        logger.info("OIDC login refused: %s", match.refusal)
        record_login(db, match, email=email)
        await revoke_tokens(
            settings,
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
        )
        await _keep_diagnostics(
            request, settings, token, userinfo, match.refusal or "onbekend"
        )
        return _after_login(
            settings, _frontend_redirect(settings, LOGIN_ERROR_NO_ACCESS)
        )

    session["access_token"] = token.get("access_token")
    session["refresh_token"] = token.get("refresh_token")
    session["id_token"] = token.get("id_token")
    session["person_id"] = str(person.id)
    # New session id after login, against session fixation.
    session["_rotate"] = True
    # A passkey of this person can log in again for a while from now.
    from grip.services import passkeys

    await passkeys.note_oidc_login(db, person)
    record_login(db, match, email=email)
    await _keep_diagnostics(request, settings, token, userinfo, match.rule or "")

    logger.info("OIDC login successful for person %s", person.id)
    return _after_login(settings, _frontend_redirect(settings, next_path=next_path))


# -- diagnostics of a first login (OIDC_DIAGNOSTICS, never when deployed) ------


async def _keep_diagnostics(
    request: Request,
    settings: Settings,
    token: dict,
    userinfo: dict,
    outcome: str,
) -> None:
    """Remember, masked, what the provider sent at this login."""
    if not settings.OIDC_DIAGNOSTICS:
        return
    id_claims = diagnostics.claims_of_id_token(
        token.get("id_token"), await get_jwks(settings)
    )
    request.session[diagnostics.SESSION_KEY] = {
        "first": diagnostics.snapshot(
            id_claims=id_claims,
            userinfo=userinfo,
            token=token,
            outcome={"code": outcome},
        )
    }


def _diagnostic_pending(request: Request, settings: Settings) -> bool:
    if not settings.OIDC_DIAGNOSTICS:
        return False
    kept = request.session.get(diagnostics.SESSION_KEY)
    state = request.query_params.get("state")
    return isinstance(kept, dict) and bool(state) and kept.get("state") == state


async def _finish_diagnostic_reauth(
    request: Request, settings: Settings
) -> RedirectResponse:
    """The provider sent someone back from the forced re-authentication test."""
    oauth = get_oauth(settings)
    assert oauth is not None
    kept = dict(request.session.get(diagnostics.SESSION_KEY) or {})
    kept.pop("state", None)
    started = kept.pop("reauth_started", None)
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except (OAuthError, httpx.HTTPError) as exc:
        kept["reauth_failed"] = getattr(exc, "error", None) or type(exc).__name__
        request.session[diagnostics.SESSION_KEY] = kept
        return RedirectResponse(url="/api/auth/diagnose", status_code=302)
    userinfo = token.get("userinfo") or {}
    kept.pop("reauth_failed", None)
    kept["second"] = diagnostics.snapshot(
        id_claims=diagnostics.claims_of_id_token(
            token.get("id_token"), await get_jwks(settings)
        ),
        userinfo=userinfo,
        token=token,
    )
    if isinstance(started, int | float):
        kept["reauth_seconds"] = int(time.time() - started)
    request.session[diagnostics.SESSION_KEY] = kept
    # This login is not used for anything: give the tokens back.
    await revoke_tokens(
        settings,
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
    )
    return RedirectResponse(url="/api/auth/diagnose", status_code=302)


def _require_diagnostics(settings: Settings) -> None:
    if not settings.OIDC_DIAGNOSTICS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.get("/diagnose", response_class=PlainTextResponse)
async def diagnose(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    """What the provider sent at the last login in this browser, masked."""
    _require_diagnostics(settings)
    return PlainTextResponse(
        diagnostics.render(request.session.get(diagnostics.SESSION_KEY)),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/diagnose/reauth")
async def diagnose_reauth(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Ask the provider to authenticate again, to see whether it does."""
    _require_diagnostics(settings)
    _rate_limiter.check(request)
    oauth = get_oauth(settings)
    kept = request.session.get(diagnostics.SESSION_KEY)
    if oauth is None or not isinstance(kept, dict) or "first" not in kept:
        return RedirectResponse(url="/api/auth/diagnose", status_code=302)
    state = secrets.token_urlsafe(24)
    request.session[diagnostics.SESSION_KEY] = {
        **kept,
        "state": state,
        "reauth_started": time.time(),
    }
    return await oauth.keycloak.authorize_redirect(
        request,
        _callback_url(request, settings),
        state=state,
        prompt="login",
        max_age=0,
    )


@router.get("/logout")
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Clear the session and redirect to the end-session endpoint."""
    id_token = request.session.get("id_token")
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    from_passkey = is_passkey_session(request.session)
    request.session.clear()

    # A session that began with a passkey has nothing at the provider to end.
    if not settings.OIDC_ISSUER or from_passkey:
        return _frontend_redirect(settings)

    await revoke_tokens(
        settings, access_token=access_token, refresh_token=refresh_token
    )

    params = {
        "post_logout_redirect_uri": settings.FRONTEND_URL,
        "client_id": settings.OIDC_CLIENT_ID,
    }
    if id_token:
        params["id_token_hint"] = id_token
    # The provider says where a session ends; the Keycloak path is the
    # fallback for a discovery document that leaves it out.
    metadata = await get_oidc_metadata(settings) or {}
    end_session_url = metadata.get("end_session_endpoint") or (
        f"{settings.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/logout"
    )
    return RedirectResponse(
        url=f"{end_session_url}?{urlencode(params)}", status_code=302
    )


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthStatus:
    """Return who is logged in. The frontend calls this on every page load."""
    from grip.services import passkeys

    oidc_configured = bool(settings.OIDC_ISSUER)
    passkey_login = passkeys.login_enabled(settings)
    person = await resolve_person(request, db, settings)
    if person is None:
        guest = await resolve_guest(request, settings)
        return AuthStatus(
            authenticated=False,
            oidc_configured=oidc_configured,
            passkey_login=passkey_login,
            guest=GuestSummary(name=guest["name"], email=guest["email"])
            if guest
            else None,
        )

    people = PersonRepository(db)
    return AuthStatus(
        authenticated=True,
        oidc_configured=oidc_configured,
        person=PersonSummary.model_validate(person),
        functions=await people.active_function_ids(person.id),
        relations=await people.relation_names(person.id),
        passkey_login=passkey_login,
        passkey_session=is_passkey_session(request.session),
    )
