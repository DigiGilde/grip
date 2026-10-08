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
    # The URI grip minted for this person, when Wies holds it.
    grip_person_uri: str | None = None


@dataclass(frozen=True)
class WiesProposalAnswer:
    """What staff of Wies decided on a new colleague grip proposed."""

    person_uri: str
    state: str
    public_id: str | None = None


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
        person_uri = str(item.get("grip_person_uri") or "").strip() or None
        # The two systems share the person URI and, later, the address. A
        # colleague with neither cannot be matched to anyone.
        if not name or (not email and not person_uri) or (email and email in seen):
            continue
        if email:
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
                grip_person_uri=person_uri,
            )
        )
    return colleagues


def parse_proposal_answers(payload: object) -> list[WiesProposalAnswer]:
    """The decisions of Wies on proposed colleagues; absent in an older Wies."""
    if not isinstance(payload, dict):
        return []
    answers: list[WiesProposalAnswer] = []
    for item in payload.get("proposals") or ():
        if not isinstance(item, dict):
            continue
        uri = str(item.get("grip_person_uri") or "").strip()
        state = str(item.get("state") or "").strip()
        if uri and state:
            answers.append(
                WiesProposalAnswer(
                    person_uri=uri,
                    state=state,
                    public_id=str(item.get("public_id") or "").strip() or None,
                )
            )
    return answers


async def fetch_colleagues(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> list[WiesColleague]:
    """All colleagues Wies offers. ``transport`` is for tests."""
    return (await fetch_wies_state(settings, transport=transport))[0]


async def fetch_wies_state(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> tuple[list[WiesColleague], list[WiesProposalAnswer]]:
    """The colleagues of Wies and its answers to proposed colleagues."""
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
    return parse_colleagues(payload), parse_proposal_answers(payload)


SKILLS_PATH = "/koppelvlak/grip/vaardigheden/"


@dataclass(frozen=True)
class WiesSkill:
    """A skill in Wies: what a role on an assignment is called there."""

    public_id: str
    name: str


def parse_skills(payload: object) -> list[WiesSkill]:
    if not isinstance(payload, dict) or not isinstance(payload.get("skills"), list):
        raise WiesUnavailableError("Wies gaf geen lijst met rollen terug.")
    skills: list[WiesSkill] = []
    seen: set[str] = set()
    for item in payload["skills"]:
        if not isinstance(item, dict):
            continue
        public_id = str(item.get("public_id") or "").strip()
        name = " ".join(str(item.get("name") or "").split())
        if not public_id or not name or public_id in seen:
            continue
        seen.add(public_id)
        skills.append(WiesSkill(public_id=public_id, name=name))
    return skills


async def fetch_skills(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> list[WiesSkill]:
    """The skills of Wies, which fill the role catalogue. ``transport`` is for tests."""
    if not is_wies_configured(settings):
        raise WiesNotConfiguredError("De koppeling met Wies is niet ingesteld.")
    url = settings.WIES_BASE_URL.rstrip("/") + SKILLS_PATH
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
    return parse_skills(payload)
