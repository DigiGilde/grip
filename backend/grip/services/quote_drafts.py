"""The text of a quote in preparation, and how it is frozen into a quote.

A draft belongs to an assignment and holds the words of the next quote: the
subject, the addressee, the salutation, the sections and the closing. The
numbers are not here; they come from the budget when the quote is made.

Shape of ``QuoteDraft.content``::

    {
      "subject": "...", "addressee": ["..."], "salutation": "...",
      "opening": "...", "closing": "...", "billing_annex": false,
      "client_signatory": {"on_behalf_of", "name", "function", "organisation"},
      "sections": [
        {"key", "heading", "body", "hint", "included", "with_costs",
         "numbered", "draftable",
         "origin": "empty" | "standard" | "written" | "generated",
         "generated": {"model", "prompt_version", "at"} | null,
         "settled": true,
         "required": false, "custom": false,
         "version": 3, "changed_by": "...", "changed_at": "..."}
      ]
    }

A section that a language model drafted is ``settled: false`` until a person
saves it. A quote cannot be made while an included section is unsettled.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Assignment
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote_draft import QuoteDraft
from grip.repositories.domain import AssignmentRepository
from grip.services import instance_settings, quote_prose, quote_sender
from grip.services.errors import DomainError, DomainValidationError
from grip.services.llm import ChatClient, get_chat_client
from grip.services.quote_drafting import (
    MAX_OTHER_SECTIONS,
    PROMPT_VERSION,
    RoleFact,
    SectionInput,
    SectionInputError,
    build_prompt,
    ensure_no_person_names,
)

ORIGINS = ("empty", "standard", "written", "generated")
SIGNATORY_FIELDS = ("on_behalf_of", "name", "function", "organisation")
LETTER_FIELDS = ("subject", "salutation", "opening", "closing")
MAX_SECTIONS = 30


@dataclass(frozen=True)
class FrozenLetter:
    """The text as it goes into a quote, and where each section came from."""

    letter: dict[str, Any]
    provenance: list[dict[str, Any]]


class DraftConflictError(DomainError):
    """Someone else saved this part of the draft in the meantime."""

    def __init__(self, what: str, by: str | None, at: str | None) -> None:
        who = f" door {by}" if by else ""
        super().__init__(
            f"{what} is intussen gewijzigd{who}. Bekijk de nieuwe tekst en sla "
            "daarna opnieuw op."
        )
        self.changed_by = by
        self.changed_at = at


def _normalise(content: dict[str, Any]) -> dict[str, Any]:
    """A draft from before versions and section rules, in today's shape."""
    content.setdefault("head_version", 0)
    content.setdefault("outline_version", 0)
    for section in content["sections"]:
        section.setdefault("version", 0)
        section.setdefault("required", False)
        section.setdefault("custom", False)
    return content


def section_rules(section: dict[str, Any]) -> dict[str, bool]:
    """What a writer may do with a section, from the organisation's outline.

    - ``optional``: may be left out of this quote. Not a section the
      organisation requires, and not the one that carries the amounts.
    - ``removable``: may be taken out of the draft altogether. Only a
      section the writer added; one from the outline is left out instead.
    - ``movable``: may change place. A required section keeps its place
      among the other required sections.
    """
    fixed = bool(section.get("required")) or bool(section.get("with_costs"))
    return {
        "optional": not fixed,
        "removable": bool(section.get("custom")),
        "movable": not section.get("required"),
    }


def _check_version(
    expected: int | None, current: int, what: str, holder: dict[str, Any]
) -> None:
    if expected is not None and expected != current:
        raise DraftConflictError(
            what, holder.get("changed_by"), holder.get("changed_at")
        )


def _stamp(holder: dict[str, Any], key: str, actor: Person | None) -> None:
    holder[key] = int(holder.get(key, 0)) + 1
    holder["changed_by"] = actor.name if actor is not None else None
    holder["changed_at"] = datetime.now(UTC).isoformat()


