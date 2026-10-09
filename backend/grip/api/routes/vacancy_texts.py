"""The texts of a vacancy as work, the standard texts, and where a vacancy
is published.

- ``/vacancies/{id}/text-work``: where each text stands, its versions,
  rounds of review and remarks, and what the viewer can do next.
- ``/vacancy-texts``: the library of standard texts per role.
- ``/vacancies/{id}/publications``: the public address of a published
  vacancy.

Every field carries a data class (see ``grip.access.vacancies``): the text
work is the vacancy without names, names of people are the full view.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from openai import OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, build_response, in_class, nested
from grip.access.deps import AccessDecider, CurrentSubject, decide, require
from grip.access.vacancies import (
    form_template_resource,
    language_model_resource,
    vacancy_resource,
)
from grip.api.routes import node_picker
from grip.api.routes.vacancies import _load_for_edit, _permitted, _resource
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.federation.corpus import CorpusClient
from grip.models.assignment import Assignment
from grip.models.vacancy import TextKind, TextSource, Vacancy, VacancyStatus
from grip.repositories.vacancy import VacancyRepository
from grip.services import context_fetch, instance_settings, internal_judges
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.llm import LlmNotConfiguredError, LlmResponseError, get_chat_client
from grip.services.llm.client import (
    PROVIDER_CLAUDE_CLI,
    PROVIDER_NONE,
    active_provider,
    is_llm_configured,
    provider_label,
)
from grip.services.vacancies import library, text_flow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vacancies"])

NO_NAMES = in_class(DataClass.STAFFING_COUNTS)
FULL = in_class(DataClass.STAFFING)
ADMIN = in_class(DataClass.MASTER_DATA)

STATE_WORDS = {
    text_flow.STATE_NONE: "Nog niet begonnen",
    text_flow.STATE_DRAFT: "In de maak",
    text_flow.STATE_IN_REVIEW: "Ter beoordeling",
    text_flow.STATE_RETURNED: "Terug met opmerkingen",
    text_flow.STATE_AGREED: "Akkoord, nog vaststellen",
    text_flow.STATE_SETTLED: "Vastgesteld",
}


# --- schemas ------------------------------------------------------------------


class VersionOut(BaseModel):
    id: Annotated[UUID, NO_NAMES]
    number: Annotated[int, NO_NAMES]
    # The text to write on from: a fact of the vacancy stands in it by key.
    body: Annotated[str, NO_NAMES]
    # The text as it reads: a settled version as it was frozen, a draft with
    # the facts as they stand now.
    text: Annotated[str, NO_NAMES] = ""
    # human, model or template.
    source: Annotated[str, NO_NAMES]
    # In words: "Uit de standaardtekst Software engineer, versie 2026-10-08".
    origin: Annotated[str | None, NO_NAMES] = None
    created_at: Annotated[datetime, NO_NAMES]
    settled_at: Annotated[datetime | None, NO_NAMES] = None
    created_by_name: Annotated[str | None, FULL] = None
    settled_by_name: Annotated[str | None, FULL] = None
    by_viewer: Annotated[bool, NO_NAMES] = False


class VerdictOut(BaseModel):
    reviewer_id: Annotated[UUID, FULL]
    reviewer_name: Annotated[str | None, FULL] = None
    is_viewer: Annotated[bool, NO_NAMES]
    # None while waited for; agreed or remarks.
    verdict: Annotated[str | None, NO_NAMES] = None
    note: Annotated[str | None, NO_NAMES] = None
    decided_at: Annotated[datetime | None, NO_NAMES] = None


class RoundOut(BaseModel):
    id: Annotated[UUID, NO_NAMES]
    round: Annotated[int, NO_NAMES]
    version_number: Annotated[int, NO_NAMES]
    offered_at: Annotated[datetime, NO_NAMES]
    offered_by_name: Annotated[str | None, FULL] = None
    note: Annotated[str | None, NO_NAMES] = None
    withdrawn: Annotated[bool, NO_NAMES] = False
    # open, agreed, returned or withdrawn.
    outcome: Annotated[str, NO_NAMES]
    verdicts: Annotated[list[VerdictOut], nested()] = Field(default_factory=list)


class RemarkOut(BaseModel):
    id: Annotated[UUID, NO_NAMES]
    section: Annotated[str, NO_NAMES]
    body: Annotated[str, NO_NAMES]
    version_number: Annotated[int | None, NO_NAMES] = None
    created_at: Annotated[datetime, NO_NAMES]
    author_name: Annotated[str | None, FULL] = None
    by_viewer: Annotated[bool, NO_NAMES] = False
    resolved_at: Annotated[datetime | None, NO_NAMES] = None
    answers: Annotated[list[RemarkOut], nested()] = Field(default_factory=list)


class ChangeOut(BaseModel):
    heading: Annotated[str, NO_NAMES]
    change: Annotated[str, NO_NAMES]
    summary: Annotated[str, NO_NAMES]
    before: Annotated[str, NO_NAMES] = ""
    after: Annotated[str, NO_NAMES] = ""


class ActionOut(BaseModel):
    """The one next step for this viewer on this text."""

    # start, write, offer, withdraw, judge, process, settle, revise or none.
    key: Annotated[str, NO_NAMES]
    text: Annotated[str, NO_NAMES]


class StandardTextOut(BaseModel):
    """The standard text this vacancy would start from."""

    role: Annotated[str, NO_NAMES]
    # role, name or function_group (the nearest text, of another role).
    match: Annotated[str, NO_NAMES]
    unread: Annotated[bool, NO_NAMES]
    missing: Annotated[list[str], NO_NAMES] = Field(default_factory=list)


class FactOut(BaseModel):
    """A fact of the vacancy a text names by key."""

    key: Annotated[str, NO_NAMES]
    label: Annotated[str, NO_NAMES]
    # None while grip does not know it.
    value: Annotated[str | None, NO_NAMES] = None
    # "uit de aanvraag: Schaal".
    source: Annotated[str, NO_NAMES]
    # request, settings or sender: where it is filled.
    where: Annotated[str, NO_NAMES]
    # "Vul de schaal in op de aanvraag".
    instruction: Annotated[str, NO_NAMES]


class ChangedFactOut(BaseModel):
    """A fact that reads differently now than in the settled text."""

    key: Annotated[str, NO_NAMES]
    label: Annotated[str, NO_NAMES]
    settled: Annotated[str, NO_NAMES]
    current: Annotated[str | None, NO_NAMES] = None


class TextWorkOut(BaseModel):
    kind: Annotated[TextKind, NO_NAMES]
    needed: Annotated[bool, NO_NAMES]
    state: Annotated[str, NO_NAMES]
    state_text: Annotated[str, NO_NAMES]
    # Who has it now, in words.
    with_whom: Annotated[str | None, NO_NAMES] = None
    revising: Annotated[bool, NO_NAMES] = False
    open_passages: Annotated[list[str], NO_NAMES] = Field(default_factory=list)
    facts: Annotated[list[FactOut], nested()] = Field(default_factory=list)
    changed_facts: Annotated[list[ChangedFactOut], nested()] = Field(
        default_factory=list
    )
    action: Annotated[ActionOut, nested()]
    may_write: Annotated[bool, NO_NAMES]
    may_remark: Annotated[bool, NO_NAMES]
    may_settle: Annotated[bool, NO_NAMES]
    viewer_review_id: Annotated[UUID | None, NO_NAMES] = None
    standard_text: Annotated[StandardTextOut | None, nested()] = None
    default_reviewer_ids: Annotated[list[UUID], FULL] = Field(default_factory=list)
    versions: Annotated[list[VersionOut], nested()] = Field(default_factory=list)
    rounds: Annotated[list[RoundOut], nested()] = Field(default_factory=list)
    remarks: Annotated[list[RemarkOut], nested()] = Field(default_factory=list)
    # What changed in the latest version against the one before.
    latest_changes: Annotated[list[ChangeOut], nested()] = Field(default_factory=list)


class PublicationOut(BaseModel):
    id: Annotated[UUID, NO_NAMES]
    place: Annotated[str, NO_NAMES]
    place_text: Annotated[str, NO_NAMES]
    url: Annotated[str, NO_NAMES]
    published_on: Annotated[date, NO_NAMES]


class ReviewerOptionOut(BaseModel):
    id: Annotated[UUID, FULL]
    name: Annotated[str, FULL]


class VacancyTextWorkOut(BaseModel):
    vacancy_id: Annotated[UUID, NO_NAMES]
    texts: Annotated[list[TextWorkOut], nested()]
    publications: Annotated[list[PublicationOut], nested()] = Field(
        default_factory=list
    )
    may_record_publication: Annotated[bool, NO_NAMES] = False
    # The vacancy is open and no public address is recorded yet.
    publication_missing: Annotated[bool, NO_NAMES] = False
    drafting_available: Annotated[bool, NO_NAMES] = False
    # In development: the local model. None for the government's own.
    drafting_note: Annotated[str | None, NO_NAMES] = None
    reviewer_options: Annotated[list[ReviewerOptionOut], nested()] = Field(
        default_factory=list
    )
    # The vacancy is not opened to applicants, so it has no vacancy text.
    vacancy_text_skipped: Annotated[bool, NO_NAMES] = False
    may_want_text: Annotated[bool, NO_NAMES] = False


class SaveIn(BaseModel):
    kind: TextKind
    body: str = Field(min_length=1, max_length=40000)
    based_on_id: UUID | None = None


class OfferIn(BaseModel):
    kind: TextKind
    reviewer_ids: list[UUID] = Field(min_length=1, max_length=10)
    note: str | None = Field(default=None, max_length=2000)


class VerdictIn(BaseModel):
    verdict: str
    note: str | None = Field(default=None, max_length=4000)


class RemarkIn(BaseModel):
    kind: TextKind
    body: str = Field(min_length=1, max_length=4000)
    section: str = Field(default="", max_length=200)
    parent_id: UUID | None = None


class ResolveIn(BaseModel):
    resolved: bool = True


class TailoredIn(BaseModel):
    instruction: str | None = Field(default=None, max_length=600)


class PassageIn(BaseModel):
    # The text as the writer has it now, saved or not.
    body: str = Field(min_length=1, max_length=40000)
    # The open place as it stands in it: "[vul aan: ...]".
    place: str = Field(min_length=1, max_length=1000)


class PublicationIn(BaseModel):
    place: str
    url: str = Field(max_length=1000)
    published_on: date | None = None


# --- the text work of a vacancy ---------------------------------------------


def _origin(version: Any) -> str | None:
    if version.source == TextSource.template.value:
        return f"Uit de standaardtekst {version.template_label}"
    if version.source == TextSource.model.value:
        label = provider_label(version.model_id) or "een taalmodel"
        example = (
            f", met de standaardtekst {version.template_label} als voorbeeld"
            if version.template_label
            else ""
        )
        return f"Opgesteld met {label}{example}"
    return None


def _outcome(review: Any) -> str:
    if review.withdrawn_at is not None:
        return "withdrawn"
    verdicts = [verdict.verdict for verdict in review.verdicts]
    if any(verdict is None for verdict in verdicts):
        return "open"
    return "returned" if "remarks" in verdicts else "agreed"


def _action(
    work: text_flow.TextWork,
    *,
    can_edit: bool,
    viewer_verdict_open: bool,
    has_standard: bool,
) -> ActionOut:
    word = text_flow.KIND_WORDS[work.kind]
    if viewer_verdict_open:
        return ActionOut(key="judge", text="Geef je oordeel")
    if not can_edit:
        return ActionOut(key="none", text="")
    if work.state == text_flow.STATE_NONE:
        if work.kind == TextKind.vacancy_text.value and has_standard:
            return ActionOut(key="start", text="Begin met de standaardtekst")
        return ActionOut(key="write", text=f"Schrijf de {word}")
    if work.state == text_flow.STATE_DRAFT:
        return ActionOut(key="offer", text="Vraag om een oordeel")
    if work.state == text_flow.STATE_IN_REVIEW:
        return ActionOut(key="withdraw", text="Neem terug om verder te schrijven")
    if work.state == text_flow.STATE_RETURNED:
        return ActionOut(key="process", text="Verwerk de opmerkingen")
    if work.state == text_flow.STATE_AGREED:
        return ActionOut(key="settle", text="Stel vast")
    return ActionOut(key="revise", text="Pas de vastgestelde tekst aan")


def _with_whom(
    work: text_flow.TextWork, names: dict[UUID, str], has_names: bool
) -> str | None:
    review = work.round
    if work.state == text_flow.STATE_IN_REVIEW and review is not None:
        waiting = [v for v in review.verdicts if v.verdict is None]
        if has_names:
            who = ", ".join(names.get(v.reviewer_id, "een collega") for v in waiting)
            return f"Wacht op het oordeel van {who}"
        count = len(waiting)
        unit = "collega" if count == 1 else "collega's"
        return f"Wacht op het oordeel van {count} {unit}"
    if work.state == text_flow.STATE_RETURNED:
        writer = names.get(work.writer_id) if work.writer_id and has_names else None
        return f"Terug bij {writer}" if writer else "Terug bij de schrijver"
    return None


async def _text_work_response(
    db: AsyncSession,
    decider: Any,
    subject: Any,
    vacancy: Vacancy,
    assignment_id: UUID | None,
    settings: Settings,
) -> dict[str, Any]:
    resource = _resource(vacancy, assignment_id)
    permitted = await _permitted(decider, subject, resource)
    can_edit = bool(await decide(decider, subject, Action.EDIT, resource))
    can_review = bool(await decide(decider, subject, Action.REVIEW_TEXT, resource))
    has_names = DataClass.STAFFING in permitted
    viewer_id = subject.person_id
    works = await text_flow.work_of(db, vacancy)

    person_ids: set[UUID] = set()
    for work in works.values():
        for version in work.versions:
            person_ids.update({version.created_by_id, version.established_by_id})
        for review in work.reviews:
            person_ids.add(review.offered_by_id)
            person_ids.update(v.reviewer_id for v in review.verdicts)
        person_ids.update(remark.author_id for remark in work.remarks)
    person_ids.discard(None)
    repo = VacancyRepository(db)
    names = await repo.person_names_by_id(person_ids) if has_names else {}

    match = await library.find_template(db, vacancy) if can_edit else None
    texts: list[TextWorkOut] = []
    for kind, work in works.items():
        if not work.needed and not work.versions:
            # A text this vacancy does not need: nothing is shown about it.
            continue
        number = {version.id: index for index, version in enumerate(work.versions, 1)}
        review = work.round
        mine = None
        if review is not None and viewer_id is not None:
            mine = next(
                (
                    v
                    for v in review.verdicts
                    if v.reviewer_id == viewer_id and v.verdict is None
                ),
                None,
            )
        standard = None
        if kind == TextKind.vacancy_text.value and match is not None:
            resolved = await library.resolve_for_vacancy(db, vacancy, match.template)
            standard = StandardTextOut(
                role=match.template.role_name,
                match=match.how,
                unread=library.status_of(match.template) == "derived_unread",
                # What will still be open in a text started from it.
                missing=[
                    library.FACT_KINDS[name].instruction
                    if name in library.FACT_KINDS
                    else library.PLACEHOLDERS.get(name, name)
                    for name in resolved.missing
                ],
            )
        roots = [remark for remark in work.remarks if remark.parent_id is None]

        def remark_out(
            remark: Any,
            work: text_flow.TextWork = work,
            number: dict[UUID, int] = number,
        ) -> RemarkOut:
            return RemarkOut(
                id=remark.id,
                section=remark.section,
                body=remark.body,
                version_number=number.get(remark.text_id),
                created_at=remark.created_at,
                author_name=names.get(remark.author_id),
                by_viewer=remark.author_id == viewer_id,
                resolved_at=remark.resolved_at,
                answers=[
                    remark_out(answer)
                    for answer in work.remarks
                    if answer.parent_id == remark.id
                ],
            )

        changes: list[ChangeOut] = []
        if len(work.versions) >= 2:
            changes = [
                ChangeOut(
                    heading=change.heading,
                    change=change.change,
                    summary=change.summary,
                    before=change.before,
                    after=change.after,
                )
                for change in text_flow.compare(
                    work.reading(work.versions[-2]), work.reading(work.versions[-1])
                )
                if change.change != "same"
            ]
        texts.append(
            TextWorkOut(
                kind=TextKind(kind),
                needed=work.needed,
                state=work.state,
                state_text=STATE_WORDS[work.state],
                with_whom=_with_whom(work, names, has_names),
                revising=work.revising,
                open_passages=work.open_passages,
                facts=[
                    FactOut(
                        key=fact.key,
                        label=fact.label,
                        value=fact.value,
                        source=fact.source,
                        where=fact.where,
                        instruction=fact.instruction,
                    )
                    for fact in work.facts.values()
                ],
                changed_facts=[
                    ChangedFactOut(
                        key=changed.key,
                        label=changed.label,
                        settled=changed.settled,
                        current=changed.current,
                    )
                    for changed in work.changed_facts
                ],
                action=_action(
                    work,
                    can_edit=can_edit,
                    viewer_verdict_open=mine is not None,
                    has_standard=standard is not None,
                ),
                may_write=can_edit and work.state != text_flow.STATE_IN_REVIEW,
                may_remark=can_review and work.latest is not None,
                may_settle=can_edit
                and work.latest is not None
                and work.state
                in (
                    text_flow.STATE_DRAFT,
                    text_flow.STATE_RETURNED,
                    text_flow.STATE_AGREED,
                )
                and not work.open_passages,
                viewer_review_id=review.id if mine is not None and review else None,
                standard_text=standard,
                default_reviewer_ids=await text_flow.default_reviewers(
                    db, vacancy, kind
                )
                if can_edit
                else [],
                versions=[
                    VersionOut(
                        id=version.id,
                        number=number[version.id],
                        body=work.editing(version),
                        text=work.reading(version),
                        source=version.source,
                        origin=_origin(version),
                        created_at=version.created_at,
                        settled_at=version.established_at,
                        created_by_name=names.get(version.created_by_id),
                        settled_by_name=names.get(version.established_by_id),
                        by_viewer=version.created_by_id == viewer_id,
                    )
                    for version in work.versions
                ],
                rounds=[
                    RoundOut(
                        id=item.id,
                        round=item.round,
                        version_number=number.get(item.text_id, 0),
                        offered_at=item.offered_at,
                        offered_by_name=names.get(item.offered_by_id),
                        note=item.note,
                        withdrawn=item.withdrawn_at is not None,
                        outcome=_outcome(item),
                        verdicts=[
                            VerdictOut(
                                reviewer_id=verdict.reviewer_id,
                                reviewer_name=names.get(verdict.reviewer_id),
                                is_viewer=verdict.reviewer_id == viewer_id,
                                verdict=verdict.verdict,
                                note=verdict.note,
                                decided_at=verdict.decided_at,
                            )
                            for verdict in item.verdicts
                        ],
                    )
                    for item in work.reviews
                ],
                remarks=[remark_out(remark) for remark in roots],
                latest_changes=changes,
            )
        )

    vacancy_text = works[TextKind.vacancy_text.value]
    skipped = not vacancy_text.needed and not vacancy_text.versions
    published = await text_flow.publications(db, vacancy.id)
    is_open = vacancy.status in (VacancyStatus.open.value, VacancyStatus.filled.value)
    reviewer_options: list[ReviewerOptionOut] = []
    if can_edit and has_names:
        reviewer_options = [
            ReviewerOptionOut(id=person_id, name=name)
            for person_id, name in await internal_judges.judge_options(db)
            if person_id != viewer_id
        ]
    provider = active_provider(settings)
    value = VacancyTextWorkOut(
        vacancy_id=vacancy.id,
        texts=texts,
        publications=[
            PublicationOut(
                id=row.id,
                place=row.place,
                place_text=text_flow.PLACE_LABELS[row.place],
                url=row.url,
                published_on=row.published_on,
            )
            for row in published
        ],
        may_record_publication=can_edit and is_open,
        publication_missing=is_open
        and text_flow.is_needed(vacancy, TextKind.vacancy_text.value)
        and not published,
        drafting_available=can_edit and is_llm_configured(settings),
        drafting_note="Het concept komt van het lokale ontwikkelmodel, niet van VLAM."
        if provider == PROVIDER_CLAUDE_CLI
        else None,
        reviewer_options=reviewer_options,
        vacancy_text_skipped=skipped,
        may_want_text=skipped and can_edit,
    )
    return build_response(value, permitted)


async def _loaded(
    db: AsyncSession,
    decider: Any,
    subject: Any,
    vacancy_id: UUID,
    *,
    action: Action | None,
) -> tuple[Vacancy, UUID | None]:
    if action is Action.EDIT:
        return await _load_for_edit(db, decider, subject, vacancy_id)
    vacancy, assignment_id = await _load_reader(db, decider, subject, vacancy_id)
    if action is not None:
        await require(decider, subject, action, _resource(vacancy, assignment_id))
    return vacancy, assignment_id


async def _load_reader(
    db: AsyncSession, decider: Any, subject: Any, vacancy_id: UUID
) -> tuple[Vacancy, UUID | None]:
    """The vacancy for whoever may read it without names (a reviewer too)."""
    from grip.api.routes.vacancies import _assignment_of
    from grip.services.vacancies import service

    try:
        vacancy = await service.get_vacancy(db, vacancy_id)
    except NotFoundError:
        vacancy = None
    if vacancy is None:
        await require(
            decider,
            subject,
            Action.READ,
            vacancy_resource(vacancy_id),
            DataClass.STAFFING_COUNTS,
            hide_existence=True,
        )
        raise NotFoundError("Vacature", vacancy_id)
    assignment_id, _name = await _assignment_of(db, vacancy)
    await require(
        decider,
        subject,
        Action.READ,
        _resource(vacancy, assignment_id),
        DataClass.STAFFING_COUNTS,
        hide_existence=True,
    )
    return vacancy, assignment_id


@router.get("/vacancies/{vacancy_id}/text-work", response_model=None)
async def get_text_work(
    vacancy_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Where the texts of the vacancy stand and what the viewer can do."""
    vacancy, assignment_id = await _load_reader(db, decider, subject, vacancy_id)
    return await _text_work_response(
        db, decider, subject, vacancy, assignment_id, settings
    )


