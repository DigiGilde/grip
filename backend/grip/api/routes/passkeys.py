"""Passkeys: a person's own, the beheerder withdrawing one, and logging in.

Three groups of routes:

- ``/api/passkeys``: a person lists, registers and withdraws their own.
- ``/api/people/{person_id}/passkeys``: who manages users sees that a person
  has passkeys and can withdraw one, never make one.
- ``/api/auth/passkey``: logging in with a passkey, without a session.

Confirming a decision with a passkey is part of the proof routes
(``grip.api.routes.proof``).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, Resource
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.core.auth import (
    PASSKEY_SESSION_KEY,
    CurrentPerson,
    is_passkey_session,
    start_passkey_session,
)
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.repositories.passkey import PasskeyRepository
from grip.schema.passkeys import (
    AssertionIn,
    OptionsOut,
    PasskeyListOut,
    PasskeyOut,
    RegisterIn,
)
from grip.services import passkeys
from grip.services.errors import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/passkeys", tags=["passkeys"])
people_router = APIRouter(prefix="/people", tags=["passkeys"])
login_router = APIRouter(prefix="/auth/passkey", tags=["passkeys"])

# Session keys for the challenge between the two steps of a ceremony.
_REGISTER_CHALLENGE = "passkey_register_challenge"
_LOGIN_CHALLENGE = "passkey_login_challenge"


class _RateLimiter:
    """At most ``limit`` calls per client address in ``window`` seconds.

    In memory, per process: enough to slow down guessing against the two
    routes that need no session. It does not replace a limit at the edge.
    """

    def __init__(self, *, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        calls = self._calls[key]
        while calls and now - calls[0] > self.window:
            calls.popleft()
        if len(calls) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Te veel pogingen. Probeer het over een minuut opnieuw.",
            )
        calls.append(now)

    def reset(self) -> None:
        self._calls.clear()


login_rate_limiter = _RateLimiter(limit=20, window=60)


def _require_configured(settings: Settings) -> None:
    if not passkeys.configured(settings):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Passkeys zijn in deze omgeving niet ingesteld",
        )


def _may_register(request: Request, settings: Settings) -> bool:
    """A new passkey needs a session that began at the identity provider.

    A session that began with a passkey cannot make another one: every
    passkey then goes back to a login the provider vouched for. Without a
    provider (local development) anyone who is there may try it.
    """
    return not is_passkey_session(request.session)


# -- a person's own passkeys --------------------------------------------------


@router.get("", response_model=PasskeyListOut)
async def list_own(
    request: Request,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PasskeyListOut:
    items = await PasskeyRepository(db).of_person(person.id)
    return PasskeyListOut(
        available=passkeys.configured(settings),
        login_enabled=passkeys.login_enabled(settings),
        login_max_age_days=settings.PASSKEY_LOGIN_MAX_AGE_DAYS,
        may_register=_may_register(request, settings),
        items=[PasskeyOut.model_validate(item) for item in items],
    )


@router.post("/register/options", response_model=OptionsOut)
async def register_options(
    request: Request,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OptionsOut:
    _require_configured(settings)
    if not _may_register(request, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Log in via de gewone weg om een passkey vast te leggen.",
        )
    options_json, challenge = await passkeys.registration_options(db, person, settings)
    request.session[_REGISTER_CHALLENGE] = challenge
    return OptionsOut(options_json=options_json)


@router.post(
    "/register/verify", response_model=PasskeyOut, status_code=status.HTTP_201_CREATED
)
async def register_verify(
    body: RegisterIn,
    request: Request,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PasskeyOut:
    _require_configured(settings)
    challenge = request.session.pop(_REGISTER_CHALLENGE, None)
    if not challenge or not _may_register(request, settings):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Begin opnieuw met het vastleggen van de passkey.",
        )
    try:
        passkey = await passkeys.register(
            db,
            person,
            settings,
            credential=body.credential,
            challenge_hex=challenge,
            label=body.label,
            login=passkeys.login_of_session(request.session, settings),
        )
    except passkeys.PasskeyRefusedError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return PasskeyOut.model_validate(passkey)


@router.delete("/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_own(
    passkey_id: UUID,
    person: CurrentPerson,
    db: AsyncSession = Depends(get_db),
) -> None:
    passkey = await passkeys.get_own(db, passkey_id, person)
    await passkeys.revoke(db, passkey, actor=person)


# -- the beheerder --------------------------------------------------------------


@people_router.get("/{person_id}/passkeys", response_model=list[PasskeyOut])
async def list_of_person(
    person_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> list[PasskeyOut]:
    """The passkeys of a person, for who manages users."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    items = await PasskeyRepository(db).of_person(person_id)
    return [PasskeyOut.model_validate(item) for item in items]


@people_router.delete(
    "/{person_id}/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_of_person(
    person_id: UUID,
    passkey_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Withdraw someone's passkey, for instance when a device is lost."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.person(person_id))
    passkey = await PasskeyRepository(db).get(passkey_id)
    if passkey is None or passkey.person_id != person_id or passkey.revoked_at:
        raise NotFoundError("Passkey", passkey_id)
    await passkeys.revoke(db, passkey, actor=person)


# -- logging in -------------------------------------------------------------------


@login_router.post("/options", response_model=OptionsOut)
async def login_options(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> OptionsOut:
    """The challenge for logging in with a passkey. No session needed."""
    login_rate_limiter.check(request)
    if not passkeys.login_enabled(settings):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Inloggen met een passkey staat in deze omgeving uit",
        )
    options_json, challenge = passkeys.login_options(settings)
    request.session[_LOGIN_CHALLENGE] = challenge
    return OptionsOut(options_json=options_json)


@login_router.post("/verify", response_model=None)
async def login_verify(
    body: AssertionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    """Check the assertion and start a session for the person it belongs to."""
    login_rate_limiter.check(request)
    challenge = request.session.pop(_LOGIN_CHALLENGE, None)
    if not challenge:
        raise HTTPException(status_code=400, detail=passkeys.REFUSED)
    try:
        person = await passkeys.login(
            db, settings, credential=body.credential, challenge_hex=challenge
        )
    except passkeys.PasskeyRefusedError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    start_passkey_session(request.session, person)
    logger.info("Passkey login for person %s", person.id)
    return {"authenticated": True}


__all__ = ["PASSKEY_SESSION_KEY", "login_router", "people_router", "router"]
