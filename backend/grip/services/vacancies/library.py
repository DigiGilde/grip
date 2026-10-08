"""The library of standard vacancy texts.

A standard text belongs to a role and is built from sections. Sections that
every role shares (what we offer, how to apply) are stored once and referred
to, so one change shows in every text. A text is plain structured text: a
section has a heading and a body of paragraphs, lists ("- ") and emphasis
("*...*"); nothing else.

Between braces a text names what a vacancy or a setting supplies
(``{functie}``, ``{schaal}``). A placeholder that cannot be filled, and a
passage a person still has to write, stay in the text as ``[vul aan: ...]``,
and a text with such a passage cannot be settled.

The shipped defaults are data (``grip/data/vacancy_texts``), loaded at start.
Loading never overwrites a text a person changed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Assignment, BudgetLine
from grip.models.catalogue_role import CatalogueRole
from grip.models.person import Person
from grip.models.vacancy import ContractType, TextKind, TextSource, Vacancy, VacancyText
from grip.models.vacancy_text_flow import (
    ORIGIN_DERIVED,
    ORIGIN_MANUAL,
    ORIGINS,
    VacancyTextSharedSection,
    VacancyTextTemplate,
)
from grip.services import catalogue_roles, instance_settings, quote_sender
from grip.services.errors import DomainValidationError, NotFoundError

_DATA = Path(__file__).resolve().parents[2] / "data" / "vacancy_texts"

PLACEHOLDERS: dict[str, str] = {
    "functie": "de functienaam van de vacature",
    "schaal": "de schaal van de vacature",
    "uren": "het aantal uren per week, uit de omvang in fte",
    "contract": "het soort contract",
    "standplaats": "de standplaats, uit de instellingen",
    "organisatie": "de naam van de organisatie, uit de afzender onder Beheer",
    "eenheid": "de naam van het onderdeel, uit de instellingen",
    "website": "de website, uit de instellingen",
    "contact": "bij wie een sollicitant terecht kan, uit de instellingen",
    "sluitingsdatum": "de datum tot wanneer reageren kan",
    "opdracht": "de naam van de opdracht waar de rol bij hoort",
}

CONTRACT_SENTENCES: dict[str, str] = {
    ContractType.temporary_project.value: (
        "Een tijdelijk contract voor de duur van het project"
    ),
    ContractType.temporary_before_permanent.value: (
        "Een jaarcontract met uitzicht op een vast dienstverband"
    ),
}

OPEN_MARK = "[vul aan"
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,58}$")
_FULL_WEEK = Decimal("36")
MAX_SECTIONS = 20
MAX_BODY = 8000


# --- settings ---------------------------------------------------------------

_TEXT_SETTING_FIELDS = ("unit_name", "location", "website", "contact")


def _check_text_settings(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - set(_TEXT_SETTING_FIELDS):
        raise DomainValidationError(
            "De instellingen voor vacatureteksten kennen alleen: "
            + ", ".join(_TEXT_SETTING_FIELDS)
            + "."
        )
    result = {}
    for name in _TEXT_SETTING_FIELDS:
        text = value.get(name, "")
        if not isinstance(text, str) or len(text) > 300:
            raise DomainValidationError(
                "Een instelling is een tekst van hooguit 300 tekens."
            )
        result[name] = text.strip()
    if result["website"] and not result["website"].startswith("https://"):
        raise DomainValidationError("De website begint met https://.")
    return result


TEXT_SETTINGS = instance_settings.declare(
    "vacancy.text_settings",
    {name: "" for name in _TEXT_SETTING_FIELDS},
    _check_text_settings,
    "Wat een standaard vacaturetekst invult: naam van het onderdeel, "
    "standplaats, website en bij wie een sollicitant terecht kan.",
)


# --- the markup ---------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    key: str
    heading: str
    body: str
    shared: bool = False


def render(sections: list[Section]) -> str:
    """Sections as one text: a heading line ``## ...`` and the body."""
    parts = []
    for section in sections:
        body = section.body.strip()
        if not body:
            continue
        parts.append(f"## {section.heading}\n\n{body}" if section.heading else body)
    return "\n\n".join(parts)


