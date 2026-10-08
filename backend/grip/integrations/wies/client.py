"""Reads colleagues from Wies.

Wies decides who works here. Grip reads the list to pick people from; it
never writes to Wies.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from grip.core.config import Settings

COLLEAGUES_PATH = "/koppelvlak/grip/collegas/"


class WiesNotConfiguredError(RuntimeError):
    """WIES_BASE_URL or WIES_API_KEY is not set."""


class WiesUnavailableError(RuntimeError):
    """Wies did not answer with a list of colleagues."""


@dataclass(frozen=True)
class WiesColleague:
    public_id: str
    name: str
    email: str
    active: bool
    suborganization: str | None = None
    skills: tuple[str, ...] = ()
    labels: tuple[tuple[str, str], ...] = ()


def is_wies_configured(settings: Settings) -> bool:
    return bool(settings.WIES_BASE_URL and settings.WIES_API_KEY)


def parse_colleagues(payload: object) -> list[WiesColleague]:
    """Turn the answer of Wies into colleagues; refuse anything else."""
    if not isinstance(payload, dict) or not isinstance(payload.get("colleagues"), list):
        raise WiesUnavailableError("Wies gaf geen lijst met collega's terug.")
    colleagues: list[WiesColleague] = []
    seen: set[str] = set()
    for item in payload["colleagues"]:
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        # The address is the only key the two systems share.
        if not email or not name or email in seen:
            continue
        seen.add(email)
        colleagues.append(
            WiesColleague(
                public_id=str(item.get("public_id") or ""),
                name=name,
                email=email,
                active=bool(item.get("active")),
                suborganization=item.get("suborganization") or None,
                skills=tuple(str(s) for s in item.get("skills") or ()),
                labels=tuple(
                    (str(label.get("category") or ""), str(label.get("name") or ""))
                    for label in item.get("labels") or ()
                    if isinstance(label, dict)
                ),
            )
        )
    return colleagues


async def fetch_colleagues(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> list[WiesColleague]:
    """All colleagues Wies offers. ``transport`` is for tests."""
    if not is_wies_configured(settings):
        raise WiesNotConfiguredError("De koppeling met Wies is niet ingesteld.")
    url = settings.WIES_BASE_URL.rstrip("/") + COLLEAGUES_PATH
    try:
        async with httpx.AsyncClient(timeout=30, transport=transport) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {settings.WIES_API_KEY}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise WiesUnavailableError("Wies is niet bereikbaar.") from exc
    if response.status_code != httpx.codes.OK:
        raise WiesUnavailableError(f"Wies gaf status {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise WiesUnavailableError("Wies gaf geen JSON terug.") from exc
    return parse_colleagues(payload)