async def _again(
    db: AsyncSession, decider: Any, subject: Any, vacancy_id: UUID, settings: Settings
) -> dict[str, Any]:
    from grip.services.vacancies import service

    await db.flush()
    vacancy = await service.get_vacancy(db, vacancy_id)
    await db.refresh(vacancy, ["texts"])
    from grip.api.routes.vacancies import _assignment_of

    assignment_id, _name = await _assignment_of(db, vacancy)
    return await _text_work_response(
        db, decider, subject, vacancy, assignment_id, settings
    )


@router.post(
    "/vacancies/{vacancy_id}/text-work/versions",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def save_version(
    vacancy_id: UUID,
    body: SaveIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Write on: a new version on top of the one you started from.

    409 when someone else saved in between; nothing is overwritten.
    """
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await text_flow.save_version(
        db,
        vacancy,
        body.kind,
        actor=person,
        body=body.body,
        based_on_id=body.based_on_id,
    )
    return await _again(db, decider, subject, vacancy_id, settings)


@router.post(
    "/vacancies/{vacancy_id}/text-work/standard",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def use_standard_text(
    vacancy_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Start the vacancy text from the standard text of the role."""
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    work = (await text_flow.work_of(db, vacancy))[TextKind.vacancy_text.value]
    if work.state == text_flow.STATE_IN_REVIEW:
        raise DomainValidationError("De vacaturetekst ligt ter beoordeling.")
    await library.use_standard_text(db, vacancy, actor=person)
    return await _again(db, decider, subject, vacancy_id, settings)


async def _context(
    db: AsyncSession,
    corpus: CorpusClient,
    settings: Settings,
    vacancy: Vacancy,
    assignment_id: UUID | None,
) -> context_fetch.FetchedContext:
    """The policy context of the assignment the vacancy belongs to: the
    same block a quote section gets."""
    if assignment_id is None:
        return context_fetch.FetchedContext()
    assignment = await db.get(Assignment, assignment_id)
    from grip.api.routes.quote_drafts import assignment_context

    try:
        return await assignment_context(db, corpus, settings, assignment)
    except Exception:  # the corpus is a help, never a condition
        logger.warning("No corpus context for vacancy %s", vacancy.id, exc_info=True)
        return context_fetch.FetchedContext(state=context_fetch.CONTEXT_UNREACHABLE)


@router.post(
    "/vacancies/{vacancy_id}/text-work/tailored",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def draft_tailored(
    vacancy_id: UUID,
    body: TailoredIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    corpus: CorpusClient = Depends(node_picker.get_corpus_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Draft a vacancy text for this vacancy, with the standard text of the
    role as example. A proposal: a person reads, changes and settles it."""
    vacancy, assignment_id = await _load_for_edit(db, decider, subject, vacancy_id)
    context = await _context(db, corpus, settings, vacancy, assignment_id)
    try:
        await text_flow.draft_tailored(
            db,
            vacancy,
            actor=person,
            instruction=body.instruction,
            context=context.lines,
        )
    except LlmNotConfiguredError as exc:
        raise DomainValidationError(str(exc)) from exc
    except LlmResponseError as exc:
        raise DomainValidationError(str(exc)) from exc
    except OpenAIError as exc:
        logger.warning("Drafting with the language model failed: %s", exc)
        raise DomainValidationError(
            "Het taalmodel gaf geen antwoord. Probeer het later opnieuw, of "
            "begin met de standaardtekst."
        ) from exc
    out = await _again(db, decider, subject, vacancy_id, settings)
    # "used", "none" or "unreachable": so the screen can say that a draft was
    # made without the context of the corpus when that could not be asked.
    out["context"] = context.state
    return out


@router.post("/vacancies/{vacancy_id}/text-work/passage", response_model=None)
async def propose_passage(
    vacancy_id: UUID,
    body: PassageIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    corpus: CorpusClient = Depends(node_picker.get_corpus_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """A proposal for one open place of the vacancy text, from the policy
    context of the assignment and the facts of the vacancy. Nothing is
    stored: the writer takes it over or not."""
    vacancy, assignment_id = await _load_for_edit(db, decider, subject, vacancy_id)
    context = await _context(db, corpus, settings, vacancy, assignment_id)
    try:
        proposal = await text_flow.propose_passage(
            db,
            vacancy,
            actor=person,
            body=body.body,
            place=body.place,
            context=context.lines,
        )
    except (LlmNotConfiguredError, LlmResponseError) as exc:
        raise DomainValidationError(str(exc)) from exc
    except OpenAIError as exc:
        logger.warning("Proposing a passage with the language model failed: %s", exc)
        raise DomainValidationError(
            "Het taalmodel gaf geen antwoord. Probeer het later opnieuw, of "
            "schrijf de passage zelf."
        ) from exc
    return {"proposal": proposal, "context": context.state}


@router.post(
    "/vacancies/{vacancy_id}/text-work/wanted",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def want_text(
    vacancy_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Write a vacancy text for a vacancy that needs none by its kind."""
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await text_flow.want_text(db, vacancy, actor=person)
    return await _again(db, decider, subject, vacancy_id, settings)


@router.post(
    "/vacancies/{vacancy_id}/text-work/reviews",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def offer_for_review(
    vacancy_id: UUID,
    body: OfferIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Offer the latest version to people to judge: a round."""
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await text_flow.offer_for_review(
        db,
        vacancy,
        body.kind,
        actor=person,
        reviewer_ids=body.reviewer_ids,
        note=body.note,
    )
    return await _again(db, decider, subject, vacancy_id, settings)


@router.post(
    "/vacancies/{vacancy_id}/text-work/reviews/{review_id}/withdraw",
    response_model=None,
)
async def withdraw_review(
    vacancy_id: UUID,
    review_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await text_flow.withdraw_review(db, vacancy, review_id, actor=person)
    return await _again(db, decider, subject, vacancy_id, settings)


@router.post(
    "/vacancies/{vacancy_id}/text-work/reviews/{review_id}/verdict", response_model=None
)
async def give_verdict(
    vacancy_id: UUID,
    review_id: UUID,
    body: VerdictIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Agree, or return the text with remarks. Only who was asked."""
    vacancy, _ = await _loaded(
        db, decider, subject, vacancy_id, action=Action.REVIEW_TEXT
    )
    await text_flow.give_verdict(
        db, vacancy, review_id, actor=person, verdict=body.verdict, note=body.note
    )
    return await _again(db, decider, subject, vacancy_id, settings)


@router.post(
    "/vacancies/{vacancy_id}/text-work/remarks",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def add_remark(
    vacancy_id: UUID,
    body: RemarkIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vacancy, _ = await _loaded(
        db, decider, subject, vacancy_id, action=Action.REVIEW_TEXT
    )
    await text_flow.add_remark(
        db,
        vacancy,
        body.kind,
        actor=person,
        body=body.body,
        section=body.section,
        parent_id=body.parent_id,
    )
    return await _again(db, decider, subject, vacancy_id, settings)


@router.post(
    "/vacancies/{vacancy_id}/text-work/remarks/{remark_id}/resolve", response_model=None
)
async def resolve_remark(
    vacancy_id: UUID,
    remark_id: UUID,
    body: ResolveIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vacancy, _ = await _loaded(
        db, decider, subject, vacancy_id, action=Action.REVIEW_TEXT
    )
    await text_flow.resolve_remark(
        db, vacancy, remark_id, actor=person, resolved=body.resolved
    )
    return await _again(db, decider, subject, vacancy_id, settings)


@router.post(
    "/vacancies/{vacancy_id}/text-work/versions/{text_id}/settle", response_model=None
)
async def settle_text(
    vacancy_id: UUID,
    text_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Take responsibility for the latest version; only then may it leave grip."""
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await text_flow.settle(db, vacancy, text_id, actor=person)
    return await _again(db, decider, subject, vacancy_id, settings)


@router.get("/vacancies/{vacancy_id}/text-work/compare", response_model=None)
async def compare_versions(
    vacancy_id: UUID,
    before: UUID,
    after: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What changed between two versions of a text, per section."""
    vacancy, assignment_id = await _load_reader(db, decider, subject, vacancy_id)
    by_id = {text.id: text for text in vacancy.texts}
    if (
        before not in by_id
        or after not in by_id
        or by_id[before].kind != by_id[after].kind
    ):
        raise NotFoundError("Tekst", before)
    work = (await text_flow.work_of(db, vacancy))[by_id[before].kind]
    changes = text_flow.compare(work.reading(by_id[before]), work.reading(by_id[after]))

    class _Out(BaseModel):
        changes: Annotated[list[ChangeOut], nested()]

    permitted = await _permitted(decider, subject, _resource(vacancy, assignment_id))
    return build_response(
        _Out(
            changes=[
                ChangeOut(
                    heading=c.heading,
                    change=c.change,
                    summary=c.summary,
                    before=c.before,
                    after=c.after,
                )
                for c in changes
                if c.change != "same"
            ]
        ),
        permitted,
    )


# --- where the vacancy is published -------------------------------------------


@router.put("/vacancies/{vacancy_id}/publications", response_model=None)
async def set_publication(
    vacancy_id: UUID,
    body: PublicationIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Record the public address of the published vacancy, per place."""
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await text_flow.set_publication(
        db,
        vacancy,
        actor=person,
        place=body.place,
        url=body.url,
        published_on=body.published_on,
    )
    return await _again(db, decider, subject, vacancy_id, settings)


@router.delete(
    "/vacancies/{vacancy_id}/publications/{publication_id}", response_model=None
)
async def remove_publication(
    vacancy_id: UUID,
    publication_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vacancy, _ = await _load_for_edit(db, decider, subject, vacancy_id)
    await text_flow.remove_publication(db, vacancy, publication_id, actor=person)
    return await _again(db, decider, subject, vacancy_id, settings)


# --- the library of standard texts --------------------------------------------


class SectionIn(BaseModel):
    key: str | None = None
    heading: str = ""
    body: str = ""
    shared: str | None = None
    optional: str | None = None


class TemplateIn(BaseModel):
    role_name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    scale_min: int | None = Field(default=None, ge=1, le=19)
    scale_max: int | None = Field(default=None, ge=1, le=19)
    function_group: str | None = Field(default=None, max_length=255)
    sections: list[SectionIn] | None = None
    copy_of: UUID | None = None


class SharedIn(BaseModel):
    heading: str = Field(max_length=200)
    body: str = Field(min_length=1, max_length=library.MAX_BODY)


class TextSettingsIn(BaseModel):
    unit_name: str = Field(default="", max_length=300)
    location: str = Field(default="", max_length=300)
    website: str = Field(default="", max_length=300)
    contact: str = Field(default="", max_length=300)


STATUS_WORDS = {
    "example": "Uit de voorbeelden",
    "derived": "Afgeleid en nagelezen",
    "derived_unread": "Afgeleid, nog niet nagelezen",
    "manual": "Zelf toegevoegd",
    "changed": "Aangepast",
}


def _sections_in(sections: list[SectionIn] | None) -> list[dict[str, Any]] | None:
    if sections is None:
        return None
    result: list[dict[str, Any]] = []
    for section in sections:
        if section.shared:
            result.append({"shared": section.shared})
        else:
            entry: dict[str, Any] = {
                "key": section.key,
                "heading": section.heading,
                "body": section.body,
            }
            if section.optional:
                entry["optional"] = section.optional
            result.append(entry)
    return result


async def _library_out(db: AsyncSession, *, may_manage: bool) -> dict[str, Any]:
    templates = await library.list_templates(db)
    shared = await library.shared_sections(db)
    usage = library.usage_of_shared(templates)
    people = await VacancyRepository(db).person_names_by_id(
        {t.changed_by_id for t in templates if t.changed_by_id}
        | {s.changed_by_id for s in shared if s.changed_by_id}
    )
    return {
        "may_manage": may_manage,
        "placeholders": [
            {"name": name, "meaning": meaning}
            for name, meaning in library.PLACEHOLDERS.items()
        ],
        "settings": await instance_settings.get(db, library.TEXT_SETTINGS.key),
        "settings_version": await instance_settings.version(db),
        "shared_sections": [
            {
                "key": section.key,
                "heading": section.heading,
                "body": section.body,
                "used_by": usage.get(section.key, []),
                "version": section.version,
                "changed_at": section.changed_at,
                "changed_by_name": people.get(section.changed_by_id)
                if may_manage
                else None,
            }
            for section in shared
        ],
        "templates": [
            {
                "id": template.id,
                "version": template.version,
                "role_name": template.role_name,
                "aliases": template.aliases,
                "scale_min": template.scale_min,
                "scale_max": template.scale_max,
                "function_group": template.function_group,
                "status": library.status_of(template),
                "status_text": STATUS_WORDS[library.status_of(template)],
                "changed_at": template.changed_at,
                "changed_by_name": people.get(template.changed_by_id)
                if may_manage
                else None,
                "is_active": template.is_active,
                "sections": template.sections,
                "label": library.template_label(template),
            }
            for template in templates
        ],
    }


async def _may_manage(decider: Any, subject: Any) -> bool:
    return bool(await decide(decider, subject, Action.EDIT, form_template_resource()))


async def _require_manage(decider: Any, subject: Any) -> None:
    await require(decider, subject, Action.EDIT, form_template_resource())


@router.get("/vacancy-texts", response_model=None)
async def get_library(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """The standard texts. Read by whoever may make a vacancy; changed by
    whoever manages the vacancy setup."""
    may_manage = await _may_manage(decider, subject)
    if not may_manage:
        await require(decider, subject, Action.EDIT, vacancy_resource(None))
    return await _library_out(db, may_manage=may_manage)


@router.post(
    "/vacancy-texts/templates", response_model=None, status_code=status.HTTP_201_CREATED
)
async def add_template(
    body: TemplateIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Add a standard text for a role, written or as a copy of another."""
    await _require_manage(decider, subject)
    await library.save_template(
        db,
        None,
        actor=person,
        role_name=body.role_name,
        sections=_sections_in(body.sections),
        aliases=body.aliases,
        scale_min=body.scale_min,
        scale_max=body.scale_max,
        function_group=body.function_group,
        copy_of=body.copy_of,
    )
    return await _library_out(db, may_manage=True)


@router.put("/vacancy-texts/templates/{template_id}", response_model=None)
async def change_template(
    template_id: UUID,
    body: TemplateIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manage(decider, subject)
    await library.save_template(
        db,
        template_id,
        actor=person,
        role_name=body.role_name,
        sections=_sections_in(body.sections),
        aliases=body.aliases,
        scale_min=body.scale_min,
        scale_max=body.scale_max,
        function_group=body.function_group,
    )
    return await _library_out(db, may_manage=True)


@router.post("/vacancy-texts/templates/{template_id}/read", response_model=None)
async def mark_template_read(
    template_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Say that a derived text was read and stands."""
    await _require_manage(decider, subject)
    await library.mark_read(db, template_id, actor=person)
    return await _library_out(db, may_manage=True)


class ActiveIn(BaseModel):
    is_active: bool


@router.post("/vacancy-texts/templates/{template_id}/active", response_model=None)
async def set_template_active(
    template_id: UUID,
    body: ActiveIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manage(decider, subject)
    await library.set_active(db, template_id, body.is_active, actor=person)
    return await _library_out(db, may_manage=True)


@router.put("/vacancy-texts/shared/{key}", response_model=None)
async def change_shared_section(
    key: str,
    body: SharedIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Change a section every standard text shares: once, for every role."""
    await _require_manage(decider, subject)
    await library.update_shared_section(
        db, key, heading=body.heading, body=body.body, actor=person
    )
    return await _library_out(db, may_manage=True)


@router.put("/vacancy-texts/settings", response_model=None)
async def change_text_settings(
    body: TextSettingsIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manage(decider, subject)
    await instance_settings.set_values(
        db, {library.TEXT_SETTINGS.key: body.model_dump()}, actor=person
    )
    return await _library_out(db, may_manage=True)


class PreviewIn(BaseModel):
    function_title: str | None = Field(default=None, max_length=255)
    scale: int | None = Field(default=None, ge=1, le=19)
    fte: str | None = None


@router.post("/vacancy-texts/templates/{template_id}/preview", response_model=None)
async def preview_template(
    template_id: UUID,
    body: PreviewIn,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A standard text filled in for a sample vacancy."""
    if not await _may_manage(decider, subject):
        await require(decider, subject, Action.EDIT, vacancy_resource(None))
    from decimal import Decimal, InvalidOperation

    template = await library.get_template(db, template_id)
    try:
        fte = Decimal(body.fte.replace(",", ".")) if body.fte else Decimal("1")
    except InvalidOperation as exc:
        raise DomainValidationError("Het aantal fte is een getal.") from exc
    sample = Vacancy(
        function_title=body.function_title or template.role_name,
        scale=body.scale or template.scale_max or template.scale_min,
        fte=fte,
        declarable=True,
        contract_type="temporary_before_permanent",
    )
    resolved = await library.resolve_for_vacancy(db, sample, template)
    return {
        "text": resolved.text,
        "missing": [library.PLACEHOLDERS.get(name, name) for name in resolved.missing],
    }


# --- the language model -------------------------------------------------------


@router.get("/vacancy-texts/model", response_model=None)
async def model_status(
    subject: CurrentSubject,
    decider: AccessDecider,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Which model drafts texts here. For the beheerder."""
    await require(decider, subject, Action.READ, language_model_resource())
    provider = active_provider(settings)
    return {
        "provider": provider,
        "provider_text": {
            PROVIDER_NONE: "Geen taalmodel ingesteld",
            PROVIDER_CLAUDE_CLI: "Claude via de lokale ontwikkelomgeving",
        }.get(provider, "VLAM"),
        "available": is_llm_configured(settings),
        "development": provider == PROVIDER_CLAUDE_CLI,
        "note": "Dit is het ontwikkelmodel. Tekst die je laat opstellen verlaat "
        "de eigen modeldienst van de overheid; gebruik alleen verzonnen gegevens."
        if provider == PROVIDER_CLAUDE_CLI
        else None,
    }


@router.post("/vacancy-texts/model/test", response_model=None)
async def test_model(
    subject: CurrentSubject,
    decider: AccessDecider,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Send one line to the model and say whether it answered."""
    await require(decider, subject, Action.EDIT, language_model_resource())
    started = time.monotonic()
    try:
        client = get_chat_client(settings)
        answer = await client.complete(
            system="Je antwoordt met één woord.",
            user="Antwoord met het woord: werkt",
            max_tokens=20,
        )
    except (LlmNotConfiguredError, LlmResponseError) as exc:
        return {"answered": False, "message": str(exc)}
    except OpenAIError:
        return {"answered": False, "message": "Het taalmodel gaf geen antwoord."}
    seconds = round(time.monotonic() - started, 1)
    return {
        "answered": True,
        "message": "Het taalmodel antwoordde in "
        + str(seconds).replace(".", ",")
        + " seconden.",
        "model": provider_label(client.model_id),
        "answer": answer[:40],
    }