def split(text: str) -> list[tuple[str, str]]:
    """A text back into (heading, body) pairs; text before a heading has none."""
    result: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            result.append((line[3:].strip(), []))
        else:
            result[-1][1].append(line)
    pairs = [(heading, "\n".join(lines).strip()) for heading, lines in result]
    return [(heading, body) for heading, body in pairs if heading or body]


def open_passages(text: str) -> list[str]:
    """What still has to be filled in before the text can be settled."""
    found = [f"{{{name}}}" for name in _PLACEHOLDER.findall(text)]
    found += re.findall(r"\[vul aan[^\]]*\]", text)
    return found


def check_sections(value: Any, shared_keys: set[str]) -> list[dict[str, Any]]:
    """Validate the sections of a template as they are stored."""
    if not isinstance(value, list) or not value:
        raise DomainValidationError("Een standaardtekst heeft minstens één onderdeel.")
    if len(value) > MAX_SECTIONS:
        raise DomainValidationError(
            f"Een standaardtekst heeft hooguit {MAX_SECTIONS} onderdelen."
        )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise DomainValidationError("Een onderdeel is een object.")
        if "shared" in raw:
            key = raw["shared"]
            if key not in shared_keys:
                raise DomainValidationError(
                    f"Het gedeelde onderdeel '{key}' bestaat niet."
                )
            entry: dict[str, Any] = {"shared": key}
        else:
            key = raw.get("key")
            if not isinstance(key, str) or not _KEY.match(key):
                raise DomainValidationError(
                    "De sleutel van een onderdeel bestaat uit kleine letters, "
                    "cijfers en onderstrepingstekens."
                )
            heading = raw.get("heading", "")
            body = raw.get("body", "")
            if not isinstance(heading, str) or len(heading) > 200:
                raise DomainValidationError(
                    "Een kop is een tekst van hooguit 200 tekens."
                )
            if not isinstance(body, str) or not body.strip() or len(body) > MAX_BODY:
                raise DomainValidationError(
                    f"Een onderdeel heeft tekst, hooguit {MAX_BODY} tekens."
                )
            if "<" in body and re.search(r"<[a-zA-Z/!]", body):
                raise DomainValidationError(
                    "Een onderdeel bevat alleen tekst, lijsten en nadruk, geen HTML."
                )
            entry = {"key": key, "heading": heading.strip(), "body": body.strip()}
            if raw.get("optional") == "assignment":
                entry["optional"] = "assignment"
        if key in seen:
            raise DomainValidationError(f"Het onderdeel '{key}' staat er twee keer in.")
        seen.add(key)
        result.append(entry)
    return result


# --- reading ------------------------------------------------------------------


async def shared_sections(db: AsyncSession) -> list[VacancyTextSharedSection]:
    rows = await db.scalars(
        select(VacancyTextSharedSection).order_by(
            VacancyTextSharedSection.position, VacancyTextSharedSection.key
        )
    )
    return list(rows)


async def list_templates(
    db: AsyncSession, *, active_only: bool = False
) -> list[VacancyTextTemplate]:
    query = select(VacancyTextTemplate).order_by(
        func.lower(VacancyTextTemplate.role_name)
    )
    if active_only:
        query = query.where(VacancyTextTemplate.is_active.is_(True))
    return list(await db.scalars(query))


async def get_template(db: AsyncSession, template_id: UUID) -> VacancyTextTemplate:
    template = await db.get(VacancyTextTemplate, template_id)
    if template is None:
        raise NotFoundError("Standaardtekst", template_id)
    return template


def status_of(template: VacancyTextTemplate) -> str:
    """Where a standard text stands: who wrote it and whether it was read."""
    if template.changed_at is not None:
        return "changed"
    if template.origin == ORIGIN_DERIVED and template.reviewed_at is None:
        return "derived_unread"
    return template.origin