def _section_from_block(
    block: dict[str, Any], values: dict[str, str]
) -> dict[str, Any]:
    body = quote_sender.fill_placeholders(block["body"], values)
    return {
        "key": block["key"],
        "heading": block["heading"],
        "body": body,
        "hint": block["hint"],
        "included": block["included"],
        "with_costs": block["with_costs"],
        "numbered": block["numbered"],
        "draftable": block["draftable"],
        "required": block["required"],
        "custom": False,
        "version": 0,
        "origin": "standard" if body else "empty",
        "generated": None,
        "settled": True,
    }


async def client_of(
    session: AsyncSession, assignment: Assignment
) -> Organisation | None:
    if assignment.client_organisation_id is None:
        return None
    return await session.get(Organisation, assignment.client_organisation_id)


def years_text(years: list[int]) -> str:
    """Years as they are said: "2027", "2026 en 2027", "2026, 2027 en 2028"."""
    words = [str(year) for year in sorted(set(years))]
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " en " + words[-1]


async def rate_years(
    session: AsyncSession, assignment: Assignment, *, today: date | None = None
) -> list[int]:
    """The years whose rates price this quote: those the personnel lines of
    the budget run over. Without such a line the years of the assignment,
    and without a period this year."""
    years: set[int] = set()
    for line in await AssignmentRepository(session).budget_lines([assignment.id]):
        if line.kind == "personnel" and line.start_date and line.end_date:
            years.update(range(line.start_date.year, line.end_date.year + 1))
    if not years and assignment.start_date and assignment.end_date:
        years.update(range(assignment.start_date.year, assignment.end_date.year + 1))
    if not years:
        years.add((today or datetime.now(UTC).date()).year)
    return sorted(years)


async def _placeholder_values(
    session: AsyncSession,
    assignment: Assignment,
    sender: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, str]:
    # The letter states the rhythm the assignment is billed by.
    from grip.services import billing_deliveries
    from grip.services.billing_periods import RHYTHM_TEXTS

    terms = await billing_deliveries.terms_of(session, assignment.id)
    return quote_sender.placeholders(
        sender,
        year=years_text(await rate_years(session, assignment, today=today)),
        billing=RHYTHM_TEXTS[terms.rhythm],
    )


_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def _matches(template: str, text: str) -> bool:
    parts = _PLACEHOLDER.split(template)
    pattern = "".join(
        ".*?" if index % 2 else re.escape(part) for index, part in enumerate(parts)
    )
    return re.fullmatch(pattern, text, re.DOTALL) is not None


def _follows(template: str, text: str) -> bool:
    """Whether a text is still the standard text, whatever stood between its
    braces when it was filled in. A value that was empty then took its line
    and its label out of the text, so the template without them counts too."""
    if _matches(template, text):
        return True
    names = sorted(set(_PLACEHOLDER.findall(template)))
    shortened = template
    for name in names:
        without = quote_sender.without_value_line(template, name)
        if without != template and _matches(without, text):
            return True
        shortened = quote_sender.without_value_line(shortened, name)
    return shortened != template and _matches(shortened, text)


# What a standard text can ask of the sender, in the words of the Beheer page.
_SENDER_NEEDS = {
    "organisatie": "de naam van de organisatie",
    "eenheid": "de naam van de organisatie",
    "contactpersoon": "de contactpersoon",
    "opdrachtenadres": "het adres voor opdrachten",
}


async def _bring_up_to_date(
    session: AsyncSession,
    assignment: Assignment,
    content: dict[str, Any],
    sender: dict[str, Any],
) -> list[str]:
    """Fill the standard texts of a draft with what holds now, in place.

    A standard text is filled in when the draft starts; the budget, the
    billing terms and the sender can change afterwards. A text nobody changed
    follows them: the years of the rates, the rhythm of billing, the contact
    person. A text a person wrote is left alone.

    Returns what the sender still lacks for the texts this draft uses.
    """
    values = await _placeholder_values(session, assignment, sender)
    letter = await quote_sender.current_letter(session)
    blocks = {
        block["key"]: block for block in await quote_sender.current_blocks(session)
    }
    used: set[str] = set()

    for field_name in ("opening", "closing"):
        template = letter[field_name]
        if template and _follows(template, content.get(field_name) or ""):
            content[field_name] = quote_sender.fill_placeholders(template, values)
            used.update(_PLACEHOLDER.findall(template))
    for section in content["sections"]:
        block = blocks.get(section["key"])
        if (
            block is None
            or section.get("origin") != "standard"
            or section.get("custom")
        ):
            continue
        if not _follows(block["body"], section["body"]):
            continue
        section["body"] = quote_sender.fill_placeholders(block["body"], values)
        if section["included"]:
            used.update(_PLACEHOLDER.findall(block["body"]))

    missing: list[str] = []
    for name in sorted(used):
        need = _SENDER_NEEDS.get(name)
        if need and not values.get(name) and need not in missing:
            missing.append(need)
    if not sender["signatory"]["name"]:
        missing.append("de ondertekenaar")
    return missing


