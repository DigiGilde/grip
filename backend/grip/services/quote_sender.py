"""Who sends a quote, and the standard texts of the organisation.

Three settings of the instance, changed by the beheerder under Beheer:

- ``quote.sender``: the organisation as it stands on a letter: its name,
  what it is part of, the unit, the addresses, the mailbox for orders, a
  contact person and who signs.
- ``quote.text_blocks``: the outline of a quote. Every block is a section
  with a heading; a block with a body is a standard text of the organisation
  (delivery terms), a block without one is prose a person writes per quote.
- ``quote.letter``: the sentences around the sections: the opening and the
  closing.

A quote freezes what it was made with. Changing a setting changes the next
quote, never one that exists.

The environment gives the starting value of the name and of what the
organisation is part of (``ORGANISATION_NAME``, ``LETTERHEAD_LINES``), as it
does for the reference prefix. The logo and the typeface stay deployment
settings: they are files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings, get_settings
from grip.models.person import Person
from grip.services import instance_settings, quote_prose
from grip.services.errors import DomainValidationError

_PROFILES = Path(__file__).resolve().parents[1] / "data" / "profiles"

SENDER_TEXT_FIELDS = ("organisation", "unit", "orders_email", "website")
SENDER_LINE_FIELDS = ("part_of", "visiting_address", "postal_address")
CONTACT_FIELDS = ("name", "role", "email", "phone")
SIGNATORY_FIELDS = ("on_behalf_of", "name", "title", "organisation")
# ``required``: the section stands in every quote; a writer cannot leave it
# out or move it past another required section.
BLOCK_FLAGS = ("included", "with_costs", "numbered", "draftable", "required")

MAX_LINE = 200
MAX_BLOCKS = 30

EMPTY_SENDER: dict[str, Any] = {
    "organisation": "",
    "part_of": [],
    "unit": "",
    "visiting_address": [],
    "postal_address": [],
    "orders_email": "",
    "website": "",
    "contact": dict.fromkeys(CONTACT_FIELDS, ""),
    "signatory": dict.fromkeys(SIGNATORY_FIELDS, ""),
}

# The outline a new instance starts with: the sections a quote of a
# government contractor usually has, without any text of an organisation.
DEFAULT_BLOCKS: list[dict[str, Any]] = [
    {
        "key": "inleiding",
        "heading": "Inleiding",
        "hint": "Waarom is deze opdracht nodig? De aanleiding en het doel "
        "waaraan de opdracht bijdraagt.",
        "draftable": True,
    },
    {
        "key": "opdracht",
        "heading": "Opdracht",
        "hint": "Wat wordt er gevraagd, wat hoort erbij en wat valt erbuiten.",
        "draftable": True,
    },
    {
        "key": "team",
        "heading": "Opbouw en inzet team",
        "hint": "Welke rollen levert de organisatie, vanaf wanneer en in welke "
        "opbouw. Rollen en niveaus, geen namen van personen.",
        "draftable": True,
    },
    {
        "key": "kosten",
        "heading": "Kosten",
        "hint": "Wat bij de bedragen gezegd moet worden. De tabel met regels en "
        "het totaal volgt uit de begroting.",
        "with_costs": True,
    },
    {
        "key": "werkwijze",
        "heading": "Werkwijze",
        "hint": "Hoe het team werkt en hoe wordt afgestemd.",
        "draftable": True,
    },
    {
        "key": "governance",
        "heading": "Governance",
        "hint": "Wie stuurt, wie levert, en welk overleg er is.",
        "draftable": True,
    },
    {
        "key": "voorwaarden",
        "heading": "Leveringsvoorwaarden",
        "hint": "De standaardvoorwaarden van de organisatie.",
    },
]

DEFAULT_LETTER: dict[str, Any] = {
    "opening": "Met genoegen bied ik u de volgende offerte aan.",
    "closing": "",
    "billing_annex": False,
}


def _text(value: Any, where: str, *, limit: int = MAX_LINE) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DomainValidationError(f"{where} is tekst.")
    value = " ".join(value.split())
    if len(value) > limit:
        raise DomainValidationError(f"{where} is te lang (hooguit {limit} tekens).")
    return value


def _lines(value: Any, where: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split("\n")
    if not isinstance(value, list):
        raise DomainValidationError(f"{where} is een lijst van regels.")
    lines = [_text(line, where) for line in value]
    lines = [line for line in lines if line]
    if len(lines) > 6:
        raise DomainValidationError(f"{where} heeft hooguit zes regels.")
    return lines


def _group(value: Any, fields: tuple[str, ...], where: str) -> dict[str, str]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise DomainValidationError(f"{where} is een groep van velden.")
    unknown = sorted(set(value) - set(fields))
    if unknown:
        raise DomainValidationError(f"{where}: onbekend veld {', '.join(unknown)}.")
    return {name: _text(value.get(name), f"{where}, {name}") for name in fields}


def check_sender(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainValidationError("De afzender is een groep van velden.")
    known = {*SENDER_TEXT_FIELDS, *SENDER_LINE_FIELDS, "contact", "signatory"}
    unknown = sorted(set(value) - known)
    if unknown:
        raise DomainValidationError(f"Afzender: onbekend veld {', '.join(unknown)}.")
    out: dict[str, Any] = {}
    for name in SENDER_TEXT_FIELDS:
        out[name] = _text(value.get(name), f"Afzender, {name}")
    for name in SENDER_LINE_FIELDS:
        out[name] = _lines(value.get(name), f"Afzender, {name}")
    out["contact"] = _group(value.get("contact"), CONTACT_FIELDS, "Contactpersoon")
    out["signatory"] = _group(value.get("signatory"), SIGNATORY_FIELDS, "Ondertekenaar")
    return out


def _key(value: Any) -> str:
    key = _text(value, "De sleutel van een tekstblok", limit=40).lower()
    if not key or not key.replace("-", "").replace("_", "").isalnum():
        raise DomainValidationError(
            "De sleutel van een tekstblok bestaat uit letters, cijfers en streepjes."
        )
    return key


def check_blocks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise DomainValidationError("De tekstblokken zijn een lijst.")
    if len(value) > MAX_BLOCKS:
        raise DomainValidationError(f"Hooguit {MAX_BLOCKS} tekstblokken.")
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise DomainValidationError("Een tekstblok is een groep van velden.")
        unknown = sorted(set(raw) - {"key", "heading", "body", "hint", *BLOCK_FLAGS})
        if unknown:
            raise DomainValidationError(
                f"Tekstblok: onbekend veld {', '.join(unknown)}."
            )
        key = _key(raw.get("key"))
        if key in seen:
            raise DomainValidationError(f"De sleutel '{key}' komt twee keer voor.")
        seen.add(key)
        heading = _text(raw.get("heading"), f"De kop van '{key}'")
        if not heading:
            raise DomainValidationError(f"Het tekstblok '{key}' heeft een kop nodig.")
        try:
            body = quote_prose.clean(raw.get("body"))
        except quote_prose.ProseError as exc:
            raise DomainValidationError(f"Tekstblok '{key}': {exc}") from exc
        block: dict[str, Any] = {
            "key": key,
            "heading": heading,
            "body": body,
            "hint": _text(raw.get("hint"), f"De aanwijzing van '{key}'", limit=400),
        }
        for flag in BLOCK_FLAGS:
            default = flag in ("included", "numbered")
            flagged = raw.get(flag, default)
            if not isinstance(flagged, bool):
                raise DomainValidationError(f"Tekstblok '{key}': {flag} is aan of uit.")
            block[flag] = flagged
        if block["required"]:
            block["included"] = True
        blocks.append(block)
    if sum(1 for block in blocks if block["with_costs"]) > 1:
        raise DomainValidationError(
            "De tabel met bedragen staat in hooguit een onderdeel."
        )
    return blocks


def check_letter(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainValidationError("De brieftekst is een groep van velden.")
    unknown = sorted(set(value) - set(DEFAULT_LETTER))
    if unknown:
        raise DomainValidationError(f"Brieftekst: onbekend veld {', '.join(unknown)}.")
    annex = value.get("billing_annex", False)
    if not isinstance(annex, bool):
        raise DomainValidationError("De bijlage Factuurinformatie is aan of uit.")
    try:
        return {
            "opening": quote_prose.clean(value.get("opening")),
            "closing": quote_prose.clean(value.get("closing")),
            "billing_annex": annex,
        }
    except quote_prose.ProseError as exc:
        raise DomainValidationError(str(exc)) from exc


def sender_from_environment(settings: Settings | None = None) -> dict[str, Any]:
    """The starting value: the name and letterhead lines of the deployment."""
    settings = settings or get_settings()
    sender = json.loads(json.dumps(EMPTY_SENDER))
    sender["organisation"] = settings.ORGANISATION_NAME.strip()
    sender["part_of"] = [
        part.strip() for part in settings.LETTERHEAD_LINES.split("|") if part.strip()
    ]
    return sender


SENDER = instance_settings.declare(
    "quote.sender",
    None,
    lambda value: None if value is None else check_sender(value),
    "De afzender van offertes: organisatie, adressen, contactpersoon en ondertekenaar",
)
TEXT_BLOCKS = instance_settings.declare(
    "quote.text_blocks",
    None,
    lambda value: None if value is None else check_blocks(value),
    "De onderdelen van een offerte, met de standaardteksten van de organisatie",
)
LETTER = instance_settings.declare(
    "quote.letter",
    None,
    lambda value: None if value is None else check_letter(value),
    "De opening en de afsluiting van een offerte",
)
AI_DISCLOSURE = instance_settings.declare(
    "quote.ai_disclosure",
    False,
    instance_settings.boolean,
    "Vermeld in de offerte dat een taalmodel is gebruikt bij het opstellen",
)

AI_DISCLOSURE_SENTENCE = (
    "Bij het opstellen van deze offerte is een taalmodel gebruikt. De tekst is "
    "door een medewerker beoordeeld en vastgesteld."
)


async def current_sender(session: AsyncSession) -> dict[str, Any]:
    stored = await instance_settings.get(session, SENDER.key)
    return check_sender(stored) if stored is not None else sender_from_environment()


async def current_blocks(session: AsyncSession) -> list[dict[str, Any]]:
    stored = await instance_settings.get(session, TEXT_BLOCKS.key)
    return check_blocks(stored if stored is not None else DEFAULT_BLOCKS)


async def current_letter(session: AsyncSession) -> dict[str, Any]:
    stored = await instance_settings.get(session, LETTER.key)
    return check_letter(stored if stored is not None else DEFAULT_LETTER)


def placeholders(
    sender: dict[str, Any], *, year: int | str, billing: str = "per kwartaal"
) -> dict[str, str]:
    """What a standard text may refer to between braces.

    ``billing`` is how the assignment is billed, in words ("per kwartaal"):
    the letter then states the rhythm the system bills by.
    """
    contact = sender["contact"]
    name = contact["name"]
    if name and contact["role"]:
        name = f"{name} ({contact['role']})"
    reach = " of ".join(part for part in (contact["email"], contact["phone"]) if part)
    contact_line = ", ".join(part for part in (name, reach) if part)
    return {
        "organisatie": sender["organisation"],
        "eenheid": sender["unit"] or sender["organisation"],
        "opdrachtenadres": sender["orders_email"],
        "contactpersoon": contact_line,
        "jaar": str(year),
        "factureren": billing,
    }


def without_value_line(text: str, name: str) -> str:
    """The text without the line that holds only ``{name}``, and without the
    bold label right above it: a label says nothing when its value is missing."""
    pattern = (
        r"(?m)^(?:\*\*[^\n]*\*\*[ \t]*\n)?\{"
        + re.escape(name)
        + r"\}[ \t]*(?:\n(?:[ \t]*\n)?|\Z)"
    )
    return re.sub(pattern, "", text)


def fill_placeholders(text: str, values: dict[str, str]) -> str:
    """Replace ``{naam}`` by its value; an unknown name stays as written.

    A value that is empty takes its own line and the label above it along."""
    for name, value in values.items():
        if not value:
            text = without_value_line(text, name)
    for name, value in values.items():
        text = text.replace("{" + name + "}", value)
    return text


def profile_names() -> list[str]:
    if not _PROFILES.is_dir():
        return []
    return sorted(path.stem for path in _PROFILES.glob("*.json"))


def load_profile(name: str) -> dict[str, Any]:
    """A set of starting values for one organisation, shipped as data."""
    if not name.replace("-", "").replace("_", "").isalnum():
        raise DomainValidationError(f"Ongeldige naam voor een profiel: '{name}'.")
    path = _PROFILES / f"{name}.json"
    if not path.is_file():
        raise DomainValidationError(f"Er is geen profiel met de naam '{name}'.")
    return json.loads(path.read_text(encoding="utf-8"))


async def apply_profile(
    session: AsyncSession, name: str, *, actor: Person | None
) -> dict[str, Any]:
    """Set sender, text blocks and letter texts from a shipped profile.

    Fields a profile leaves out keep their current value: a contact person
    and a signatory are people, and a profile never names one.
    """
    profile = load_profile(name)
    values: dict[str, Any] = {}
    if "sender" in profile:
        sender = await current_sender(session)
        for key, value in profile["sender"].items():
            if isinstance(value, dict):
                sender[key] = {**sender.get(key, {}), **value}
            else:
                sender[key] = value
        values[SENDER.key] = sender
    if "text_blocks" in profile:
        values[TEXT_BLOCKS.key] = profile["text_blocks"]
    if "letter" in profile:
        values[LETTER.key] = {**DEFAULT_LETTER, **profile["letter"]}
    return await instance_settings.set_values(session, values, actor=actor)