def usage_of_shared(templates: list[VacancyTextTemplate]) -> dict[str, list[str]]:
    """Per shared section the roles whose text uses it."""
    usage: dict[str, list[str]] = {}
    for template in templates:
        for entry in template.sections:
            if "shared" in entry:
                usage.setdefault(entry["shared"], []).append(template.role_name)
    return usage


# --- finding the text of a vacancy -------------------------------------------


def _fold(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


@dataclass(frozen=True)
class Match:
    template: VacancyTextTemplate
    # role: the role of the budget line. name: the function title or an
    # alias. function_group: the nearest text, of another role.
    how: str


async def find_template(db: AsyncSession, vacancy: Vacancy) -> Match | None:
    templates = await list_templates(db, active_only=True)
    if not templates:
        return None
    role_id = None
    role_name = None
    if vacancy.budget_line_id is not None:
        line = await db.get(BudgetLine, vacancy.budget_line_id)
        if line is not None:
            role_id = getattr(line, "role_id", None)
            role_name = line.role
    if role_id is not None:
        for template in templates:
            if template.catalogue_role_id == role_id:
                return Match(template, "role")
    wanted = {_fold(vacancy.function_title), _fold(role_name)} - {""}
    for template in templates:
        names = {
            _fold(template.role_name),
            *(_fold(alias) for alias in template.aliases),
        }
        if wanted & names:
            return Match(template, "name")
    # A title that contains the role, "Senior software engineer RegelRecht".
    title = _fold(vacancy.function_title)
    best: VacancyTextTemplate | None = None
    for template in templates:
        name = _fold(template.role_name)
        if (
            name
            and name in title
            and (best is None or len(name) > len(_fold(best.role_name)))
        ):
            best = template
    if best is not None:
        return Match(best, "name")
    group = _fold(vacancy.fgr_function_name)
    if group:
        near = [t for t in templates if _fold(t.function_group) == group]
        if vacancy.scale is not None:
            near.sort(
                key=lambda t: (
                    not (
                        (t.scale_min or 0) <= vacancy.scale <= (t.scale_max or 99)  # type: ignore[operator]
                    ),
                    t.role_name,
                )
            )
        if near:
            return Match(near[0], "function_group")
    return None


async def neighbours(
    db: AsyncSession, template: VacancyTextTemplate, limit: int = 1
) -> list[VacancyTextTemplate]:
    """Standard texts close to this one, as further examples for a draft."""
    others = [
        t for t in await list_templates(db, active_only=True) if t.id != template.id
    ]
    others.sort(
        key=lambda t: (
            _fold(t.function_group) != _fold(template.function_group),
            abs((t.scale_min or 0) - (template.scale_min or 0)),
            t.role_name,
        )
    )
    return others[:limit]


# --- filling a text ----------------------------------------------------------


def _hours(fte: Decimal | None) -> str | None:
    if fte is None:
        return None
    hours = (Decimal(fte) * _FULL_WEEK).quantize(Decimal("1"))
    return str(hours)


async def values_for(db: AsyncSession, vacancy: Vacancy) -> dict[str, str]:
    """What the placeholders stand for on this vacancy; missing ones are absent."""
    settings = _check_text_settings(await instance_settings.get(db, TEXT_SETTINGS.key))
    sender = await quote_sender.current_sender(db)
    assignment_name = None
    if vacancy.budget_line_id is not None:
        line = await db.get(BudgetLine, vacancy.budget_line_id)
        if line is not None:
            assignment = await db.get(Assignment, line.assignment_id)
            assignment_name = assignment.name if assignment else None
    organisation = (sender.get("organisation") or "").strip()
    values = {
        "functie": vacancy.function_title,
        "schaal": str(vacancy.scale) if vacancy.scale is not None else None,
        "uren": _hours(vacancy.fte),
        "contract": CONTRACT_SENTENCES.get(vacancy.contract_type or ""),
        "standplaats": settings["location"],
        "organisatie": organisation,
        "eenheid": settings["unit_name"] or organisation,
        "website": settings["website"],
        "contact": settings["contact"],
        "opdracht": assignment_name,
    }
    return {name: value for name, value in values.items() if value}


@dataclass
class Resolved:
    sections: list[Section]
    # Placeholders that could not be filled, by name.
    missing: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return render(self.sections)


def _fill(text: str, values: dict[str, str], missing: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in values:
            return values[name]
        if name not in missing:
            missing.append(name)
        return f"[vul aan: {PLACEHOLDERS.get(name, name)}]"

    return _PLACEHOLDER.sub(replace, text)


def resolve(
    template: VacancyTextTemplate,
    shared: dict[str, VacancyTextSharedSection],
    values: dict[str, str],
    *,
    only: str | None = None,
) -> Resolved:
    """The sections of a template with the placeholders filled.

    ``only`` keeps the shared sections (``"shared"``) or the role's own
    (``"own"``); a section that depends on an assignment is left out when the
    vacancy has none.
    """
    resolved = Resolved(sections=[])
    for entry in template.sections:
        if "shared" in entry:
            section = shared.get(entry["shared"])
            if section is None or only == "own":
                continue
            key, heading, body, is_shared = (
                section.key,
                section.heading,
                section.body,
                True,
            )
        else:
            if only == "shared":
                continue
            if entry.get("optional") == "assignment" and "opdracht" not in values:
                continue
            key, heading, body, is_shared = (
                entry["key"],
                entry.get("heading", ""),
                entry["body"],
                False,
            )
        resolved.sections.append(
            Section(
                key=key,
                heading=_fill(heading, values, resolved.missing),
                body=_fill(body, values, resolved.missing),
                shared=is_shared,
            )
        )
    return resolved


def template_label(template: VacancyTextTemplate) -> str:
    moment = template.changed_at or template.updated_at or datetime.now(UTC)
    version = template.shipped_version if template.changed_at is None else None
    return f"{template.role_name}, versie {version or moment.date().isoformat()}"


async def resolve_for_vacancy(
    db: AsyncSession, vacancy: Vacancy, template: VacancyTextTemplate, **kwargs: Any
) -> Resolved:
    shared = {section.key: section for section in await shared_sections(db)}
    return resolve(template, shared, await values_for(db, vacancy), **kwargs)


async def use_standard_text(
    db: AsyncSession, vacancy: Vacancy, *, actor: Person | None
) -> tuple[VacancyText, Match, list[str]]:
    """Start the vacancy text from the standard text of its role.

    The result is a draft like any other: a person changes and settles it.
    """
    match = await find_template(db, vacancy)
    if match is None:
        raise DomainValidationError(
            "Er is geen standaardtekst voor deze rol, en ook geen tekst van een "
            "verwante rol. Voeg er een toe onder Standaardteksten, of schrijf "
            "de tekst zelf."
        )
    resolved = await resolve_for_vacancy(db, vacancy, match.template)
    text = VacancyText(
        vacancy_id=vacancy.id,
        kind=TextKind.vacancy_text.value,
        body=resolved.text,
        source=TextSource.template.value,
        template_label=template_label(match.template),
        created_by_id=actor.id if actor else None,
    )
    db.add(text)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="vacancy_text",
        entity_id=text.id,
        new_value={
            "kind": text.kind,
            "source": text.source,
            "template": text.template_label,
            "match": match.how,
        },
        vacancy_id=vacancy.id,
    )
    return text, match, resolved.missing


# --- changing -----------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


async def update_shared_section(
    db: AsyncSession, key: str, *, heading: str, body: str, actor: Person
) -> VacancyTextSharedSection:
    section = await db.get(VacancyTextSharedSection, key)
    if section is None:
        raise NotFoundError("Gedeeld onderdeel", key)
    if not body.strip() or len(body) > MAX_BODY or len(heading) > 200:
        raise DomainValidationError("Het onderdeel heeft een kop en tekst nodig.")
    old = {"heading": section.heading, "body": section.body}
    section.heading = heading.strip()
    section.body = body.strip()
    section.changed_by_id = actor.id
    section.changed_at = _now()
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy_text_shared_section",
        entity_id=key,
        old_value=old,
        new_value={"heading": section.heading, "body": section.body},
    )
    return section


