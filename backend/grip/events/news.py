"""The feed of updates: what happened that this reader would want to know.

The audit log answers "what exactly changed, and who did it". This answers
"what did I miss", in a handful of sentences. It reads the same stream with
a different selection:

1. Only what is news. ``NEWS`` is the list, as data: decisions and
   transitions, each with a rank and with the functions that get it for the
   whole instance. Everything else is off, by kind (``OFF_KINDS``) or by
   type (``OFF_TYPES``). A test keeps the two lists total, so a new type
   can neither be forgotten nor flood the feed.
2. Only what concerns the reader: an assignment they own, manage or work
   on, a vacancy they asked for or decide on, a person they manage, and
   themselves. Some functions get the whole instance. Every item also
   passes the access model, exactly as the history does: the feed never
   shows what the reader could not open, and never a value.
3. Not what the reader did themselves.

A burst becomes one item ("3 maanden afgesloten op …"). Each item is one
Dutch sentence, written here so the wording lives in one place.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.relations import RelationSource
from grip.access.types import DataClass, Resource, ResourceKind, Subject
from grip.core import clock
from grip.events.reading import READ_TYPE, EventAccess
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.quote import Quote
from grip.models.stream_event import (
    ACTOR_GUEST,
    ACTOR_PEER,
    CASE_ASSIGNMENT,
    CASE_VACANCY,
    StreamEvent,
)
from grip.models.update_feed import UpdateFeedMarker
from grip.models.vacancy import Vacancy, VacancyDecision
from grip.services.reports.labels import MONTH_NAMES

BEHEERDER, PLANNER, LEZER = "beheerder", "planner", "lezer"
_ALL = frozenset({BEHEERDER, LEZER})
_MONEY = frozenset({BEHEERDER, LEZER})
_PEOPLE = frozenset({BEHEERDER, PLANNER})
_EVERY = frozenset({BEHEERDER, PLANNER, LEZER})
_ADMIN = frozenset({BEHEERDER})

_ZONE = ZoneInfo("Europe/Amsterdam")
# How many candidate events one request looks at.
SCAN_LIMIT = 800
MAX_ITEMS = 50
# Two steps on one quote this close together are one piece of news.
_TOGETHER = timedelta(hours=1)

Match = Callable[[StreamEvent], bool]


def _new(event: StreamEvent, name: str) -> Any:
    return (event.new_value or {}).get(name)


def _status(*values: str) -> Match:
    return lambda event: _new(event, "status") in values


def _decision(kind: str, agreed: bool) -> Match:
    return lambda event: _new(event, "kind") == kind and _new(event, "agreed") is agreed


@dataclass(frozen=True)
class News:
    key: str
    types: tuple[str, ...]
    # 1: a decision. 2: a transition. 3: good to know.
    rank: int
    # The functions that get this for the whole instance. Everyone else
    # gets it only for what they are part of.
    functions: frozenset[str]
    # The sentence. ``{object}`` is the assignment, vacancy or person and
    # becomes a link; ``{person}`` the person it is about; ``{detail}`` and
    # ``{ref}`` as the rule fills them.
    one: str
    # The sentence for a burst; ``{n}`` is how many.
    many: str
    match: Match | None = None
    # The tab of the assignment or vacancy where it is to be seen.
    tab: str = ""
    # Used instead of ``one`` when the reader may not know who.
    anonymous: str | None = None
    # Only for who manages the person, the person, and the functions.
    personal: bool = False
    # The assignment is the subject itself (an event without a case).
    object_is_subject: bool = False
    # A fixed place for something that is not a case or a person.
    href: str | None = None
    # The sentence when the reader is the person it is about.
    you: str | None = None
    # Whether the sentence ends with who did it.
    by: bool = True
    # On an assignment: only for who owns or manages it, not the team.
    managers_only: bool = False


NEWS: tuple[News, ...] = (
    # -- the quote ------------------------------------------------------
    News(
        "quote_signed",
        ("quote_acceptance.created",),
        1,
        _MONEY,
        "Offerte{ref} voor {object} is getekend",
        "{n} offertes voor {object} zijn getekend",
        tab="offerte",
    ),
    News(
        "quote_rejected",
        ("quote_rejection.created",),
        1,
        _MONEY,
        "Offerte{ref} voor {object} is afgewezen",
        "{n} offertes voor {object} zijn afgewezen",
        tab="offerte",
    ),
    News(
        "quote_made",
        ("quote.created",),
        2,
        _MONEY,
        "Offerte{ref} gemaakt voor {object}",
        "{n} offertes gemaakt voor {object}",
        tab="offerte",
        managers_only=True,
    ),
    News(
        "quote_offered",
        ("quote_offer.created",),
        2,
        _MONEY,
        "Offerte{ref} aangeboden voor {object}",
        "Offerte {n} keer aangeboden voor {object}",
        tab="offerte",
        managers_only=True,
    ),
    News(
        "quote_approval_asked",
        ("quote_approval.requested",),
        2,
        _MONEY,
        "De offerte voor {object} is ter goedkeuring aangeboden",
        "{n} keer goedkeuring gevraagd voor de offerte van {object}",
        tab="offerte",
        managers_only=True,
    ),
    News(
        "quote_approval_given",
        ("quote_approval.approved",),
        1,
        _MONEY,
        "De offerte voor {object} is intern goedgekeurd",
        "De offerte voor {object} is {n} keer intern goedgekeurd",
        tab="offerte",
        managers_only=True,
    ),
    News(
        "quote_approval_sent_back",
        ("quote_approval.sent_back",),
        1,
        _MONEY,
        "De offerte voor {object} is teruggestuurd naar de maker",
        "De offerte voor {object} is {n} keer teruggestuurd",
        tab="offerte",
        managers_only=True,
    ),
    # -- the assignment ---------------------------------------------------
    News(
        "assignment_requested",
        ("assignment_request.created",),
        1,
        _EVERY,
        "Aanvraag voor een offerte: {object}",
        "{n} aanvragen voor een offerte",
        by=False,
    ),
    News(
        "assignment_new",
        ("assignment.created",),
        3,
        _EVERY,
        "Nieuwe potentiële opdracht: {object}",
        "{n} nieuwe potentiële opdrachten",
        by=False,
    ),
    News(
        "assignment_started",
        ("assignment.updated",),
        2,
        _EVERY,
        "{object} is gestart",
        "{n} opdrachten zijn gestart",
        match=_status("in_progress"),
    ),
    News(
        "assignment_completed",
        ("assignment.updated",),
        2,
        _EVERY,
        "{object} is afgerond",
        "{n} opdrachten zijn afgerond",
        match=_status("completed"),
    ),
    News(
        "assignment_cancelled",
        ("assignment.updated",),
        1,
        _EVERY,
        "{object} is geannuleerd",
        "{n} opdrachten zijn geannuleerd",
        match=_status("cancelled"),
    ),
    News(
        "final_report",
        ("final_report.created",),
        2,
        _MONEY,
        "Eindrapport uitgebracht voor {object}",
        "{n} eindrapporten uitgebracht",
        object_is_subject=True,
        managers_only=True,
    ),
    News(
        "final_report_received",
        ("final_report_received.created",),
        1,
        _MONEY,
        "Eindrapport ontvangen voor {object}",
        "{n} eindrapporten ontvangen",
        object_is_subject=True,
    ),
    # -- months and money -------------------------------------------------
    News(
        "month_closed",
        ("month_close.created",),
        2,
        _MONEY,
        "{detail} afgesloten op {object}",
        "{n} maanden afgesloten op {object}",
        tab="maandafsluiting",
        managers_only=True,
    ),
    News(
        "billing_delivered",
        ("billing_export.created",),
        2,
        _MONEY,
        "Factuurgegevens van {detail} aangeleverd voor {object}",
        "Factuurgegevens van {n} maanden aangeleverd voor {object}",
        tab="maandafsluiting",
        managers_only=True,
    ),
    News(
        "invoiced",
        ("outgoing_invoice.created",),
        2,
        _MONEY,
        "Factuur vastgelegd voor {object}",
        "{n} facturen vastgelegd voor {object}",
        tab="financieel",
        managers_only=True,
    ),
    # -- the team ---------------------------------------------------------
    News(
        "joined",
        ("allocation.created",),
        3,
        _PEOPLE,
        "{person} is ingezet op {object}",
        "{n} mensen ingezet op {object}",
        anonymous="Er is iemand ingezet op {object}",
        you="Je bent ingezet op {object}",
        tab="bemensing",
    ),
    News(
        "left",
        ("allocation.deleted",),
        3,
        _PEOPLE,
        "{person} is van {object} af",
        "{n} mensen zijn van {object} af",
        anonymous="Er is iemand van {object} af",
        you="Je bent van {object} af",
        tab="bemensing",
    ),
    News(
        "scale",
        ("person_scale.created", "person_scale.updated"),
        3,
        _ADMIN,
        "{object} heeft een nieuwe schaal",
        "{n} mensen hebben een nieuwe schaal",
        personal=True,
        you="Je hebt een nieuwe schaal",
        by=False,
    ),
    News(
        "person_new",
        ("person.created",),
        3,
        _PEOPLE,
        "{object} is toegevoegd aan het team",
        "{n} mensen toegevoegd aan het team",
        personal=True,
        by=False,
    ),
    # -- vacancies --------------------------------------------------------
    News(
        "vacancy_requested",
        ("vacancy.updated",),
        2,
        _EVERY,
        "Vacature {object} is aangevraagd",
        "{n} vacatures aangevraagd",
        match=_status("requested"),
    ),
    News(
        "vacancy_open",
        ("vacancy.updated",),
        2,
        _EVERY,
        "Vacature {object} is opengesteld",
        "{n} vacatures opengesteld",
        match=_status("open"),
        tab="procedure",
    ),
    News(
        "vacancy_filled",
        ("vacancy.updated",),
        1,
        _EVERY,
        "Vacature {object} is vervuld",
        "{n} vacatures vervuld",
        match=_status("filled"),
        tab="vervulling",
    ),
    News(
        "vacancy_approved",
        ("vacancy_decision.created", "vacancy_decision.updated"),
        1,
        _EVERY,
        "Vacature {object} is goedgekeurd",
        "{n} vacatures goedgekeurd",
        match=_decision("approval", True),
        tab="advies",
    ),
    News(
        "vacancy_refused",
        ("vacancy_decision.created", "vacancy_decision.updated"),
        1,
        _EVERY,
        "Vacature {object} is niet goedgekeurd",
        "{n} vacatures niet goedgekeurd",
        match=_decision("approval", False),
        tab="advies",
    ),
    News(
        "vacancy_advice",
        ("vacancy_decision.created", "vacancy_decision.updated"),
        2,
        _EVERY,
        "Advies gegeven over vacature {object}",
        "{n} adviezen gegeven over vacature {object}",
        match=lambda event: _new(event, "kind") in ("hr_advice", "control_advice"),
        tab="advies",
    ),
    News(
        "vacancy_text_settled",
        ("vacancy_text.updated", "vacancy_text.created"),
        3,
        _PEOPLE,
        "De tekst van vacature {object} is vastgesteld",
        "{n} teksten van vacature {object} vastgesteld",
        match=lambda event: _new(event, "established") is True,
        tab="tekst",
    ),
    # -- the instance -----------------------------------------------------
    News(
        "rate_card_settled",
        ("rate_card.updated",),
        2,
        _EVERY,
        "Een tarievenkaart is vastgesteld",
        "{n} tarievenkaarten vastgesteld",
        match=_status("active"),
        href="/beheer/tarieven",
        by=False,
    ),
    News(
        "peer_connected",
        ("peer.created",),
        3,
        _ADMIN,
        "Er is een koppeling met een andere organisatie toegevoegd",
        "{n} koppelingen toegevoegd",
        href="/beheer/koppelingen",
        by=False,
    ),
)

# Kinds of which nothing is news: reads, logins, drafts, notes, settings,
# mail, bookkeeping of tasks, and parts of something that is news as a whole.
OFF_KINDS: frozenset[str] = frozenset(
    {
        "data",
        "stream",
        "login",
        "passkey_credential",
        "push_subscription",
        "notification_preference",
        "mail_outbox",
        "instance_setting",
        "task",
        "quote_draft",
        "quote_invitation",
        "decision_evidence",
        "budget_line",
        "budget_usage_requested",
        "assignment_role",
        "invoice_line",
        "invoice_attachment",
        "cost_item",
        "cost_coverage",
        "billing_correction",
        "billing_delivery",
        "billing_terms",
        "person_standing",
        "person_role",
        "person_roles",
        "colleague_proposal",
        "hire",
        "billability_target",
        "vacancy_step",
        "vacancy_recruitment_ref",
        "vacancy_offer_received",
        "vacancy_hire",
        "vacancy_publication",
        "vacancy_text_library",
        "vacancy_text_remark",
        "vacancy_text_review",
        "vacancy_text_shared_section",
        "vacancy_text_template",
        "rate_band",
        "scale_band",
        "organisation",
        "organisation_sync",
        "catalogue_role",
        "catalogue_role_sync",
        "function_framework",
        "function_family",
        "function_group",
        "form_template",
    }
)

# Types that are off although their kind has news: the same fact is told by
# another event, or it is a detail.
OFF_TYPES: frozenset[str] = frozenset(
    {
        # Told by the change record of the same fact.
        "quote.issued",
        "quote.offered",
        "quote.accepted",
        "quote.rejected",
        "assignment.status_changed",
        "final_report.issued",
        "vacancy.published",
        "invoice.recorded",
        "invoice.withdrawn",
        "person_scale.changed",
        "billing_correction.arose",
        "quote_approval.withdrawn",
        # Details and corrections.
        "assignment.deleted",
        "assignment_request.updated",
        "assignment_request.deleted",
        "quote.updated",
        "quote.deleted",
        "quote_offer.updated",
        "quote_offer.deleted",
        "quote_acceptance.updated",
        "quote_acceptance.deleted",
        "quote_rejection.updated",
        "quote_rejection.deleted",
        "quote_approval.created",
        "quote_approval.updated",
        "quote_approval.deleted",
        "final_report.updated",
        "final_report.deleted",
        "final_report_received.updated",
        "final_report_received.deleted",
        "month_close.updated",
        "month_close.deleted",
        "billing_export.updated",
        "billing_export.deleted",
        "outgoing_invoice.updated",
        "outgoing_invoice.deleted",
        "allocation.updated",
        "person.updated",
        "person.deleted",
        "person_scale.deleted",
        "vacancy.created",
        "vacancy.deleted",
        "vacancy_decision.deleted",
        "vacancy_text.deleted",
        "rate_card.created",
        "rate_card.deleted",
        "peer.updated",
        "peer.deleted",
    }
)

NEWS_TYPES: frozenset[str] = frozenset(t for rule in NEWS for t in rule.types)
_BY_TYPE: dict[str, list[News]] = {}
for _rule in NEWS:
    for _type in _rule.types:
        _BY_TYPE.setdefault(_type, []).append(_rule)

_COMBINED = News(
    "quote_made_offered",
    (),
    2,
    _MONEY,
    "Offerte{ref} gemaakt en aangeboden voor {object}",
    "{n} offertes gemaakt en aangeboden voor {object}",
    tab="offerte",
    managers_only=True,
)

_QUOTE_STEPS = frozenset(
    {
        "quote_made",
        "quote_offered",
        "quote_made_offered",
        "quote_approval_asked",
        "quote_approval_given",
    }
)
# News that says it all: on the same day about the same thing, the earlier
# steps towards it are left out.
SUPERSEDES: dict[str, frozenset[str]] = {
    "quote_signed": _QUOTE_STEPS | {"assignment_new"},
    "quote_rejected": _QUOTE_STEPS | {"assignment_new"},
    "quote_made_offered": frozenset({"quote_offered", "assignment_new"}),
    "quote_made": frozenset({"assignment_new"}),
    "assignment_started": frozenset({"assignment_new"}),
    "assignment_completed": frozenset({"assignment_started", "assignment_new"}),
    "assignment_cancelled": frozenset({"assignment_started", "assignment_new"}),
    "vacancy_approved": frozenset({"vacancy_advice", "vacancy_requested"}),
    "vacancy_refused": frozenset({"vacancy_advice", "vacancy_requested"}),
    "vacancy_open": frozenset({"vacancy_text_settled"}),
    "vacancy_filled": frozenset({"vacancy_open"}),
    "person_new": frozenset({"scale"}),
}
# Good-to-know news that reaches a reader only through a function, not
# through something they are part of, is dropped after this long.
_FUNCTION_NEWS_KEEPS = timedelta(days=2)


def is_decided(event_type: str) -> bool:
    """Whether a type is on the list of news or explicitly off it."""
    kind = event_type.partition(".")[0]
    return event_type in NEWS_TYPES or event_type in OFF_TYPES or kind in OFF_KINDS


def rule_for(event: StreamEvent) -> News | None:
    for rule in _BY_TYPE.get(event.type, ()):
        if rule.match is None or rule.match(event):
            return rule
    return None


# -- one piece of news, before it is put into words ----------------------------


@dataclass
class _Raw:
    rule: News
    event: StreamEvent
    object_kind: str | None  # assignment, vacancy, person
    object_id: UUID | None
    person_visible: bool
    detail_visible: bool
    seqs: list[int] = field(default_factory=list)
    actors: set[tuple[str, UUID | None]] = field(default_factory=set)
    count: int = 1
    # The reader is the person this is about.
    about_reader: bool = False
    # The reader may open the page of the object. News about the reader or
    # someone they lead can name an assignment that stays closed to them:
    # the name is theirs to know, a link to it would lead nowhere.
    openable: bool = True

    @property
    def target(self) -> UUID | None:
        """What supersedes what is decided per assignment, vacancy or person."""
        return self.event.person_id if self.rule.personal else self.object_id

    @property
    def top(self) -> int:
        return max(self.seqs)

    @property
    def day(self) -> Any:
        return clock.local_date(self.event.occurred_at)


@dataclass(frozen=True)
class Part:
    text: str
    href: str | None = None


@dataclass(frozen=True)
class Item:
    id: str
    seq: int
    kind: str
    rank: int
    when: datetime
    when_text: str
    day: str
    parts: tuple[Part, ...]
    text: str
    count: int
    new: bool


@dataclass
class Feed:
    items: list[Item] = field(default_factory=list)
    new_count: int = 0
    # Pass as ``na`` to read further back; None when there is nothing older.
    next_cursor: int | None = None


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


class _Relevance:
    """Whether an event concerns this reader, remembered for one request."""

    def __init__(
        self, db: AsyncSession, relations: RelationSource, subject: Subject
    ) -> None:
        self._db = db
        self._relations = relations
        self._subject = subject
        self._assignments: dict[UUID, bool] = {}
        self._vacancies: dict[UUID, bool] = {}
        self._persons: dict[UUID, bool] = {}

    async def _assignment(self, assignment_id: UUID) -> bool:
        if assignment_id not in self._assignments:
            me = self._subject.person_id
            assert me is not None
            self._assignments[assignment_id] = (
                await self._relations.assignment_role(me, assignment_id)
            ) is not None or await self._relations.is_member(
                me, assignment_id, clock.today()
            )
        return self._assignments[assignment_id]

    async def _vacancy(self, vacancy_id: UUID) -> bool:
        if vacancy_id not in self._vacancies:
            me = self._subject.person_id
            requester = await self._db.scalar(
                select(Vacancy.requester_id).where(Vacancy.id == vacancy_id)
            )
            named = await self._db.scalar(
                select(func.count())
                .select_from(VacancyDecision)
                .where(
                    VacancyDecision.vacancy_id == vacancy_id,
                    VacancyDecision.person_id == me,
                )
            )
            self._vacancies[vacancy_id] = requester == me or bool(named)
        return self._vacancies[vacancy_id]

    async def prepare(self, events: Iterable[StreamEvent]) -> None:
        """Read for every vacancy in a list of events whether the reader
        asked for it or is named in it, all at once."""
        me = self._subject.person_id
        wanted = {
            event.case_id
            for event in events
            if event.case_kind == CASE_VACANCY and event.case_id is not None
        } - set(self._vacancies)
        if not wanted:
            return
        mine = {
            row[0]
            for row in await self._db.execute(
                select(Vacancy.id).where(
                    Vacancy.id.in_(wanted), Vacancy.requester_id == me
                )
            )
        }
        mine |= {
            row[0]
            for row in await self._db.execute(
                select(VacancyDecision.vacancy_id).where(
                    VacancyDecision.vacancy_id.in_(wanted),
                    VacancyDecision.person_id == me,
                )
            )
        }
        for vacancy_id in wanted:
            self._vacancies[vacancy_id] = vacancy_id in mine

    async def _person(self, person_id: UUID) -> bool:
        if person_id not in self._persons:
            me = self._subject.person_id
            assert me is not None
            self._persons[person_id] = (
                person_id == me or await self._relations.is_line_manager(me, person_id)
            )
        return self._persons[person_id]

    async def _on_assignment(self, rule: News, assignment_id: UUID) -> bool:
        if rule.managers_only:
            me = self._subject.person_id
            assert me is not None
            return (
                await self._relations.assignment_role(me, assignment_id)
            ) is not None
        return await self._assignment(assignment_id)

    async def concerns(self, rule: News, event: StreamEvent) -> str | None:
        """``relation`` when the reader is part of it, ``function`` when a
        function gives the whole instance, None when it is not for them."""
        if event.person_id is not None and await self._person(event.person_id):
            return "relation"
        related = False
        if rule.personal:
            pass
        elif event.case_id is not None and event.case_kind == CASE_ASSIGNMENT:
            related = await self._on_assignment(rule, event.case_id)
        elif event.case_id is not None and event.case_kind == CASE_VACANCY:
            related = await self._vacancy(event.case_id)
        elif rule.object_is_subject:
            assignment_id = _uuid(event.subject_id)
            related = assignment_id is not None and await self._on_assignment(
                rule, assignment_id
            )
        if related:
            return "relation"
        return "function" if self._subject.functions & rule.functions else None


def _object_of(rule: News, event: StreamEvent) -> tuple[str | None, UUID | None]:
    if rule.object_is_subject:
        return "assignment", _uuid(event.subject_id)
    if rule.personal:
        return "person", event.person_id
    if event.case_id is not None:
        return event.case_kind, event.case_id
    return None, None


def _combine(raws: list[_Raw]) -> list[_Raw]:
    """A quote that was made and offered within the hour is one item."""
    made = {raw.event.subject_id: raw for raw in raws if raw.rule.key == "quote_made"}
    result: list[_Raw] = []
    used: set[int] = set()
    for raw in raws:
        if raw.rule.key != "quote_offered":
            continue
        first = made.get(str(_new(raw.event, "quote_id")))
        if (
            first is None
            or abs(raw.event.occurred_at - first.event.occurred_at) > _TOGETHER
        ):
            continue
        if id(first) in used:
            # Offered once more within the hour: still the one item.
            used.add(id(raw))
            continue
        used |= {id(first), id(raw)}
        result.append(
            _Raw(
                _COMBINED,
                raw.event,
                raw.object_kind,
                raw.object_id,
                False,
                raw.detail_visible and first.detail_visible,
                seqs=[*raw.seqs, *first.seqs],
                actors=raw.actors | first.actors,
            )
        )
    result += [raw for raw in raws if id(raw) not in used]
    return sorted(result, key=lambda raw: raw.top, reverse=True)


def _supersede(raws: list[_Raw]) -> list[_Raw]:
    """Leave out the steps towards news that says it all, and what a
    reader needs no telling about themselves."""
    said = {(raw.rule.key, raw.target, raw.day) for raw in raws}
    kept = []
    for raw in raws:
        if any(
            raw.rule.key in lesser and (key, raw.target, raw.day) in said
            for key, lesser in SUPERSEDES.items()
        ):
            continue
        if raw.about_reader and raw.rule.you is None and raw.rule.personal:
            # "You were added to the team" is no news to the one added.
            continue
        kept.append(raw)
    return kept


def _collapse(raws: list[_Raw]) -> list[_Raw]:
    """A burst of the same news about the same thing on one day is one item."""
    groups: dict[tuple[Any, ...], _Raw] = {}
    for raw in raws:
        # News without an object of its own, and news that names one object
        # per event (a new person), bursts per day as a whole.
        scope = None if raw.rule.personal else raw.object_id
        # What is about the reader is told to them on its own.
        key = (raw.rule.key, scope, raw.day, raw.about_reader)
        group = groups.get(key)
        if group is None:
            groups[key] = raw
        else:
            group.count += raw.count
            group.seqs += raw.seqs
            group.actors |= raw.actors
    return sorted(groups.values(), key=lambda raw: raw.top, reverse=True)


# -- words -------------------------------------------------------------------------


def _month(value: Any) -> str | None:
    text = str(value or "")
    try:
        year, month = int(text[:4]), int(text[5:7])
        return f"{MONTH_NAMES[month - 1].capitalize()} {year}"
    except (ValueError, IndexError):
        return None


def when_text(moment: datetime, now: datetime) -> str:
    """ "vanochtend", "gisteren", and after that the date."""
    local, today = moment.astimezone(_ZONE), clock.local_date(now)
    if local.date() == today:
        if local.hour < 12:
            return "vanochtend"
        return "vanmiddag" if local.hour < 18 else "vanavond"
    if local.date() == today - timedelta(days=1):
        return "gisteren"
    return f"{local.day} {MONTH_NAMES[local.month - 1]}"


def day_label(moment: datetime, now: datetime) -> str:
    local, today = clock.local_date(moment), clock.local_date(now)
    if local == today:
        return "Vandaag"
    if local == today - timedelta(days=1):
        return "Gisteren"
    text = f"{local.day} {MONTH_NAMES[local.month - 1]}"
    return text if local.year == today.year else f"{text} {local.year}"


_HREFS = {
    "assignment": "/opdrachten/{id}",
    "vacancy": "/vacatures/{id}",
    "person": "/team/{id}",
}


def _sentence(
    raw: _Raw,
    names: Mapping[tuple[str, UUID], str],
    people: Mapping[UUID, str],
    refs: Mapping[str, str],
) -> tuple[Part, ...]:
    rule, event = raw.rule, raw.event
    object_name = (
        names.get((raw.object_kind, raw.object_id))
        if raw.object_kind and raw.object_id
        else None
    )
    if raw.about_reader and rule.you:
        # Said to the reader, however often it happened that day.
        template = rule.you
    elif raw.count > 1:
        template = rule.many
        if raw.rule.personal or object_name is None:
            object_name = None
    else:
        template = rule.one
        if "{person}" in template:
            person = (
                people.get(event.person_id)
                if raw.person_visible and event.person_id
                else None
            )
            template = (
                template.replace("{person}", person)
                if person
                else (rule.anonymous or template.replace("{person}", "Iemand"))
            )
    reference = (
        refs.get(event.subject_id) or refs.get(str(_new(event, "quote_id")))
        if raw.detail_visible and raw.count == 1
        else None
    )
    detail = _month(_new(event, "month")) if raw.detail_visible else None
    fallback = {
        "assignment": "een opdracht",
        "vacancy": "een functie",
        "person": "Een collega",
    }.get(raw.object_kind or "", "")
    text = (
        template.replace("{n}", str(raw.count))
        .replace("{ref}", f" {reference}" if reference else "")
        .replace("{detail}", detail or "Een maand")
    )
    if "{object}" not in text:
        href = rule.href
        return (Part(text, href),) if href else (Part(text),)
    before, _, after = text.partition("{object}")
    href = None
    if object_name and raw.object_kind and raw.object_id and raw.openable:
        href = _HREFS[raw.object_kind].format(id=raw.object_id)
        if rule.tab and raw.object_kind != "person":
            href += f"/{rule.tab}"
    label = object_name or fallback
    if not before and label:
        label = label[0].upper() + label[1:]
    parts = [Part(before), Part(label, href), Part(after)]
    if rule.by and len(raw.actors) == 1:
        ((kind, person_id),) = raw.actors
        by = (
            people.get(person_id)
            if person_id
            else {
                ACTOR_PEER: "een andere organisatie",
                ACTOR_GUEST: "de opdrachtgever",
            }.get(kind)
        )
        if by and by != object_name and person_id != event.person_id:
            parts.append(Part(f" door {by}"))
    return tuple(part for part in parts if part.text)


async def _names(
    db: AsyncSession, raws: Sequence[_Raw]
) -> tuple[dict[tuple[str, UUID], str], dict[UUID, str], dict[str, str]]:
    wanted: dict[str, set[UUID]] = {
        "assignment": set(),
        "vacancy": set(),
        "person": set(),
    }
    quotes: set[UUID] = set()
    for raw in raws:
        if raw.object_kind in wanted and raw.object_id:
            wanted[raw.object_kind].add(raw.object_id)
        if raw.person_visible and raw.event.person_id:
            wanted["person"].add(raw.event.person_id)
        wanted["person"] |= {person for _kind, person in raw.actors if person}
        for candidate in (raw.event.subject_id, _new(raw.event, "quote_id")):
            quote_id = _uuid(candidate)
            if quote_id and raw.rule.key.startswith("quote"):
                quotes.add(quote_id)
    names: dict[tuple[str, UUID], str] = {}
    people: dict[UUID, str] = {}
    refs: dict[str, str] = {}
    if wanted["assignment"]:
        rows = await db.execute(
            select(Assignment.id, Assignment.name).where(
                Assignment.id.in_(wanted["assignment"])
            )
        )
        names |= {("assignment", row[0]): row[1] for row in rows}
    if wanted["vacancy"]:
        rows = await db.execute(
            select(Vacancy.id, Vacancy.function_title).where(
                Vacancy.id.in_(wanted["vacancy"])
            )
        )
        names |= {("vacancy", row[0]): row[1] for row in rows}
    if wanted["person"]:
        rows = await db.execute(
            select(Person.id, Person.name).where(Person.id.in_(wanted["person"]))
        )
        people = {row[0]: row[1] for row in rows}
        names |= {("person", person_id): name for person_id, name in people.items()}
    if quotes:
        rows = await db.execute(
            select(Quote.id, Quote.reference).where(Quote.id.in_(quotes))
        )
        refs = {str(row[0]): row[1] for row in rows if row[1]}
    return names, people, refs


# -- the feed ------------------------------------------------------------------------


async def _openable(
    access: EventAccess, object_kind: str | None, object_id: UUID | None
) -> bool:
    """Whether the reader can open the assignment a piece of news names."""
    if object_kind != "assignment" or object_id is None:
        return True
    resource = Resource(ResourceKind.ASSIGNMENT, id=object_id, assignment_id=object_id)
    return await access.may(resource, DataClass.ASSIGNMENT_BASIC)


async def seen_seq(db: AsyncSession, person_id: UUID) -> int | None:
    return await db.scalar(
        select(UpdateFeedMarker.seen_seq).where(UpdateFeedMarker.person_id == person_id)
    )


async def mark_seen(db: AsyncSession, person_id: UUID) -> int:
    """The reader has seen the feed up to the head of the stream."""
    head = await db.scalar(select(func.coalesce(func.max(StreamEvent.seq), 0))) or 0
    await db.execute(
        pg_insert(UpdateFeedMarker)
        .values(person_id=person_id, seen_seq=head)
        .on_conflict_do_update(
            index_elements=["person_id"],
            set_={"seen_seq": head, "seen_at": func.now()},
        )
    )
    return head


async def read(
    db: AsyncSession,
    access: EventAccess,
    relations: RelationSource,
    *,
    cursor: int | None = None,
    limit: int = 10,
    now: datetime | None = None,
) -> Feed:
    """The news for this reader, newest first, bursts as one item."""
    subject = access.subject
    if subject.person_id is None:
        return Feed()
    now = now or datetime.now(UTC)
    limit = max(1, min(limit, MAX_ITEMS))
    query = (
        select(StreamEvent)
        .where(
            StreamEvent.type.in_(NEWS_TYPES),
            # News is never a read; said as a literal, so the index on the
            # changes serves this and the newest are found without sorting.
            StreamEvent.type != literal(READ_TYPE, literal_execute=True),
            # What the reader did themselves is not news to them.
            StreamEvent.actor_person_id.is_distinct_from(subject.person_id),
        )
        .order_by(StreamEvent.seq.desc())
        .limit(SCAN_LIMIT + 1)
    )
    # Always read from the head: what is one item, and what later news makes
    # superfluous, must not depend on where a page happens to start. The
    # cursor then cuts the list of items.
    rows = (await db.scalars(query)).all()[:SCAN_LIMIT]

    relevance = _Relevance(db, relations, subject)
    await relevance.prepare(rows)
    await access.prepare(rows)
    raws: list[_Raw] = []
    for event in rows:
        rule = rule_for(event)
        if rule is None:
            continue
        how = await relevance.concerns(rule, event)
        if how is None:
            continue
        if (
            how == "function"
            and rule.rank >= 3
            and now - event.occurred_at > _FUNCTION_NEWS_KEEPS
        ):
            continue
        # Never what the reader could not open.
        if not await access.may_know(event):
            continue
        object_kind, object_id = _object_of(rule, event)
        sees_person = await access.may_see_person(event)
        if rule.personal and not sees_person:
            continue
        _changes, details = await access.changes(event)
        raws.append(
            _Raw(
                rule,
                event,
                object_kind,
                object_id,
                sees_person,
                details,
                seqs=[event.seq],
                actors={(event.actor_kind, event.actor_person_id)},
                about_reader=event.person_id == subject.person_id,
                openable=await _openable(access, object_kind, object_id),
            )
        )

    collapsed = _collapse(_supersede(_combine(raws)))
    marker = await seen_seq(db, subject.person_id)
    feed = Feed(
        new_count=sum(1 for raw in collapsed if marker is not None and raw.top > marker)
        if cursor is None
        else 0
    )
    if cursor is not None:
        collapsed = [raw for raw in collapsed if raw.top < cursor]
    shown = collapsed[:limit]
    names, people, refs = await _names(db, shown)
    for raw in shown:
        parts = _sentence(raw, names, people, refs)
        feed.items.append(
            Item(
                id=str(raw.top),
                seq=raw.top,
                kind=raw.rule.key,
                rank=raw.rule.rank,
                when=raw.event.occurred_at,
                when_text=when_text(raw.event.occurred_at, now),
                day=day_label(raw.event.occurred_at, now),
                parts=parts,
                text="".join(part.text for part in parts),
                count=raw.count,
                new=marker is not None and raw.top > marker,
            )
        )
    if len(collapsed) > limit:
        # Read on below the last item shown.
        feed.next_cursor = shown[-1].top
    return feed
