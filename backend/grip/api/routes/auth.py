"""Auth routes: OIDC login, callback, logout and status."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import (
    get_oauth,
    resolve_person,
    resolve_person_for_login,
    revoke_tokens,
)
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.repositories.person import PersonRepository
from grip.schema.auth import AuthStatus, PersonSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Query parameter the frontend reads to explain a failed login.
LOGIN_ERROR_PARAM = "login_error"
LOGIN_ERROR_NO_ACCESS = "geen_toegang"
LOGIN_ERROR_FAILED = "mislukt"


def _frontend_redirect(settings: Settings, error: str = "") -> RedirectResponse:
    url = settings.FRONTEND_URL
    if error:
        url = f"{url.rstrip('/')}/?{urlencode({LOGIN_ERROR_PARAM: error})}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/login")
async def login(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect the user to the login page of the identity provider."""
    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Inloggen is niet geconfigureerd",
        )
    # Built from settings, not from the Host header, so it cannot be steered.
    redirect_uri = f"{settings.BACKEND_URL.rstrip('/')}/api/auth/callback"
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


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

    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except OAuthError as exc:
        logger.warning("OIDC callback failed: %s", exc.error)
        request.session.clear()
        return _frontend_redirect(settings, LOGIN_ERROR_FAILED)

    userinfo = token.get("userinfo") or {}
    person = await resolve_person_for_login(
        db,
        sub=userinfo.get("sub", ""),
        email=userinfo.get("email", ""),
        email_verified=bool(userinfo.get("email_verified")),
        name=userinfo.get("name") or userinfo.get("preferred_username", ""),
    )

    session = request.session
    session.clear()

    if person is None:
        logger.info("OIDC login refused: no active person for this identity")
        await revoke_tokens(
            settings,
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
        )
        return _frontend_redirect(settings, LOGIN_ERROR_NO_ACCESS)

    session["access_token"] = token.get("access_token")
    session["refresh_token"] = token.get("refresh_token")
    session["id_token"] = token.get("id_token")
    session["person_id"] = str(person.id)
    # New session id after login, against session fixation.
    session["_rotate"] = True

    logger.info("OIDC login successful for person %s", person.id)
    return _frontend_redirect(settings)


@router.get("/logout")
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Clear the session and redirect to the end-session endpoint."""
    id_token = request.session.get("id_token")
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")
    request.session.clear()

    if not settings.OIDC_ISSUER:
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
    end_session_url = (
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
    oidc_configured = bool(settings.OIDC_ISSUER)
    person = await resolve_person(request, db, settings)
    if person is None:
        return AuthStatus(authenticated=False, oidc_configured=oidc_configured)

    functions = await PersonRepository(db).active_function_ids(person.id)
    return AuthStatus(
        authenticated=True,
        oidc_configured=oidc_configured,
        person=PersonSummary.model_validate(person),
        functions=functions,
    )
