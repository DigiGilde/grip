"""The text of a quote in preparation, and the sender and standard texts.

The draft belongs to an assignment. Reading it takes the financial class of
the assignment, like the quote it becomes; changing it takes the right to
make a quote. The sender and the standard texts are settings of the
instance, for the beheerder.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.access import Action, DataClass, Resource
from grip.access.deps import AccessDecider, CurrentSubject, decide, require
from grip.api.routes import node_picker
from grip.core import clock
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.federation.corpus import CorpusClient
from grip.models.assignment import Assignment
from grip.services import (
    context_fetch,
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
    # The ``head_version`` the writer started from; a mismatch answers 409.
    head_version: int | None = None


class SectionIn(BaseModel):
    body: str | None = None
    heading: str | None = None
    included: bool | None = None
    # Give up the own text and follow the organisation's standard text again.
    follow_standard: bool = False
    # The ``version`` of the section the writer started from.
    version: int | None = None


class NewSectionIn(BaseModel):
    key: str
    heading: str


class OutlineIn(BaseModel):
    keys: list[str]
    new_sections: list[NewSectionIn] = Field(default_factory=list)
    outline_version: int | None = None


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
    sections = [
        {**section, **quote_drafts.section_rules(section)}
        for section in content["sections"]
    ]
    return {
        "saved": saved,
        "may_edit": may_edit,
        "drafting_available": is_llm_configured(),
        "problems": _problems(content),
        **{**content, "sections": sections},
    }


async def _answer(
    db: AsyncSession,
    decider: Any,
    subject: Any,
    assignment: Assignment,
    *,
    may_edit: bool,
) -> dict[str, Any]:
    """The draft as it reads now, with what the sender still lacks for it.

    The standard texts follow the budget, the billing terms and the sender,
    so the answer is read again after a change rather than taken from it.
    """
    content, saved = await quote_drafts.read_draft(db, assignment)
    missing = await quote_drafts.sender_gaps(db, assignment)
    return {
        **_draft_out(content, saved=saved, may_edit=may_edit),
        # What a beheerder must fill in under Beheer, Afzender before a quote
        # can be made; null when nothing is missing.
        "sender_problem": quote_drafts.sender_problem(missing),
        "may_set_sender": bool(
            await decide(decider, subject, Action.MANAGE_USERS, Resource.instance())
        ),
    }


def _conflict(
    exc: quote_drafts.DraftConflictError, content: dict[str, Any]
) -> JSONResponse:
    """409 with what is there now, so the screen can show it next to the
    writer's own text."""
    return JSONResponse(
        status_code=409,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Conflict",
            "status": 409,
            "detail": str(exc),
            "changed_by": exc.changed_by,
            "changed_at": exc.changed_at,
            "current": _draft_out(content, saved=True, may_edit=True),
        },
    )


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
    may_edit = bool(await decide(decider, subject, Action.ISSUE_QUOTE, resource))
    return await _answer(db, decider, subject, assignment, may_edit=may_edit)


@router.patch("/assignments/{assignment_id}/quote-draft", response_model=None)
async def update_quote_draft(
    assignment_id: UUID,
    body: LetterIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Change subject, addressee, salutation, opening, closing or the
    signatory of the client."""
    assignment = await _editable(db, decider, subject, assignment_id)
    fields = body.model_dump(exclude_unset=True)
    fields.pop("head_version", None)
    try:
        await quote_drafts.update_letter(
            db, assignment, fields, actor=person, expected_version=body.head_version
        )
    except quote_drafts.DraftConflictError as exc:
        current, _ = await quote_drafts.read_draft(db, assignment)
        return _conflict(exc, current)
    return await _answer(db, decider, subject, assignment, may_edit=True)


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
) -> Any:
    """Save a section. Saving is what settles a text the model drafted."""
    assignment = await _editable(db, decider, subject, assignment_id)
    try:
        await quote_drafts.save_section(
            db,
            assignment,
            key,
            actor=person,
            body=body.body,
            heading=body.heading,
            included=body.included,
            follow_standard=body.follow_standard,
            expected_version=body.version,
        )
    except quote_drafts.DraftConflictError as exc:
        current, _ = await quote_drafts.read_draft(db, assignment)
        return _conflict(exc, current)
    return await _answer(db, decider, subject, assignment, may_edit=True)


@router.put("/assignments/{assignment_id}/quote-draft/outline", response_model=None)
async def set_quote_outline(
    assignment_id: UUID,
    body: OutlineIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reorder the sections, drop one, or add a section of your own."""
    assignment = await _editable(db, decider, subject, assignment_id)
    try:
        await quote_drafts.set_outline(
            db,
            assignment,
            body.keys,
            actor=person,
            new_sections=[item.model_dump() for item in body.new_sections],
            expected_version=body.outline_version,
        )
    except quote_drafts.DraftConflictError as exc:
        current, _ = await quote_drafts.read_draft(db, assignment)
        return _conflict(exc, current)
    return await _answer(db, decider, subject, assignment, may_edit=True)


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
    await quote_drafts.restart(db, assignment, actor=person)
    return await _answer(db, decider, subject, assignment, may_edit=True)


async def assignment_context(
    db: AsyncSession,
    corpus: CorpusClient,
    settings: Settings,
    assignment: Assignment | None,
) -> context_fetch.FetchedContext:
    """Why this assignment exists, for a prompt: what the context sheet
    shows a person, fetched with the same client."""
    if assignment is None or not assignment.context_refs:
        return context_fetch.FetchedContext()
    corpora = await node_picker.known_corpora(db, settings)
    return await context_fetch.for_assignment(
        db,
        assignment,
        corpus=corpus,
        reachable=bool(corpora) and corpora.outway_configured,
        corpus_name=corpora.name,
    )


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
    context = await assignment_context(db, corpus, settings, assignment)
    try:
        await quote_drafts.draft_section(
            db,
            assignment,
            key,
            actor=person,
            context=context.lines,
            context_state=context.state,
        )
    except (LlmNotConfiguredError, LlmResponseError) as exc:
        raise _llm_problem(exc) from exc
    return await _answer(db, decider, subject, assignment, may_edit=True)


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
        issued_at=datetime.combine(clock.today(), datetime.min.time(), tzinfo=UTC),
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
        # The settings are saved together: one version for the set.
        "settings_version": await instance_settings.version(db),
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