async def _link_role(
    db: AsyncSession, role_name: str, aliases: list[str], *, actor: Person | None
) -> CatalogueRole:
    for name in (role_name, *aliases):
        found = await catalogue_roles.find_by_name(db, name)
        if found is not None:
            return found
    role = CatalogueRole(
        name=role_name, source="manual", created_by_id=actor.id if actor else None
    )
    db.add(role)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="catalogue_role",
        entity_id=role.id,
        new_value={"name": role.name, "source": role.source, "reason": "standard_text"},
    )
    return role


async def save_template(
    db: AsyncSession,
    template_id: UUID | None,
    *,
    actor: Person,
    role_name: str,
    sections: Any,
    aliases: list[str] | None = None,
    scale_min: int | None = None,
    scale_max: int | None = None,
    function_group: str | None = None,
    copy_of: UUID | None = None,
) -> VacancyTextTemplate:
    """Change a standard text, or add one (optionally as a copy of another)."""
    shared_keys = {section.key for section in await shared_sections(db)}
    name = " ".join(role_name.split())
    if not name:
        raise DomainValidationError("Geef de rol waarvoor de tekst is.")
    if scale_min is not None and scale_max is not None and scale_min > scale_max:
        raise DomainValidationError("De laagste schaal is hoger dan de hoogste.")
    clash = await db.scalar(
        select(VacancyTextTemplate).where(
            func.lower(VacancyTextTemplate.role_name) == name.lower()
        )
    )
    if template_id is None:
        if clash is not None:
            raise DomainValidationError(
                f"Er is al een standaardtekst voor '{clash.role_name}'."
            )
        if copy_of is not None and sections is None:
            sections = (await get_template(db, copy_of)).sections
        template = VacancyTextTemplate(
            role_name=name,
            origin=ORIGIN_MANUAL,
            sections=check_sections(sections, shared_keys),
        )
        db.add(template)
        action, old = CREATE, None
    else:
        template = await get_template(db, template_id)
        if clash is not None and clash.id != template.id:
            raise DomainValidationError(
                f"Er is al een standaardtekst voor '{clash.role_name}'."
            )
        old = {"role_name": template.role_name, "sections": template.sections}
        template.role_name = name
        template.sections = check_sections(sections, shared_keys)
        action = UPDATE
    template.aliases = sorted(
        {" ".join(a.split()) for a in (aliases or []) if a.strip()}
    )
    template.scale_min = scale_min
    template.scale_max = scale_max
    template.function_group = (function_group or "").strip() or None
    template.changed_by_id = actor.id
    template.changed_at = _now()
    # Who rewrites a text has read it.
    template.reviewed_by_id = actor.id
    template.reviewed_at = template.changed_at
    role = await _link_role(db, name, template.aliases, actor=actor)
    template.catalogue_role_id = role.id
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=action,
        entity="vacancy_text_template",
        entity_id=template.id,
        old_value=old,
        new_value={"role_name": template.role_name, "sections": template.sections},
    )
    return template