def sender_problem(missing: list[str]) -> str | None:
    """One sentence for what the sender lacks, or None."""
    if not missing:
        return None
    if len(missing) == 1:
        named = missing[0]
    else:
        named = ", ".join(missing[:-1]) + " en " + missing[-1]
    return f"Onder Beheer, Afzender ontbreekt nog: {named}."


async def start_content(
    session: AsyncSession, assignment: Assignment, *, today: date | None = None
) -> dict[str, Any]:
    """The draft a new quote starts from: the outline and standard texts of
    the organisation, with what is known of the assignment filled in."""
    today = today or datetime.now(UTC).date()
    sender = await quote_sender.current_sender(session)
    letter = await quote_sender.current_letter(session)
    blocks = await quote_sender.current_blocks(session)
    values = await _placeholder_values(session, assignment, sender, today=today)
    client = await client_of(session, assignment)
    addressee = [client.name] if client is not None else []
    if assignment.client_contact:
        addressee.append(f"T.a.v. {assignment.client_contact}")
    return {
        "subject": f"Offerte {assignment.name}",
        "addressee": addressee,
        "salutation": "Geachte heer, mevrouw,",
        "opening": quote_sender.fill_placeholders(letter["opening"], values),
        "closing": quote_sender.fill_placeholders(letter["closing"], values),
        "billing_annex": letter["billing_annex"],
        "client_signatory": {
            "on_behalf_of": client.name if client is not None else "",
            "name": "",
            "function": "",
            "organisation": client.name if client is not None else "",
        },
        "sections": [_section_from_block(block, values) for block in blocks],
        "head_version": 0,
        "outline_version": 0,
    }


async def find_draft(session: AsyncSession, assignment_id: UUID) -> QuoteDraft | None:
    return await session.get(QuoteDraft, assignment_id)


async def read_draft(
    session: AsyncSession, assignment: Assignment
) -> tuple[dict[str, Any], bool]:
    """The content of the draft and whether it was saved before. A draft
    that was never saved is the organisation's start, not yet a row."""
    row = await find_draft(session, assignment.id)
    if row is not None:
        content = _normalise(copy.deepcopy(row.content))
        await _bring_up_to_date(
            session, assignment, content, await quote_sender.current_sender(session)
        )
        return content, True
    return await start_content(session, assignment), False


async def sender_gaps(session: AsyncSession, assignment: Assignment) -> list[str]:
    """What the sender still lacks for the letter of this assignment."""
    row = await find_draft(session, assignment.id)
    content = (
        _normalise(copy.deepcopy(row.content))
        if row is not None
        else await start_content(session, assignment)
    )
    return await _bring_up_to_date(
        session, assignment, content, await quote_sender.current_sender(session)
    )


def _prose(value: Any, where: str) -> str:
    try:
        return quote_prose.clean(value)
    except quote_prose.ProseError as exc:
        raise DomainValidationError(f"{where}: {exc}") from exc


def _line(value: Any, where: str, limit: int = 300) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DomainValidationError(f"{where} is tekst.")
    value = " ".join(value.split())
    if len(value) > limit:
        raise DomainValidationError(f"{where} is te lang (hooguit {limit} tekens).")
    return value


