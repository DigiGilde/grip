"""The stream as an audit log for people, through the access model.

Every event is decided on its own: whether the reader may know that it
happened (the existence class), and per field whether the value may be
seen. A reader who may know of a change but not see its values gets the
names of the changed fields and nothing else. There is no way to count
what stays hidden: a page is cut from what the reader may see, and no
total is given.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.access.decider import Decider, decide
from grip.access.types import Action, DataClass, Resource, ResourceKind, Subject
from grip.access.vacancies import vacancy_resource
from grip.events import words
from grip.events.classification import DEFAULT, class_from, class_of_field, spec_for
from grip.models.assignment import BudgetLine
from grip.models.person import Person
from grip.models.stream_event import CASE_ASSIGNMENT, CASE_VACANCY, StreamEvent
from grip.models.vacancy import Vacancy

# How many rows one request reads at most while looking for a full page.
# A reader who may see little gets a short page and a cursor to go on.
SCAN_LIMIT = 2000
_CHUNK = 200
MAX_PAGE = 200

KIND_CHANGES = "changes"
KIND_READS = "reads"
KIND_ALL = "all"
KINDS = (KIND_CHANGES, KIND_READS, KIND_ALL)
READ_TYPE = "data.read"


@dataclass(frozen=True)
class Filters:
    case_kind: str | None = None
    case_id: UUID | None = None
    # Events about this person's data.
    person_id: UUID | None = None
    # Events this person caused.
    actor_person_id: UUID | None = None
    # A type, or a prefix ending in a dot ("quote.").
    types: Sequence[str] = ()
    subject_kind: str | None = None
    subject_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    correlation_id: str | None = None
    # Changes (everything except reads of data), reads, or all. Reads
    # outnumber changes by far, so a reader asks for one or the other.
    kind: str = KIND_ALL


@dataclass(frozen=True)
class Change:
    field: str
    # False: the reader may know this field changed, not its values.
    visible: bool
    old: Any = None
    new: Any = None
    # The Dutch name of the field, when it has one.
    label: str | None = None


@dataclass(frozen=True)
class EventView:
    seq: int
    id: UUID
    occurred_at: datetime
    type: str
    action: str | None
    subject_kind: str
    # None when the id itself would tell whose data this is.
    subject_id: str | None
    case_kind: str | None
    case_id: UUID | None
    actor_kind: str
    actor_person_id: UUID | None
    actor_name: str | None
    actor_ref: str | None
    origin: str
    origin_peer: str | None
    correlation_id: str
    purpose: str | None
    person_id: UUID | None
    person_name: str | None
    changes: tuple[Change, ...]
    # The event in Dutch, as this reader may see it: what happened, and the
    # change in words. A screen shows these and never a code name.
    title: str
    lines: tuple[str, ...]
    # The payload, the note and the references, when the reader may see
    # the values of this event.
    details_visible: bool
    payload: dict[str, Any] | None
    note: str | None
    refs: dict[str, Any] | None
    erased: bool


@dataclass
class Page:
    events: list[EventView] = field(default_factory=list)
    # Pass as ``before`` to read on; None when the stream is exhausted.
    next_before: int | None = None


class EventAccess:
    """The answers of the access model about events, kept for one request."""

    def __init__(self, db: AsyncSession, decider: Decider, subject: Subject) -> None:
        self._db = db
        self._decider = decider
        self.subject = subject
        self._answers: dict[tuple[Resource, DataClass | None], bool] = {}
        self._vacancies: dict[UUID, Resource | None] = {}

    async def _vacancy(self, vacancy_id: UUID) -> Resource | None:
        if vacancy_id not in self._vacancies:
            vacancy = (
                await self._db.scalars(
                    select(Vacancy)
                    .where(Vacancy.id == vacancy_id)
                    .options(selectinload(Vacancy.decisions))
                )
            ).first()
            resource = None
            if vacancy is not None:
                assignment_id = None
                if vacancy.budget_line_id is not None:
                    assignment_id = await self._db.scalar(
                        select(BudgetLine.assignment_id).where(
                            BudgetLine.id == vacancy.budget_line_id
                        )
                    )
                resource = vacancy_resource(
                    vacancy.id,
                    assignment_id=assignment_id,
                    named={d.kind: d.person_id for d in vacancy.decisions},
                )
            self._vacancies[vacancy_id] = resource
        return self._vacancies[vacancy_id]

    async def resource_of(self, event: StreamEvent) -> Resource | None:
        """What the access model is asked about; None when nothing can be."""
        if event.case_kind == CASE_VACANCY and event.case_id is not None:
            # A vacancy that is gone has no relations left to decide on.
            return await self._vacancy(event.case_id)
        if event.case_kind == CASE_ASSIGNMENT and event.case_id is not None:
            return Resource(
                ResourceKind.ASSIGNMENT,
                id=event.case_id,
                assignment_id=event.case_id,
                person_id=event.person_id,
            )
        if event.person_id is not None:
            return Resource.person(event.person_id)
        kind = spec_for(event.subject_kind).resource
        if kind is ResourceKind.ASSIGNMENT:
            return Resource.assignment(None)
        if kind is ResourceKind.COST_ITEM:
            return Resource.cost_item(None)
        if kind is ResourceKind.PERSON:
            return Resource.person(None)
        return Resource.instance()

    async def may(
        self, resource: Resource | None, data_class: DataClass | None
    ) -> bool:
        """Whether the reader may read this class on this resource.

        ``None`` as class is administration of the instance.
        """
        if resource is None:
            resource, data_class = Resource.instance(), None
        key = (resource, data_class)
        if key not in self._answers:
            if data_class is None:
                decision = await decide(
                    self._decider,
                    self.subject,
                    Action.MANAGE_USERS,
                    Resource.instance(),
                )
            else:
                decision = await decide(
                    self._decider, self.subject, Action.READ, resource, data_class
                )
            self._answers[key] = decision.allowed
        return self._answers[key]

    async def may_know(self, event: StreamEvent) -> bool:
        resource = await self.resource_of(event)
        return await self.may(resource, class_from(event.existence_class))

    async def may_see_person(self, event: StreamEvent) -> bool:
        """Whether the reader may know whose data the event is about."""
        if event.person_id is None:
            return False
        if event.person_id == self.subject.person_id:
            return True
        resource = await self.resource_of(event)
        if resource is None:
            return await self.may(None, None)
        roster = (
            DataClass.STAFFING
            if resource.kind is ResourceKind.VACANCY
            else DataClass.STAFFING_ROSTER
        )
        return await self.may(resource, roster)

    async def changes(self, event: StreamEvent) -> tuple[tuple[Change, ...], bool]:
        """The changed fields as this reader may see them, and whether the
        payload, note and references may be seen."""
        resource = await self.resource_of(event)
        classes = event.field_classes or {}
        old, new = event.old_value or {}, event.new_value or {}
        result = []
        for name in dict.fromkeys([*old, *new]):
            visible = await self.may(resource, class_of_field(classes, name))
            label = words.FIELD_LABELS.get(name)
            result.append(
                Change(name, True, old.get(name), new.get(name), label)
                if visible
                else Change(name, False, label=label)
            )
        details = await self.may(resource, class_of_field(classes, DEFAULT))
        return tuple(result), details


def _query(filters: Filters) -> Any:
    query = select(StreamEvent)
    if filters.kind == KIND_CHANGES:
        query = query.where(StreamEvent.type != READ_TYPE)
    elif filters.kind == KIND_READS:
        query = query.where(StreamEvent.type == READ_TYPE)
    if filters.case_kind is not None:
        query = query.where(StreamEvent.case_kind == filters.case_kind)
    if filters.case_id is not None:
        query = query.where(StreamEvent.case_id == filters.case_id)
    if filters.person_id is not None:
        query = query.where(StreamEvent.person_id == filters.person_id)
    if filters.actor_person_id is not None:
        query = query.where(StreamEvent.actor_person_id == filters.actor_person_id)
    if filters.types:
        query = query.where(
            or_(
                *(
                    StreamEvent.type.startswith(t, autoescape=True)
                    if t.endswith(".")
                    else StreamEvent.type == t
                    for t in filters.types
                )
            )
        )
    if filters.subject_kind is not None:
        query = query.where(StreamEvent.subject_kind == filters.subject_kind)
    if filters.subject_id is not None:
        query = query.where(StreamEvent.subject_id == filters.subject_id)
    if filters.since is not None:
        query = query.where(StreamEvent.occurred_at >= filters.since)
    if filters.until is not None:
        query = query.where(StreamEvent.occurred_at < filters.until)
    if filters.correlation_id is not None:
        query = query.where(StreamEvent.correlation_id == filters.correlation_id)
    return query


async def _names(db: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    rows = await db.execute(select(Person.id, Person.name).where(Person.id.in_(ids)))
    return {row[0]: row[1] for row in rows}


async def read(
    db: AsyncSession,
    access: EventAccess,
    filters: Filters,
    *,
    before: int | None = None,
    limit: int = 50,
) -> Page:
    """A page of events the reader may know of, newest first."""
    limit = max(1, min(limit, MAX_PAGE))
    base = _query(filters).order_by(StreamEvent.seq.desc())
    shown: list[tuple[StreamEvent, tuple[Change, ...], bool, bool]] = []
    cursor, scanned, exhausted = before, 0, False
    while len(shown) < limit and scanned < SCAN_LIMIT and not exhausted:
        query = base.limit(_CHUNK)
        if cursor is not None:
            query = query.where(StreamEvent.seq < cursor)
        rows = (await db.scalars(query)).all()
        exhausted = len(rows) < _CHUNK
        for event in rows:
            scanned += 1
            cursor = event.seq
            if not await access.may_know(event):
                continue
            sees_person = await access.may_see_person(event)
            if filters.person_id is not None and not sees_person:
                # Showing it would tell whose data it is about.
                continue
            changes, details = await access.changes(event)
            shown.append((event, changes, details, sees_person))
            if len(shown) >= limit:
                exhausted = False
                break
    ids = {e.actor_person_id for e, *_ in shown if e.actor_person_id}
    ids |= {e.person_id for e, _c, _d, sees in shown if sees and e.person_id}
    names = await _names(db, ids)
    page = Page(next_before=None if exhausted else cursor)
    for event, changes, details, sees_person in shown:
        page.events.append(
            EventView(
                seq=event.seq,
                id=event.id,
                occurred_at=event.occurred_at,
                type=event.type,
                action=event.action,
                subject_kind=event.subject_kind,
                subject_id=None
                if event.person_id is not None
                and not sees_person
                and event.subject_id == str(event.person_id)
                else event.subject_id,
                case_kind=event.case_kind,
                case_id=event.case_id,
                actor_kind=event.actor_kind,
                actor_person_id=event.actor_person_id,
                actor_name=names.get(event.actor_person_id)
                if event.actor_person_id
                else None,
                actor_ref=event.actor_ref if details else None,
                origin=event.origin,
                origin_peer=event.origin_peer,
                correlation_id=event.correlation_id,
                purpose=event.purpose,
                person_id=event.person_id if sees_person else None,
                person_name=names.get(event.person_id)
                if sees_person and event.person_id
                else None,
                changes=changes,
                title=words.title(
                    event.type,
                    event.subject_kind,
                    names.get(event.person_id)
                    if sees_person and event.person_id
                    else None,
                ),
                lines=tuple(
                    words.lines(
                        event.type,
                        event.subject_kind,
                        changes,
                        payload=event.payload if details else None,
                        note=event.note if details else None,
                        erased=event.erased_at is not None,
                    )
                ),
                details_visible=details,
                payload=event.payload if details else None,
                note=event.note if details else None,
                refs=event.refs if details else None,
                erased=event.erased_at is not None,
            )
        )
    return page