async def mark_read(
    db: AsyncSession, template_id: UUID, *, actor: Person
) -> VacancyTextTemplate:
    """A person read a derived text and stands for it."""
    template = await get_template(db, template_id)
    if template.reviewed_at is None:
        template.reviewed_by_id = actor.id
        template.reviewed_at = _now()
        await db.flush()
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="vacancy_text_template",
            entity_id=template.id,
            new_value={"reviewed": True},
        )
    return template


async def set_active(
    db: AsyncSession, template_id: UUID, active: bool, *, actor: Person
) -> VacancyTextTemplate:
    template = await get_template(db, template_id)
    if template.is_active != active:
        template.is_active = active
        await db.flush()
        record_audit(
            db,
            actor=actor,
            action=UPDATE,
            entity="vacancy_text_template",
            entity_id=template.id,
            new_value={"is_active": active},
        )
    return template


# --- loading the shipped library -----------------------------------------------


def profile_names() -> list[str]:
    return sorted(path.stem for path in _DATA.glob("*.json"))


def read_profile(name: str) -> dict[str, Any]:
    path = _DATA / f"{name}.json"
    if not _KEY.match(name) or not path.is_file():
        raise DomainValidationError(f"De bibliotheek '{name}' bestaat niet.")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@dataclass
class LoadResult:
    added: int = 0
    updated: int = 0
    kept: int = 0


