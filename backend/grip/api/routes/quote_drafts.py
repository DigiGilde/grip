"""The text of a quote in preparation, and the sender and standard texts.

The draft belongs to an assignment. Reading it takes the financial class of
the assignment, like the quote it becomes; changing it takes the right to
make a quote. The sender and the standard texts are settings of the
instance, for the beheerder.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import Action, DataClass, Resource
from grip.access.deps import AccessDecider, CurrentSubject, decide, require
from grip.api.routes import node_picker
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.federation.corpus import CorpusClient
from grip.models.assignment import Assignment
from grip.services import (
    instance_settings,
    quote_drafts,
    quote_sender,
    quote_views,
    quotes,
)
from grip.services.assignments import get_assignment
from grip.services.errors import DomainValidationError
from grip.services.llm import (
    LlmNotConfiguredError,
    LlmResponseError,
    is_llm_configured,
)
from grip.services.quote_document import (
    QuoteDocumentContext,
    letterhead_from_settings,
    render_quote_pdf,
)

router = APIRouter(tags=["quotes"])

# The fingerprint a preview shows: a quote that is not made has none.
_NO_HASH = "0" * 64


class LetterIn(BaseModel):
    """Only the fields that are sent change."""

    subject: str | None = None
    addressee: list[str] | None = None
    salutation: str | None = None
    opening: str | None = None
    closing: str | None = None
    client_signatory: dict[str, str] | None = None
    billing_annex: bool | None = None


class SectionIn(BaseModel):
    body: str | None = None
    heading: str | None = None
    included: bool | None = None


class NewSectionIn(BaseModel):
    key: str
    heading: str


class OutlineIn(BaseModel):
    keys: list[str]
    new_sections: list[NewSectionIn] = Field(default_factory=list)


class RewriteIn(BaseModel):
    passage: str
    instruction: str | None = None


class SenderSettingsIn(BaseModel):
    """Only the parts that are sent change."""

    sender: dict[str, Any] | None = None
    text_blocks: list[dict[str, Any]] | None = None
    letter: dict[str, Any] | None = None
    ai_disclosure: bool | None = None


async def _readable(
    db: AsyncSession, decider: Any, subject: Any, assignment_id: UUID
) -> tuple[Assignment, Resource]:
    resource = Resource.assignment(assignment_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    await require(
        decider, subject, Action.READ, resource, DataClass.ASSIGNMENT_FINANCIAL
    )
    return await get_assignment(db, assignment_id), resource


async def _editable(
    db: AsyncSession, decider: Any, subject: Any, assignment_id: UUID
) -> Assignment:
    resource = Resource.assignment(assignment_id)
    await require(
        decider,
        subject,
        Action.READ,
        resource,
        DataClass.ASSIGNMENT_BASIC,
        hide_existence=True,
    )
    await require(decider, subject, Action.ISSUE_QUOTE, resource)
    return await get_assignment(db, assignment_id)


def _problems(content: dict[str, Any]) -> list[dict[str, str]]:
    """What still stands between this draft and a quote, per section."""
    found: list[dict[str, str]] = []
    for section in content["sections"]:
        if not section["included"]:
            continue
        if not section["settled"]:
            found.append(
                {
                    "key": section["key"],
                    "problem": "Een concept van het taalmodel dat nog niet is "
                    "vastgesteld.",
                }
            )
        elif not section["body"] and not section["with_costs"]:
            found.append({"key": section["key"], "problem": "Nog geen tekst."})
    return found


def _draft_out(
    content: dict[str, Any], *, saved: bool, may_edit: bool
) -> dict[str, Any]:
    return {
        "saved": saved,
        "may_edit": may_edit,
        "drafting_available": is_llm_configured(),
        "problems": _problems(content),
        **content,
    }


@router.get("/assignments/{assignment_id}/quote-draft", response_model=None)
async def read_quote_draft(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The text of the next quote: the saved draft, or the organisation's
    starting texts when nothing was saved yet."""
    assignment, resource = await _readable(db, decider, subject, assignment_id)
    content, saved = await quote_drafts.read_draft(db, assignment)
    may_edit = bool(await decide(decider, subject, Action.ISSUE_QUOTE, resource))
    return _draft_out(content, saved=saved, may_edit=may_edit)


