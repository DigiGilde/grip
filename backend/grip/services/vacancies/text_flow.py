"""The course of a text on a vacancy: written, reviewed, returned, settled.

A text is a piece of work. Its versions are ``VacancyText`` rows, never
edited. On top of them:

- A person offers the latest version to reviewers: a round. Each reviewer
  agrees or returns it with remarks. As many rounds as it takes; every round
  is kept.
- Remarks hang on a section of the text and are answered and resolved.
- Two people can write on the same draft, one after the other: a save names
  the version it started from, and is refused when someone else saved in
  between. Nothing is overwritten; both texts stay.
- Only a settled version leaves grip. Writing on after settling makes a new
  round and the screens say the settled text is being revised.

Also here: where a published vacancy can be read (``VacancyPublication``).
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core import clock
from grip.core.audit import CREATE, DELETE, UPDATE, record_audit
from grip.models.assignment import Assignment, BudgetLine
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.vacancy import (
    ContractType,
    TextKind,
    TextSource,
    Vacancy,
    VacancyStatus,
    VacancyText,
    VacancyType,
)
from grip.models.vacancy_text_flow import (
    PLACES,
    VERDICT_REMARKS,
    VERDICTS,
    VacancyPublication,
    VacancyTextRemark,
    VacancyTextReview,
    VacancyTextVerdict,
)
from grip.repositories.vacancy import VacancyRepository
from grip.services import internal_judges, stale
from grip.services.errors import DomainError, DomainValidationError, NotFoundError
from grip.services.llm import ChatClient, get_chat_client
from grip.services.vacancies import library
from grip.services.vacancies.drafting import (
    MAX_STANDARD_EXAMPLES,
    PASSAGE_MARK,
    PASSAGE_PROMPT_VERSION,
    TAILORED_PROMPT_VERSION,
    DraftInputError,
    OutlineSection,
    PassageInput,
    StandardExample,
    TailoredInput,
    build_passage_prompt,
    build_tailored_prompt,
    clean_passage,
    find_person_names,
    parse_sections,
)

STATE_NONE = "none"
STATE_DRAFT = "draft"
STATE_IN_REVIEW = "in_review"
STATE_RETURNED = "returned"
STATE_AGREED = "agreed"
STATE_SETTLED = "settled"

KIND_WORDS = {
    TextKind.vacancy_text.value: "vacaturetekst",
    TextKind.motivation.value: "motivatie",
}

_PUBLISHING_TYPES = (VacancyType.regulier.value, VacancyType.specialistisch.value)


class TextConflictError(DomainError):
    """Someone else saved the text in between."""

    http_status = 409


def _now() -> datetime:
    return datetime.now(UTC)


def is_needed(vacancy: Vacancy, kind: str) -> bool:
    """Whether this vacancy needs this text at all.

    The motivation goes on the request form, so every vacancy needs one. A
    vacancy text is for a vacancy that is opened; one for an intended or
    ready candidate is not published and needs none, unless someone chose to
    write one for it.
    """
    if kind == TextKind.motivation.value:
        return True
    return vacancy.vacancy_type in _PUBLISHING_TYPES or bool(vacancy.wants_text)


# --- reading ------------------------------------------------------------------


@dataclass
class TextWork:
    kind: str
    needed: bool
    state: str
    versions: list[VacancyText]
    reviews: list[VacancyTextReview]
    remarks: list[VacancyTextRemark]
    latest: VacancyText | None = None
    settled: VacancyText | None = None
    # A settled text exists and a newer version is being written.
    revising: bool = False
    open_passages: list[str] = field(default_factory=list)
    # The facts of the vacancy a vacancy text can name, by key.
    facts: dict[str, library.Fact] = field(default_factory=dict)
    # Facts that read differently now than in the settled text.
    changed_facts: list[library.ChangedFact] = field(default_factory=list)

    def reading(self, version: VacancyText) -> str:
        """A version as it reads: a settled one as it was frozen, a draft
        with the facts as they stand now."""
        if version.is_established:
            return version.body
        return library.shown(version.body, self.facts)

    def editing(self, version: VacancyText) -> str:
        """A version as a person writes on from it: with the facts by key."""
        return version.keyed_body or version.body

    @property
    def round(self) -> VacancyTextReview | None:
        """The round on the latest version, if it was offered."""
        for review in reversed(self.reviews):
            if review.withdrawn_at is None:
                if self.latest is not None and review.text_id == self.latest.id:
                    return review
                return None
        return None

    @property
    def writer_id(self) -> UUID | None:
        review = self.round
        if review is not None and review.offered_by_id is not None:
            return review.offered_by_id
        return self.latest.created_by_id if self.latest is not None else None


def _state(latest: VacancyText | None, review: VacancyTextReview | None) -> str:
    if latest is None:
        return STATE_NONE
    if latest.is_established:
        return STATE_SETTLED
    if review is None:
        return STATE_DRAFT
    verdicts = [verdict.verdict for verdict in review.verdicts]
    if any(verdict is None for verdict in verdicts):
        return STATE_IN_REVIEW
    if any(verdict == VERDICT_REMARKS for verdict in verdicts):
        return STATE_RETURNED
    return STATE_AGREED


def _work(
    vacancy: Vacancy,
    kind: str,
    versions: list[VacancyText],
    reviews: list[VacancyTextReview],
    remarks: list[VacancyTextRemark],
    facts: dict[str, library.Fact],
) -> TextWork:
    versions = sorted(versions, key=lambda version: version.created_at)
    latest = versions[-1] if versions else None
    settled = next((v for v in reversed(versions) if v.is_established), None)
    work = TextWork(
        kind=kind,
        needed=is_needed(vacancy, kind),
        state=STATE_NONE,
        versions=versions,
        reviews=reviews,
        remarks=remarks,
        latest=latest,
        settled=settled,
        facts=facts,
    )
    work.state = _state(latest, work.round)
    work.revising = (
        settled is not None and latest is not None and latest.id != settled.id
    )
    if latest is not None and not latest.is_established:
        work.open_passages = library.open_passages(latest.body, facts)
    if settled is not None:
        work.changed_facts = library.changed_facts(settled.facts, facts)
    return work


async def work_of(db: AsyncSession, vacancy: Vacancy) -> dict[str, TextWork]:
    """Where each text of the vacancy stands."""
    return (await works_of(db, [vacancy]))[vacancy.id]


async def works_of(
    db: AsyncSession, vacancies: Iterable[Vacancy]
) -> dict[UUID, dict[str, TextWork]]:
    """``work_of`` of several vacancies, read together."""
    wanted = list(vacancies)
    ids = [vacancy.id for vacancy in wanted]
    if not ids:
        return {}
    reviews: dict[UUID, list[VacancyTextReview]] = {i: [] for i in ids}
    for review in await db.scalars(
        select(VacancyTextReview)
        .where(VacancyTextReview.vacancy_id.in_(ids))
        .order_by(VacancyTextReview.round)
    ):
        reviews[review.vacancy_id].append(review)
    remarks: dict[UUID, list[VacancyTextRemark]] = {i: [] for i in ids}
    for remark in await db.scalars(
        select(VacancyTextRemark)
        .where(VacancyTextRemark.vacancy_id.in_(ids))
        .order_by(VacancyTextRemark.created_at)
    ):
        remarks[remark.vacancy_id].append(remark)
    texts: dict[tuple[UUID, str], list[VacancyText]] = {}
    for text in await db.scalars(
        select(VacancyText)
        .where(VacancyText.vacancy_id.in_(ids))
        .order_by(VacancyText.created_at, VacancyText.id)
    ):
        texts.setdefault((text.vacancy_id, text.kind), []).append(text)
    facts = await library.facts_for_many(db, wanted)
    result: dict[UUID, dict[str, TextWork]] = {}
    for vacancy in wanted:
        works = {}
        for kind in (TextKind.motivation.value, TextKind.vacancy_text.value):
            works[kind] = _work(
                vacancy,
                kind,
                texts.get((vacancy.id, kind), []),
                [review for review in reviews[vacancy.id] if review.kind == kind],
                [remark for remark in remarks[vacancy.id] if remark.kind == kind],
                # Only a vacancy text names facts; a motivation is prose.
                facts[vacancy.id] if kind == TextKind.vacancy_text.value else {},
            )
        result[vacancy.id] = works
    return result


async def _one(db: AsyncSession, vacancy: Vacancy, kind: TextKind | str) -> TextWork:
    return (await work_of(db, vacancy))[TextKind(kind).value]


async def default_reviewers(
    db: AsyncSession, vacancy: Vacancy, kind: str
) -> list[UUID]:
    """Who usually judges this text: a proposal, the writer chooses.

    The motivation is read by whoever approves the request (the addressee of
    the form); the vacancy text by the HR adviser, who also advises on the
    request. Only people with an account can be asked.
    """
    repo = VacancyRepository(db)
    wanted = "approval" if kind == TextKind.motivation.value else "hr_advice"
    decision = await repo.decision(vacancy.id, wanted)
    candidates = [decision.person_id if decision else None]
    if kind == TextKind.motivation.value:
        candidates.append(vacancy.addressee_id)
    wanted_ids = [
        person_id for person_id in dict.fromkeys(candidates) if person_id is not None
    ]
    outside = await internal_judges.client_side_only(db, wanted_ids)
    return [person_id for person_id in wanted_ids if person_id not in outside]


# --- writing ------------------------------------------------------------------


def _audit(
    db: AsyncSession,
    actor: Person | None,
    action: str,
    entity: str,
    entity_id: Any,
    vacancy_id: UUID,
    **values: Any,
) -> None:
    record_audit(
        db,
        actor=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        new_value=values,
        vacancy_id=vacancy_id,
    )


async def save_version(
    db: AsyncSession,
    vacancy: Vacancy,
    kind: TextKind | str,
    *,
    actor: Person,
    body: str,
    based_on_id: UUID | None,
) -> VacancyText:
    """A person writes on: a new version on top of the one they started from."""
    kind = TextKind(kind)
    if not body.strip():
        raise DomainValidationError("De tekst is leeg.")
    work = await _one(db, vacancy, kind)
    if work.state == STATE_IN_REVIEW:
        raise DomainValidationError(
            f"De {KIND_WORDS[kind.value]} ligt ter beoordeling. Trek de "
            "beoordeling in om verder te schrijven."
        )
    latest_id = work.latest.id if work.latest else None
    if based_on_id != latest_id:
        names = await VacancyRepository(db).person_names_by_id(
            [work.latest.created_by_id]
            if work.latest and work.latest.created_by_id
            else []
        )
        who = next(iter(names.values()), "Iemand anders")
        raise TextConflictError(
            f"{who} heeft de {KIND_WORDS[kind.value]} opgeslagen terwijl jij "
            "schreef. Jouw tekst is niet opgeslagen en staat nog in het "
            "formulier. Bekijk de nieuwe versie, neem over wat je wilt "
            "houden en sla opnieuw op."
        )
    if work.latest is not None and work.editing(work.latest).strip() == body.strip():
        raise DomainValidationError("Er is niets gewijzigd.")
    text = VacancyText(
        vacancy_id=vacancy.id,
        kind=kind.value,
        body=body.strip(),
        source=TextSource.human.value,
        based_on_id=based_on_id,
        template_label=work.latest.template_label if work.latest else None,
        created_by_id=actor.id,
    )
    db.add(text)
    await db.flush()
    _audit(
        db,
        actor,
        CREATE,
        "vacancy_text",
        text.id,
        vacancy.id,
        kind=kind.value,
        source=text.source,
        based_on_id=str(based_on_id) if based_on_id else None,
        reopens_settled=bool(work.state == STATE_SETTLED),
    )
    return text


async def offer_for_review(
    db: AsyncSession,
    vacancy: Vacancy,
    kind: TextKind | str,
    *,
    actor: Person,
    reviewer_ids: Iterable[UUID],
    note: str | None = None,
) -> VacancyTextReview:
    kind = TextKind(kind)
    work = await _one(db, vacancy, kind)
    word = KIND_WORDS[kind.value]
    if work.latest is None:
        raise DomainValidationError(f"Er is nog geen {word} om te laten beoordelen.")
    if work.state == STATE_SETTLED:
        raise DomainValidationError(f"De {word} is al vastgesteld.")
    if work.state == STATE_IN_REVIEW:
        raise DomainValidationError(f"De {word} ligt al ter beoordeling.")
    if work.round is not None:
        raise DomainValidationError(
            "Deze versie is al beoordeeld. Verwerk de opmerkingen in een nieuwe "
            "versie, of stel de tekst vast."
        )
    ids = list(dict.fromkeys(reviewer_ids))
    if not ids:
        raise DomainValidationError("Kies wie de tekst beoordeelt.")
    if ids == [actor.id]:
        raise DomainValidationError(
            "Je kunt je eigen tekst niet als enige beoordelen. Kies een ander, "
            "of stel de tekst vast."
        )
    repo = VacancyRepository(db)
    for person_id in ids:
        await internal_judges.require_internal(db, person_id)
        if await repo.active_person(person_id) is None:
            raise DomainValidationError(
                "Een beoordelaar heeft een account in grip nodig. Kies iemand "
                "uit de lijst."
            )
    review = VacancyTextReview(
        vacancy_id=vacancy.id,
        kind=kind.value,
        round=len(work.reviews) + 1,
        text_id=work.latest.id,
        offered_by_id=actor.id,
        note=(note or "").strip() or None,
    )
    review.verdicts = [VacancyTextVerdict(reviewer_id=person_id) for person_id in ids]
    db.add(review)
    await db.flush()
    _audit(
        db,
        actor,
        CREATE,
        "vacancy_text_review",
        review.id,
        vacancy.id,
        kind=kind.value,
        round=review.round,
        reviewers=len(ids),
    )
    return review


async def _review(
    db: AsyncSession, vacancy: Vacancy, review_id: UUID
) -> VacancyTextReview:
    review = await db.get(VacancyTextReview, review_id)
    if review is None or review.vacancy_id != vacancy.id:
        raise NotFoundError("Beoordeling", review_id)
    return review


async def withdraw_review(
    db: AsyncSession, vacancy: Vacancy, review_id: UUID, *, actor: Person
) -> VacancyTextReview:
    """The writer takes the text back to write on."""
    review = await _review(db, vacancy, review_id)
    work = await _one(db, vacancy, review.kind)
    if (
        work.round is None
        or work.round.id != review.id
        or work.state != STATE_IN_REVIEW
    ):
        raise DomainValidationError("Deze beoordeling loopt niet meer.")
    review.withdrawn_at = _now()
    await db.flush()
    _audit(
        db, actor, UPDATE, "vacancy_text_review", review.id, vacancy.id, withdrawn=True
    )
    return review


async def give_verdict(
    db: AsyncSession,
    vacancy: Vacancy,
    review_id: UUID,
    *,
    actor: Person,
    verdict: str,
    note: str | None = None,
) -> VacancyTextReview:
    """A reviewer agrees, or returns the text with remarks."""
    if verdict not in VERDICTS:
        raise DomainValidationError("Kies akkoord of terug met opmerkingen.")
    review = await _review(db, vacancy, review_id)
    work = await _one(db, vacancy, review.kind)
    if work.round is None or work.round.id != review.id:
        raise DomainValidationError(
            "De tekst is gewijzigd of teruggenomen nadat je om een oordeel "
            "werd gevraagd."
        )
    mine = next((v for v in review.verdicts if v.reviewer_id == actor.id), None)
    if mine is None:
        raise DomainValidationError(
            "Je bent niet gevraagd om deze tekst te beoordelen."
        )
    if mine.verdict is not None:
        raise DomainValidationError("Je hebt je oordeel over deze versie al gegeven.")
    note = (note or "").strip() or None
    if verdict == VERDICT_REMARKS and note is None:
        own = [
            remark
            for remark in work.remarks
            if remark.author_id == actor.id
            and remark.text_id == review.text_id
            and remark.resolved_at is None
        ]
        if not own:
            raise DomainValidationError(
                "Zeg wat er anders moet: schrijf een opmerking bij een onderdeel, "
                "of licht je oordeel toe."
            )
    mine.verdict = verdict
    mine.note = note
    mine.decided_at = _now()
    await db.flush()
    _audit(
        db,
        actor,
        UPDATE,
        "vacancy_text_review",
        review.id,
        vacancy.id,
        kind=review.kind,
        round=review.round,
        verdict=verdict,
    )
    return review


async def settle(
    db: AsyncSession, vacancy: Vacancy, text_id: UUID, *, actor: Person
) -> VacancyText:
    """Take responsibility for the latest version; only then may it leave grip."""
    text = await VacancyRepository(db).text(text_id)
    if text is None or text.vacancy_id != vacancy.id:
        raise NotFoundError("Tekst", text_id)
    work = await _one(db, vacancy, text.kind)
    word = KIND_WORDS[text.kind]
    if work.latest is None or work.latest.id != text.id:
        raise DomainValidationError(
            f"Er is een nieuwere versie van de {word}. Stel die vast."
        )
    if text.is_established:
        return text
    if work.state == STATE_IN_REVIEW:
        raise DomainValidationError(
            f"De {word} ligt ter beoordeling. Wacht op het oordeel of trek de "
            "beoordeling in."
        )
    if work.open_passages:
        raise DomainValidationError(
            f"In de {word} staat nog iets om in te vullen: "
            + ", ".join(work.open_passages[:3])
            + "."
        )
    freeze(text, work.facts)
    text.established_by_id = actor.id
    text.established_at = _now()
    await db.flush()
    _audit(
        db,
        actor,
        UPDATE,
        "vacancy_text",
        text.id,
        vacancy.id,
        established=True,
        source=text.source,
        rounds=len(work.reviews),
        facts=text.facts or {},
    )
    return text


def freeze(text: VacancyText, facts: dict[str, library.Fact]) -> None:
    """Write the facts out: from here on the text says what it said when it
    was settled, whatever changes on the vacancy afterwards."""
    used = library.used_facts(text.body, facts)
    if not used:
        return
    text.keyed_body = text.body
    text.facts = used
    text.body = library.shown(text.body, facts)


# --- remarks ------------------------------------------------------------------


async def add_remark(
    db: AsyncSession,
    vacancy: Vacancy,
    kind: TextKind | str,
    *,
    actor: Person,
    body: str,
    section: str = "",
    parent_id: UUID | None = None,
) -> VacancyTextRemark:
    kind = TextKind(kind)
    if not body.strip():
        raise DomainValidationError("De opmerking is leeg.")
    work = await _one(db, vacancy, kind)
    if work.latest is None:
        raise DomainValidationError("Er is nog geen tekst om iets bij op te merken.")
    if parent_id is not None:
        parent = await db.get(VacancyTextRemark, parent_id)
        if (
            parent is None
            or parent.vacancy_id != vacancy.id
            or parent.kind != kind.value
        ):
            raise NotFoundError("Opmerking", parent_id)
        if parent.parent_id is not None:
            parent_id = parent.parent_id
        section = parent.section
    remark = VacancyTextRemark(
        vacancy_id=vacancy.id,
        kind=kind.value,
        text_id=work.latest.id,
        section=section.strip()[:200],
        body=body.strip(),
        author_id=actor.id,
        parent_id=parent_id,
    )
    db.add(remark)
    await db.flush()
    _audit(
        db,
        actor,
        CREATE,
        "vacancy_text_remark",
        remark.id,
        vacancy.id,
        kind=kind.value,
        section=remark.section,
        answer=parent_id is not None,
    )
    return remark


async def resolve_remark(
    db: AsyncSession,
    vacancy: Vacancy,
    remark_id: UUID,
    *,
    actor: Person,
    resolved: bool = True,
) -> VacancyTextRemark:
    remark = await db.get(VacancyTextRemark, remark_id)
    if (
        remark is None
        or remark.vacancy_id != vacancy.id
        or remark.parent_id is not None
    ):
        raise NotFoundError("Opmerking", remark_id)
    remark.resolved_at = _now() if resolved else None
    remark.resolved_by_id = actor.id if resolved else None
    await db.flush()
    _audit(
        db,
        actor,
        UPDATE,
        "vacancy_text_remark",
        remark.id,
        vacancy.id,
        resolved=resolved,
    )
    return remark


# --- comparing versions -------------------------------------------------------


@dataclass(frozen=True)
class SectionChange:
    heading: str
    # added, removed, changed or same.
    change: str
    before: str = ""
    after: str = ""
    # Sentences in words a person can read.
    summary: str = ""


def _words(text: str) -> int:
    return len(text.split())


def compare(before: str, after: str) -> list[SectionChange]:
    """What changed between two versions, per section."""
    old = dict(library.split(before))
    new = dict(library.split(after))
    changes: list[SectionChange] = []
    for heading in list(dict.fromkeys([*new, *old])):
        label = heading or "Inleiding"
        if heading not in old:
            changes.append(
                SectionChange(
                    heading,
                    "added",
                    after=new[heading],
                    summary=f"{label}: toegevoegd.",
                )
            )
        elif heading not in new:
            changes.append(
                SectionChange(
                    heading,
                    "removed",
                    before=old[heading],
                    summary=f"{label}: vervallen.",
                )
            )
        elif old[heading] != new[heading]:
            a, b = old[heading].splitlines(), new[heading].splitlines()
            matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
            rewritten = added = dropped = 0
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "replace":
                    rewritten += max(i2 - i1, j2 - j1)
                elif tag == "insert":
                    added += sum(1 for line in b[j1:j2] if line.strip())
                elif tag == "delete":
                    dropped += sum(1 for line in a[i1:i2] if line.strip())
            parts = []
            if rewritten:
                unit = "alinea" if rewritten == 1 else "alinea's"
                parts.append(f"{rewritten} {unit} herschreven")
            if added:
                parts.append(f"{added} toegevoegd")
            if dropped:
                parts.append(f"{dropped} geschrapt")
            delta = _words(new[heading]) - _words(old[heading])
            if delta:
                parts.append(
                    f"{abs(delta)} woorden {'langer' if delta > 0 else 'korter'}"
                )
            changes.append(
                SectionChange(
                    heading,
                    "changed",
                    before=old[heading],
                    after=new[heading],
                    summary=f"{label}: " + (", ".join(parts) or "gewijzigd") + ".",
                )
            )
        else:
            changes.append(SectionChange(heading, "same"))
    return changes


# --- a tailored draft ---------------------------------------------------------


async def tailored_input(
    db: AsyncSession,
    vacancy: Vacancy,
    *,
    instruction: str | None = None,
    context: tuple[str, ...] = (),
) -> tuple[TailoredInput, library.Match]:
    """What a tailored draft is based on, and nothing else.

    From the standard text only the role's own sections go along as example;
    the shared ones are inserted afterwards, never generated. No rate, cost
    or name of a colleague is read here.
    """
    match = await library.find_template(db, vacancy)
    if match is None:
        raise DomainValidationError(
            "Er is geen standaardtekst om als voorbeeld te gebruiken. Voeg er "
            "een toe onder Standaardteksten, of schrijf de tekst zelf."
        )
    values = await library.values_for(db, vacancy)
    shared = {section.key: section for section in await library.shared_sections(db)}
    own = library.resolve(match.template, shared, values, only="own")
    outline = tuple(
        OutlineSection(
            key=section.key,
            heading=section.heading,
            words=max(40, round(_words(section.body) / 10) * 10),
        )
        for section in own.sections
    )
    examples = [StandardExample(role=match.template.role_name, text=own.text)]
    for other in await library.neighbours(
        db, match.template, MAX_STANDARD_EXAMPLES - 1
    ):
        examples.append(
            StandardExample(
                role=other.role_name,
                text=library.resolve(other, shared, values, only="own").text,
            )
        )
    client_name = None
    if vacancy.budget_line_id is not None:
        line = await db.get(BudgetLine, vacancy.budget_line_id)
        assignment = await db.get(Assignment, line.assignment_id) if line else None
        client_id = (
            getattr(assignment, "client_organisation_id", None) if assignment else None
        )
        if client_id is not None:
            client = await db.get(Organisation, client_id)
            client_name = client.name if client else None
    built = TailoredInput(
        role=vacancy.function_title,
        outline=outline,
        scale_band=f"schaal {vacancy.scale}" if vacancy.scale is not None else None,
        fte=vacancy.fte,
        period_start=vacancy.start_date,
        period_end=vacancy.end_date,
        contract_type=ContractType(vacancy.contract_type)
        if vacancy.contract_type
        else None,
        assignment_name=values.get(library.ASSIGNMENT_NAME),
        client_name=client_name,
        unit_name=values.get("eenheid"),
        context=tuple(context),
        instruction=(instruction or "").strip() or None,
        examples=tuple(examples),
    )
    return built, match


def assemble(
    template_sections: list[library.Section], generated: list[tuple[str, str]]
) -> str:
    """The drafted sections in the place of the role's own, the shared ones
    as they stand. A section the model left out keeps the standard text."""
    by_heading = {library._fold(heading): body for heading, body in generated if body}
    result = []
    for section in template_sections:
        if section.shared:
            result.append(section)
            continue
        drafted = by_heading.get(library._fold(section.heading or "Inleiding"))
        result.append(
            library.Section(
                section.key, section.heading, drafted or section.body, False
            )
        )
    return library.render(result)


async def draft_tailored(
    db: AsyncSession,
    vacancy: Vacancy,
    *,
    actor: Person,
    instruction: str | None = None,
    context: tuple[str, ...] = (),
    client: ChatClient | None = None,
) -> VacancyText:
    """Ask the model for a vacancy text for this vacancy, with the standard
    text of the role as example. The result is a draft: a proposal."""
    work = await _one(db, vacancy, TextKind.vacancy_text)
    if work.state == STATE_IN_REVIEW:
        raise DomainValidationError(
            "De vacaturetekst ligt ter beoordeling. Trek de beoordeling in om "
            "een nieuw concept te maken."
        )
    client = client or get_chat_client()
    try:
        built, match = await tailored_input(
            db, vacancy, instruction=instruction, context=context
        )
    except DraftInputError as exc:
        raise DomainValidationError(str(exc)) from exc
    names = await VacancyRepository(db).person_names()
    if find_person_names(built, names):  # type: ignore[arg-type]
        raise DomainValidationError(
            "In de gegevens voor het concept staat de naam van een persoon. "
            "Namen gaan niet naar het taalmodel; haal ze uit de aanwijzing of "
            "de standaardtekst en probeer het opnieuw."
        )
    system, user = build_tailored_prompt(built)
    answer = await client.complete(system=system, user=user, max_tokens=2500)
    shared = {section.key: section for section in await library.shared_sections(db)}
    values = await library.values_for(db, vacancy)
    # The shared sections keep their facts by key, like any draft.
    full = library.resolve(match.template, shared, values, keep_facts=True)
    text = VacancyText(
        vacancy_id=vacancy.id,
        kind=TextKind.vacancy_text.value,
        body=assemble(full.sections, parse_sections(answer)),
        source=TextSource.model.value,
        model_id=client.model_id,
        prompt_version=TAILORED_PROMPT_VERSION,
        based_on_id=None,
        template_label=library.template_label(match.template),
        created_by_id=actor.id,
    )
    db.add(text)
    await db.flush()
    _audit(
        db,
        actor,
        CREATE,
        "vacancy_text",
        text.id,
        vacancy.id,
        kind=text.kind,
        source=text.source,
        model_id=client.model_id,
        prompt_version=TAILORED_PROMPT_VERSION,
        example=text.template_label,
    )
    return text


# --- a proposal for one open place ---------------------------------------------


async def propose_passage(
    db: AsyncSession,
    vacancy: Vacancy,
    *,
    actor: Person,
    body: str,
    place: str,
    context: tuple[str, ...] = (),
    client: ChatClient | None = None,
) -> str:
    """Ask the model for the text of one open place in the vacancy text.

    ``body`` is the text as the writer has it now, ``place`` the open place
    as it stands in it. Nothing is stored: the writer takes the proposal over
    or not, and saves the text as their own.
    """
    if not place.startswith(library.OPEN_MARK) or body.count(place) < 1:
        raise DomainValidationError("Deze plek staat niet meer in de tekst.")
    facts = await library.facts_for(db, vacancy)
    values = await library.values_for(db, vacancy)
    asked = place[len(library.OPEN_MARK) :].strip(":] ").strip()
    marked = library.shown(body.replace(place, PASSAGE_MARK, 1), facts)
    try:
        built = PassageInput(
            role=vacancy.function_title,
            asked=asked,
            text=marked,
            scale_band=f"schaal {vacancy.scale}" if vacancy.scale is not None else None,
            fte=vacancy.fte,
            contract_type=ContractType(vacancy.contract_type)
            if vacancy.contract_type
            else None,
            assignment_name=values.get(library.ASSIGNMENT_NAME),
            unit_name=values.get("eenheid"),
            context=tuple(context),
        )
    except DraftInputError as exc:
        raise DomainValidationError(str(exc)) from exc
    names = await VacancyRepository(db).person_names()
    if find_person_names(built, names):  # type: ignore[arg-type]
        raise DomainValidationError(
            "In de tekst staat de naam van een persoon. Namen gaan niet naar "
            "het taalmodel; haal de naam weg en probeer het opnieuw."
        )
    client = client or get_chat_client()
    system, user = build_passage_prompt(built)
    answer = await client.complete(system=system, user=user, max_tokens=400)
    try:
        proposal = clean_passage(answer)
    except DraftInputError as exc:
        raise DomainValidationError(str(exc)) from exc
    # The saved version is the writer's own; that a model proposed a passage
    # is kept here.
    _audit(
        db,
        actor,
        UPDATE,
        "vacancy",
        vacancy.id,
        vacancy.id,
        text_passage_proposed=True,
        model_id=client.model_id,
        prompt_version=PASSAGE_PROMPT_VERSION,
    )
    return proposal


async def want_text(db: AsyncSession, vacancy: Vacancy, *, actor: Person) -> None:
    """Write a vacancy text for a vacancy that needs none by its kind. From
    here on the text is part of this vacancy's course."""
    if is_needed(vacancy, TextKind.vacancy_text.value):
        return
    vacancy.wants_text = True
    await db.flush()
    _audit(db, actor, UPDATE, "vacancy", vacancy.id, vacancy.id, wants_text=True)