async def load_profile(db: AsyncSession, name: str) -> LoadResult:
    """Bring the shipped library in. Idempotent.

    New texts are added. A text that came from an earlier shipped version and
    that nobody changed follows the new version. A text a person changed, or
    added, is left as it is.
    """
    data = read_profile(name)
    version = str(data["version"])
    result = LoadResult()

    for position, raw in enumerate(data.get("shared_sections", [])):
        section = await db.get(VacancyTextSharedSection, raw["key"])
        if section is None:
            db.add(
                VacancyTextSharedSection(
                    key=raw["key"],
                    heading=raw["heading"],
                    body=raw["body"],
                    position=position,
                    shipped_version=version,
                )
            )
            result.added += 1
        elif section.changed_at is None and section.shipped_version != version:
            section.heading, section.body = raw["heading"], raw["body"]
            section.position, section.shipped_version = position, version
            result.updated += 1
        else:
            result.kept += 1
    await db.flush()
    shared_keys = {section.key for section in await shared_sections(db)}

    for raw in data.get("templates", []):
        if raw.get("origin") not in ORIGINS:
            raise DomainValidationError("Onbekende herkomst in de bibliotheek.")
        sections = check_sections(raw["sections"], shared_keys)
        template = await db.scalar(
            select(VacancyTextTemplate).where(
                func.lower(VacancyTextTemplate.role_name) == raw["role"].lower()
            )
        )
        if template is None:
            role = await _link_role(db, raw["role"], raw.get("aliases", []), actor=None)
            db.add(
                VacancyTextTemplate(
                    catalogue_role_id=role.id,
                    role_name=raw["role"],
                    aliases=raw.get("aliases", []),
                    scale_min=raw.get("scale_min"),
                    scale_max=raw.get("scale_max"),
                    function_group=raw.get("function_group"),
                    origin=raw["origin"],
                    sections=sections,
                    shipped_version=version,
                )
            )
            result.added += 1
        elif template.changed_at is None and template.shipped_version not in (
            None,
            version,
        ):
            template.sections = sections
            template.aliases = raw.get("aliases", [])
            template.scale_min = raw.get("scale_min")
            template.scale_max = raw.get("scale_max")
            template.function_group = raw.get("function_group")
            template.origin = raw["origin"]
            template.shipped_version = version
            result.updated += 1
        else:
            result.kept += 1
    await db.flush()

    # The settings start from the library when nobody set them.
    current = await instance_settings.get(db, TEXT_SETTINGS.key)
    shipped = data.get("settings") or {}
    if shipped and not any(current.values()):
        await instance_settings.set_values(
            db, {TEXT_SETTINGS.key: {**current, **shipped}}, actor=None
        )
    if result.added or result.updated:
        record_audit(
            db,
            actor=None,
            action=UPDATE,
            entity="vacancy_text_library",
            entity_id=name,
            new_value={
                "version": version,
                "added": result.added,
                "updated": result.updated,
            },
        )
    return result