async def _save(
    session: AsyncSession,
    assignment: Assignment,
    content: dict[str, Any],
    *,
    actor: Person | None,
    change: dict[str, Any],
) -> dict[str, Any]:
    row = await find_draft(session, assignment.id)
    if row is None:
        session.add(
            QuoteDraft(
                assignment_id=assignment.id,
                content=content,
                updated_by_id=actor.id if actor is not None else None,
            )
        )
        action = CREATE
    else:
        row.content = content
        row.updated_by_id = actor.id if actor is not None else None
        action = UPDATE
    await session.flush()
    # What changed, not the text itself: the text is in the draft and, once
    # a quote is made, in the quote.
    record_audit(
        session,
        actor=actor,
        action=action,
        entity="quote_draft",
        entity_id=assignment.id,
        new_value=change,
        assignment_id=assignment.id,
    )
    return copy.deepcopy(content)


async def update_letter(
    session: AsyncSession,
    assignment: Assignment,
    fields: dict[str, Any],
    *,
    actor: Person | None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Change the parts around the sections. Only the fields given change."""
    content, _ = await read_draft(session, assignment)
    _check_version(
        expected_version, content["head_version"], "De kop van de offerte", content
    )
    known = {*LETTER_FIELDS, "addressee", "client_signatory", "billing_annex"}
    unknown = sorted(set(fields) - known)
    if unknown:
        raise DomainValidationError(f"Onbekend veld: {', '.join(unknown)}.")
    if "subject" in fields:
        content["subject"] = _line(fields["subject"], "Het onderwerp")
    if "salutation" in fields:
        content["salutation"] = _line(fields["salutation"], "De aanhef")
    if "opening" in fields:
        content["opening"] = _prose(fields["opening"], "De opening")
    if "closing" in fields:
        content["closing"] = _prose(fields["closing"], "De afsluiting")
    if "addressee" in fields:
        raw = fields["addressee"]
        if isinstance(raw, str):
            raw = raw.split("\n")
        if not isinstance(raw, list) or len(raw) > 8:
            raise DomainValidationError("De geadresseerde is hooguit acht regels.")
        lines = [_line(item, "Een regel van de geadresseerde") for item in raw]
        content["addressee"] = [item for item in lines if item]
    if "client_signatory" in fields:
        raw = fields["client_signatory"] or {}
        if not isinstance(raw, dict) or set(raw) - set(SIGNATORY_FIELDS):
            raise DomainValidationError(
                "De ondertekenaar van de opdrachtgever heeft de velden namens, "
                "naam, functie en organisatie."
            )
        content["client_signatory"] = {
            name: _line(raw.get(name), "De ondertekenaar van de opdrachtgever")
            for name in SIGNATORY_FIELDS
        }
    if "billing_annex" in fields:
        if not isinstance(fields["billing_annex"], bool):
            raise DomainValidationError("De bijlage Factuurinformatie is aan of uit.")
        content["billing_annex"] = fields["billing_annex"]
    _stamp(content, "head_version", actor)
    return await _save(
        session,
        assignment,
        content,
        actor=actor,
        change={"changed": sorted(fields)},
    )


def _find(content: dict[str, Any], key: str) -> dict[str, Any]:
    for section in content["sections"]:
        if section["key"] == key:
            return section
    raise DomainValidationError(f"De offerte heeft geen onderdeel '{key}'.")


async def save_section(
    session: AsyncSession,
    assignment: Assignment,
    key: str,
    *,
    actor: Person | None,
    body: str | None = None,
    heading: str | None = None,
    included: bool | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """A person saves a section: the text is settled from here on.

    This is the step that makes a drafted text the writer's own. A text that
    a model drafted keeps saying so, with ``settled`` true.
    """
    content, _ = await read_draft(session, assignment)
    section = _find(content, key)
    _check_version(
        expected_version,
        section["version"],
        f"Het onderdeel '{section['heading']}'",
        section,
    )
    if heading is not None:
        heading = _line(heading, "De kop", 200)
        if not heading:
            raise DomainValidationError("Een onderdeel heeft een kop nodig.")
        section["heading"] = heading
    if included is not None:
        if not included and not section_rules(section)["optional"]:
            raise DomainValidationError(
                f"Het onderdeel '{section['heading']}' staat in elke offerte en kan "
                "niet worden weggelaten."
            )
        section["included"] = bool(included)
    if body is not None:
        text = _prose(body, f"Onderdeel '{section['heading']}'")
        if text != section["body"] and section["origin"] != "generated":
            section["origin"] = "written" if text else "empty"
        elif not text:
            section["origin"] = "empty"
            section["generated"] = None
        section["body"] = text
        section["settled"] = True
    _stamp(section, "version", actor)
    return await _save(
        session,
        assignment,
        content,
        actor=actor,
        change={"section": key, "origin": section["origin"], "settled": True},
    )


async def set_outline(
    session: AsyncSession,
    assignment: Assignment,
    keys: list[str],
    *,
    actor: Person | None,
    new_sections: list[dict[str, Any]] | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """The sections in a new order. A key left out is removed; a new section
    comes in with its heading."""
    content, _ = await read_draft(session, assignment)
    _check_version(expected_version, content["outline_version"], "De volgorde", content)
    by_key = {section["key"]: section for section in content["sections"]}
    before = [section["key"] for section in content["sections"]]
    for raw in new_sections or []:
        key = _line(raw.get("key"), "De sleutel", 40).lower()
        if not key or not key.replace("-", "").replace("_", "").isalnum():
            raise DomainValidationError(
                "De sleutel van een onderdeel bestaat uit letters, cijfers en "
                "streepjes."
            )
        if key in by_key:
            raise DomainValidationError(f"Het onderdeel '{key}' bestaat al.")
        heading = _line(raw.get("heading"), "De kop", 200)
        if not heading:
            raise DomainValidationError("Een onderdeel heeft een kop nodig.")
        by_key[key] = {
            "key": key,
            "heading": heading,
            "body": "",
            "hint": "",
            "included": True,
            "with_costs": False,
            "numbered": True,
            "draftable": True,
            "required": False,
            "custom": True,
            "version": 0,
            "origin": "empty",
            "generated": None,
            "settled": True,
        }
    if len(keys) != len(set(keys)):
        raise DomainValidationError("Een onderdeel staat twee keer in de volgorde.")
    missing = [key for key in keys if key not in by_key]
    if missing:
        raise DomainValidationError(f"Onbekend onderdeel: {', '.join(missing)}.")
    if len(keys) > MAX_SECTIONS:
        raise DomainValidationError(f"Hooguit {MAX_SECTIONS} onderdelen.")
    for key in before:
        if key not in keys and not section_rules(by_key[key])["removable"]:
            raise DomainValidationError(
                f"Het onderdeel '{by_key[key]['heading']}' hoort bij de opbouw van "
                "de organisatie. Laat het weg uit deze offerte in plaats van het "
                "te verwijderen."
            )

    def fixed(order: list[str]) -> list[str]:
        return [key for key in order if not section_rules(by_key[key])["movable"]]

    if fixed(before) != fixed([key for key in keys if key in before]):
        raise DomainValidationError(
            "De onderdelen die in elke offerte staan, houden hun onderlinge volgorde."
        )
    content["sections"] = [by_key[key] for key in keys]
    _stamp(content, "outline_version", actor)
    return await _save(
        session, assignment, content, actor=actor, change={"outline": list(keys)}
    )


async def restart(
    session: AsyncSession, assignment: Assignment, *, actor: Person | None
) -> dict[str, Any]:
    """Throw the draft away and start again from the organisation's texts."""
    content = await start_content(session, assignment)
    return await _save(
        session, assignment, content, actor=actor, change={"restarted": True}
    )


# --- drafting with the language model -----------------------------------------------


async def _person_names(session: AsyncSession) -> list[str]:
    return list((await session.execute(select(Person.name))).scalars())


async def section_input(
    session: AsyncSession,
    assignment: Assignment,
    content: dict[str, Any],
    key: str,
    *,
    context: tuple[str, ...] = (),
    passage: str | None = None,
    instruction: str | None = None,
) -> SectionInput:
    """What a draft of this section is based on. Rates and amounts are not
    read here at all: only the role, the size and the period of a line."""
    section = _find(content, key)
    client = await client_of(session, assignment)
    sender = await quote_sender.current_sender(session)
    lines = await AssignmentRepository(session).budget_lines([assignment.id])
    roles = tuple(
        RoleFact(
            role=line.role or line.description,
            fte=line.fte,
            period_start=line.start_date,
            period_end=line.end_date,
        )
        for line in lines
        if line.kind == "personnel"
    )
    settled = tuple(
        (other["heading"], other["body"])
        for other in content["sections"]
        if other["key"] != key
        and other["included"]
        and other["settled"]
        and other["body"]
        and other["origin"] in ("written", "generated")
    )[:MAX_OTHER_SECTIONS]
    return SectionInput(
        heading=section["heading"],
        hint=section["hint"],
        assignment_name=assignment.name,
        client_name=client.name if client is not None else None,
        sender_name=sender["unit"] or sender["organisation"] or None,
        period_start=assignment.start_date,
        period_end=assignment.end_date,
        roles=roles,
        context=tuple(context),
        outline=tuple(
            other["heading"] for other in content["sections"] if other["included"]
        ),
        settled=settled,
        passage=passage,
        instruction=instruction,
    )


async def _complete(
    session: AsyncSession, built: SectionInput, client: ChatClient | None
) -> tuple[str, str]:
    try:
        ensure_no_person_names(built, await _person_names(session))
    except SectionInputError as exc:
        raise DomainValidationError(str(exc)) from exc
    chat = client or get_chat_client()
    system, user = build_prompt(built)
    text = await chat.complete(system=system, user=user, max_tokens=900)
    return _prose(text, "Het concept van het taalmodel"), chat.model_id


async def draft_section(
    session: AsyncSession,
    assignment: Assignment,
    key: str,
    *,
    actor: Person | None,
    context: tuple[str, ...] = (),
    context_state: str = "none",
    client: ChatClient | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ask the language model for a draft of one section and put it in the
    draft, unsettled. A section with text a person wrote is not overwritten."""
    content, _ = await read_draft(session, assignment)
    section = _find(content, key)
    if not section["draftable"] or section["with_costs"]:
        raise DomainValidationError(
            f"Voor het onderdeel '{section['heading']}' stelt het taalmodel geen "
            "concept op."
        )
    if section["body"] and section["origin"] == "written":
        raise DomainValidationError(
            "Dit onderdeel heeft al een tekst. Maak het eerst leeg als je een "
            "concept wilt laten opstellen."
        )
    built = await section_input(session, assignment, content, key, context=context)
    text, model_id = await _complete(session, built, client)
    section["body"] = text
    section["origin"] = "generated"
    section["settled"] = False
    section["generated"] = {
        "model": model_id,
        "prompt_version": PROMPT_VERSION,
        "at": (now or datetime.now(UTC)).isoformat(),
        # "used", "none" or "unreachable": whether the draft had the policy
        # context of the assignment, so the screen can say when it had not.
        "context": context_state,
    }
    _stamp(section, "version", actor)
    return await _save(
        session,
        assignment,
        content,
        actor=actor,
        change={"section": key, "origin": "generated", "model": model_id},
    )


async def rewrite_passage(
    session: AsyncSession,
    assignment: Assignment,
    key: str,
    passage: str,
    *,
    instruction: str | None = None,
    client: ChatClient | None = None,
) -> str:
    """A rewritten passage as a proposal. Nothing is stored: the writer puts
    it in the text and saves the section."""
    content, _ = await read_draft(session, assignment)
    passage = _prose(passage, "De passage")
    if not passage:
        raise DomainValidationError("Selecteer de tekst die je wilt herschrijven.")
    built = await section_input(
        session,
        assignment,
        content,
        key,
        passage=passage,
        instruction=_line(instruction, "De aanwijzing", 300) or None,
    )
    text, _model = await _complete(session, built, client)
    return text


# --- freezing ----------------------------------------------------------------------


def _signature(fields: dict[str, Any]) -> dict[str, str]:
    return {name: str(fields.get(name) or "") for name in SIGNATORY_FIELDS}


async def frozen_letter(
    session: AsyncSession, assignment: Assignment, *, strict: bool
) -> FrozenLetter | None:
    """The text of the draft as it goes into a quote, or None without a draft.

    ``strict`` is the making of a quote: an included section without text, a
    drafted section nobody settled, or the name of a person of this instance
    in the text refuses it, each with the place.
    """
    row = await find_draft(session, assignment.id)
    if row is None:
        return None
    sender = await quote_sender.current_sender(session)
    # A copy: the standard texts are brought up to date for this quote; the
    # stored draft keeps what was saved.
    content = _normalise(copy.deepcopy(row.content))
    missing = await _bring_up_to_date(session, assignment, content, sender)
    included = [section for section in content["sections"] if section["included"]]

    if strict:
        for section in included:
            if not section["settled"]:
                raise DomainValidationError(
                    f"Het onderdeel '{section['heading']}' is een concept van het "
                    "taalmodel dat nog niemand heeft vastgesteld. Lees het, pas "
                    "het aan en sla het op."
                )
            if not section["body"] and not section["with_costs"]:
                raise DomainValidationError(
                    f"Het onderdeel '{section['heading']}' heeft nog geen tekst. "
                    "Schrijf het of laat het onderdeel weg."
                )
        # What the writer can solve comes first; then what only a beheerder can.
        problem = sender_problem(missing)
        if problem is not None:
            raise DomainValidationError(
                f"{problem} De brief zou die plek leeg laten. Een beheerder vult "
                "dit in."
            )
        # The contact person and the signatory stand on the quote on purpose.
        allowed = {
            " ".join(name.split()).casefold()
            for name in (sender["contact"]["name"], sender["signatory"]["name"])
            if name
        }
        names = [
            name
            for name in await _person_names(session)
            if " ".join(name.split()).casefold() not in allowed
        ]
        places = [
            ("het onderwerp", content["subject"]),
            ("de opening", content["opening"]),
        ]
        places += [
            (
                f"het onderdeel '{section['heading']}'",
                f"{section['heading']}\n{section['body']}",
            )
            for section in included
        ]
        for place, text in places:
            if quote_prose.find_names(text, names):
                raise DomainValidationError(
                    f"In {place} staat de naam van een medewerker. Een offerte noemt "
                    "rollen en niveaus, geen personen. Haal de naam uit de tekst."
                )

    closing = content["closing"]
    provenance = [
        {
            "key": section["key"],
            "origin": section["origin"],
            **({"generated": section["generated"]} if section["generated"] else {}),
        }
        for section in included
    ]
    if await instance_settings.get(session, quote_sender.AI_DISCLOSURE.key) and any(
        entry["origin"] == "generated" for entry in provenance
    ):
        closing = (
            closing + "\n\n" if closing else ""
        ) + quote_sender.AI_DISCLOSURE_SENTENCE

    letter: dict[str, Any] = {
        "subject": content["subject"],
        "addressee": list(content["addressee"]),
        "salutation": content["salutation"],
        "opening": content["opening"],
        "closing": closing,
        "sections": [
            {
                "key": section["key"],
                "heading": section["heading"],
                "body": section["body"],
                "with_costs": bool(section["with_costs"]),
                "numbered": bool(section["numbered"]),
            }
            for section in included
        ],
        "sender_details": {
            "organisation": sender["organisation"],
            "part_of": list(sender["part_of"]),
            "unit": sender["unit"],
            "visiting_address": list(sender["visiting_address"]),
            "postal_address": list(sender["postal_address"]),
            "website": sender["website"],
        },
        "signatures": [
            _signature(
                {
                    "on_behalf_of": sender["signatory"]["on_behalf_of"],
                    "name": sender["signatory"]["name"],
                    "function": sender["signatory"]["title"],
                    "organisation": sender["signatory"]["organisation"]
                    or sender["organisation"],
                }
            ),
            _signature(content["client_signatory"]),
        ],
        "billing_annex": bool(content["billing_annex"]),
    }
    return FrozenLetter(letter=letter, provenance=provenance)