# --- where the vacancy is published -------------------------------------------

PLACE_LABELS = {
    "internal": "de interne vacaturepagina",
    "government_wide": "Werken voor Nederland",
    "external": "een externe vacaturesite",
}


async def publications(db: AsyncSession, vacancy_id: UUID) -> list[VacancyPublication]:
    rows = await db.scalars(
        select(VacancyPublication)
        .where(VacancyPublication.vacancy_id == vacancy_id)
        .order_by(VacancyPublication.published_on, VacancyPublication.created_at)
    )
    return list(rows)


async def set_publication(
    db: AsyncSession,
    vacancy: Vacancy,
    *,
    actor: Person,
    place: str,
    url: str,
    published_on: date | None = None,
) -> VacancyPublication:
    """Record where the published vacancy can be read."""
    await stale.check(db, vacancy, "deze vacature")
    stale.touch(vacancy)
    if place not in PLACES:
        raise DomainValidationError("Kies waar de vacature staat.")
    url = url.strip()
    if not url.startswith("https://") or len(url) > 1000 or " " in url or len(url) < 12:
        raise DomainValidationError(
            "Geef het adres van de gepubliceerde vacature, beginnend met https://."
        )
    if vacancy.status not in (VacancyStatus.open.value, VacancyStatus.filled.value):
        raise DomainValidationError(
            "Een link naar de gepubliceerde vacature leg je vast als de vacature "
            "is opengesteld."
        )
    row = await db.scalar(
        select(VacancyPublication).where(
            VacancyPublication.vacancy_id == vacancy.id,
            VacancyPublication.place == place,
        )
    )
    day = published_on or clock.today()
    if row is None:
        row = VacancyPublication(
            vacancy_id=vacancy.id,
            place=place,
            url=url,
            published_on=day,
            recorded_by_id=actor.id,
        )
        db.add(row)
        action = CREATE
    else:
        row.url, row.published_on, row.recorded_by_id = url, day, actor.id
        action = UPDATE
    await db.flush()
    _audit(
        db,
        actor,
        action,
        "vacancy_publication",
        row.id,
        vacancy.id,
        place=place,
        url=url,
    )
    return row


async def remove_publication(
    db: AsyncSession, vacancy: Vacancy, publication_id: UUID, *, actor: Person
) -> None:
    row = await db.get(VacancyPublication, publication_id)
    if row is None or row.vacancy_id != vacancy.id:
        raise NotFoundError("Publicatie", publication_id)
    await db.delete(row)
    await db.flush()
    _audit(
        db,
        actor,
        DELETE,
        "vacancy_publication",
        publication_id,
        vacancy.id,
        place=row.place,
    )


def is_due(vacancy: Vacancy, kind: str) -> bool:
    """Whether the text still has to be written at this point.

    The motivation goes on the request form: it is due until the request is
    decided. The vacancy text is due until the vacancy is opened.
    """
    if not is_needed(vacancy, kind):
        return False
    if kind == TextKind.motivation.value:
        return vacancy.status in (
            VacancyStatus.draft.value,
            VacancyStatus.requested.value,
        )
    return vacancy.status in (
        VacancyStatus.draft.value,
        VacancyStatus.requested.value,
        VacancyStatus.approved.value,
    )