@router.patch("/assignments/{assignment_id}/quote-draft", response_model=None)
async def update_quote_draft(
    assignment_id: UUID,
    body: LetterIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Change subject, addressee, salutation, opening, closing or the
    signatory of the client."""
    assignment = await _editable(db, decider, subject, assignment_id)
    content = await quote_drafts.update_letter(
        db, assignment, body.model_dump(exclude_unset=True), actor=person
    )
    return _draft_out(content, saved=True, may_edit=True)


@router.put(
    "/assignments/{assignment_id}/quote-draft/sections/{key}", response_model=None
)
async def save_quote_section(
    assignment_id: UUID,
    key: str,
    body: SectionIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Save a section. Saving is what settles a text the model drafted."""
    assignment = await _editable(db, decider, subject, assignment_id)
    content = await quote_drafts.save_section(
        db,
        assignment,
        key,
        actor=person,
        body=body.body,
        heading=body.heading,
        included=body.included,
    )
    return _draft_out(content, saved=True, may_edit=True)


@router.put("/assignments/{assignment_id}/quote-draft/outline", response_model=None)
async def set_quote_outline(
    assignment_id: UUID,
    body: OutlineIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reorder the sections, drop one, or add a section of your own."""
    assignment = await _editable(db, decider, subject, assignment_id)
    content = await quote_drafts.set_outline(
        db,
        assignment,
        body.keys,
        actor=person,
        new_sections=[item.model_dump() for item in body.new_sections],
    )
    return _draft_out(content, saved=True, may_edit=True)


@router.post("/assignments/{assignment_id}/quote-draft/restart", response_model=None)
async def restart_quote_draft(
    assignment_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start again from the texts of the organisation."""
    assignment = await _editable(db, decider, subject, assignment_id)
    content = await quote_drafts.restart(db, assignment, actor=person)
    return _draft_out(content, saved=True, may_edit=True)


async def _context_lines(
    db: AsyncSession,
    corpus: CorpusClient,
    settings: Settings,
    assignment: Assignment,
) -> tuple[str, ...]:
    """Titles of the nodes the assignment refers to and of the political
    input they follow from. Empty when no corpus can be asked."""
    linked = list(assignment.context_refs or [])
    if not linked:
        return ()
    corpora = await node_picker.known_corpora(db, settings)
    if not corpora or not corpora.outway_configured:
        return ()
    lines: list[str] = []
    for uri in linked[:4]:
        item, summary = await node_picker.resolve(db, corpus, uri, None, corpora)
        if item.node is None:
            continue
        line = f"{item.node.type}: {item.node.title}"
        origins = ", ".join(origin.title for origin in summary.origins[:2])
        if origins:
            line += f" (volgt uit: {origins})"
        lines.append(line)
    return tuple(lines)


def _llm_problem(exc: Exception) -> DomainValidationError:
    if isinstance(exc, LlmNotConfiguredError):
        return DomainValidationError(str(exc))
    return DomainValidationError(
        "Het taalmodel gaf geen bruikbaar antwoord. Probeer het opnieuw of schrijf "
        "de tekst zelf."
    )


@router.post(
    "/assignments/{assignment_id}/quote-draft/sections/{key}/draft",
    response_model=None,
)
async def draft_quote_section(
    assignment_id: UUID,
    key: str,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    corpus: CorpusClient = Depends(node_picker.get_corpus_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Let the language model draft one section. The draft is a proposal: it
    counts for nothing until a person saves the section."""
    assignment = await _editable(db, decider, subject, assignment_id)
    context = await _context_lines(db, corpus, settings, assignment)
    try:
        content = await quote_drafts.draft_section(
            db, assignment, key, actor=person, context=context
        )
    except (LlmNotConfiguredError, LlmResponseError) as exc:
        raise _llm_problem(exc) from exc
    return _draft_out(content, saved=True, may_edit=True)


@router.post(
    "/assignments/{assignment_id}/quote-draft/sections/{key}/rewrite",
    response_model=None,
)
async def rewrite_quote_passage(
    assignment_id: UUID,
    key: str,
    body: RewriteIn,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A rewritten passage as a proposal. Nothing is stored."""
    assignment = await _editable(db, decider, subject, assignment_id)
    try:
        text = await quote_drafts.rewrite_passage(
            db, assignment, key, body.passage, instruction=body.instruction
        )
    except (LlmNotConfiguredError, LlmResponseError) as exc:
        raise _llm_problem(exc) from exc
    return {"text": text}


@router.get("/assignments/{assignment_id}/quote-draft/preview")
async def preview_quote_document(
    assignment_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The quote as it would be made now, as the PDF itself.

    The real lay-out, so page breaks and the letterhead are what the client
    will get. It has no reference and no fingerprint: it is not a quote.
    """
    assignment, _ = await _readable(db, decider, subject, assignment_id)
    frozen = await quote_drafts.frozen_letter(db, assignment, strict=False)
    if frozen is not None:
        letter = frozen.letter
    else:
        # Nothing saved yet: show the organisation's starting texts.
        letter = await _unsaved_letter(
            db, await quote_drafts.start_content(db, assignment)
        )
    try:
        snapshot = await quotes.build_snapshot(db, assignment, letter=letter)
    except calc.CalcError as exc:
        raise DomainValidationError(quote_views.describe_calc_error(exc)) from exc
    client = await quote_drafts.client_of(db, assignment)
    context = QuoteDocumentContext(
        quote_uri="",
        snapshot_hash=_NO_HASH,
        issued_at=datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC),
        contractor_name=await quotes.sender_name(db, assignment),
        client_name=client.name if client is not None else None,
        client_contact=assignment.client_contact,
        reference="Concept",
        letterhead=letterhead_from_settings(),
    )
    pdf = await asyncio.to_thread(render_quote_pdf, snapshot, context)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="offerte-concept.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


async def _unsaved_letter(db: AsyncSession, content: dict[str, Any]) -> dict[str, Any]:
    sender = await quote_sender.current_sender(db)
    included = [section for section in content["sections"] if section["included"]]
    return {
        "subject": content["subject"],
        "addressee": list(content["addressee"]),
        "salutation": content["salutation"],
        "opening": content["opening"],
        "closing": content["closing"],
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
        "signatures": [],
        "billing_annex": bool(content["billing_annex"]),
    }


# --- sender and standard texts, for the beheerder -----------------------------------


async def _sender_out(db: AsyncSession) -> dict[str, Any]:
    return {
        "sender": await quote_sender.current_sender(db),
        "text_blocks": await quote_sender.current_blocks(db),
        "letter": await quote_sender.current_letter(db),
        "ai_disclosure": bool(
            await instance_settings.get(db, quote_sender.AI_DISCLOSURE.key)
        ),
        "drafting_available": is_llm_configured(),
        "profiles": quote_sender.profile_names(),
        "placeholders": sorted(
            quote_sender.placeholders(quote_sender.EMPTY_SENDER, year=2000)
        ),
    }


@router.get("/quote-sender", response_model=None)
async def read_quote_sender(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Who sends the quotes of this instance and with which standard texts."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.instance())
    return await _sender_out(db)


@router.patch("/quote-sender", response_model=None)
async def update_quote_sender(
    body: SenderSettingsIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Change the sender, the text blocks or the letter texts. A quote that
    exists does not change: it keeps what it was made with."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.instance())
    values: dict[str, Any] = {}
    if body.sender is not None:
        values[quote_sender.SENDER.key] = body.sender
    if body.text_blocks is not None:
        values[quote_sender.TEXT_BLOCKS.key] = body.text_blocks
    if body.letter is not None:
        values[quote_sender.LETTER.key] = body.letter
    if body.ai_disclosure is not None:
        values[quote_sender.AI_DISCLOSURE.key] = body.ai_disclosure
    await instance_settings.set_values(db, values, actor=person)
    return await _sender_out(db)


@router.post("/quote-sender/profiles/{name}", response_model=None)
async def apply_quote_sender_profile(
    name: str,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Take the starting values of a shipped profile. The contact person
    and the signatory stay as they are: a profile names no people."""
    await require(decider, subject, Action.MANAGE_USERS, Resource.instance())
    await quote_sender.apply_profile(db, name, actor=person)
    return await _sender_out(db)
