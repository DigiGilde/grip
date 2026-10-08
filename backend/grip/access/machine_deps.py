"""Authorization for machine clients that present a key instead of a session.

Used for links inside one organisation (ADR 0013). Traffic between
organisations does not come through here; that goes through FSC.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status

from grip.core.config import Settings, get_settings


def presented_bearer_key(request: Request) -> str:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def key_matches(presented: str, expected: str) -> bool:
    """Constant-time comparison. An unset key matches nothing."""
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


async def require_wies_export_key(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """The caller presented the key Wies uses to pull the export.

    Refused while no key is configured, so an unset variable never opens the
    route.
    """
    if not key_matches(presented_bearer_key(request), settings.GRIP_EXPORT_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geen geldige sleutel voor de export naar Wies",
        )


async def require_feed_key(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """The caller presented the key that opens the event feed.

    Refused while no key is configured: nothing leaves the instance by
    default.
    """
    if not key_matches(presented_bearer_key(request), settings.EVENTS_FEED_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geen geldige sleutel voor de gebeurtenissen",
        )
