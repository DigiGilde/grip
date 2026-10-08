"""The one way to write an event, and the handlers that react to it.

``append`` adds an event to the session; it is written in the transaction
of the change it describes and commits or rolls back with it. ``record``
does the same and then calls the handlers.

There are two kinds of handler:

- A transactional handler runs in the transaction of the event, with its
  session. What it writes (a message in the outbox, a mark that tasks must
  be looked at again) commits or rolls back with the event, and when it
  raises it refuses the change. It must touch nothing outside the database.
- An after-commit handler runs once the transaction is durable, and never
  for one that rolled back. This is the place for anything with an effect
  outside the database.

The position in the stream, the hash chain and everything the caller left
out (actor, origin, correlation id, case, data classes) are filled in when
the session flushes, under a lock that makes the order of the stream the
order in which transactions commit.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import secrets
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import event as sa_event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.orm.util import identity_key

from grip.core.database import Base
from grip.events import chain, context
from grip.events.classification import TYPE_SUBJECTS, classify
from grip.models.stream_event import (
    ACTOR_PERSON,
    ACTOR_SYSTEM,
    CASE_ASSIGNMENT,
    CASE_VACANCY,
    ORIGIN_LOCAL,
    AuditLog,
    StreamEvent,
)

logger = logging.getLogger(__name__)

# One lock for the head of the stream (an arbitrary, fixed number).
_LOCK_KEY = 4_771_001

_VERBS = {"create": "created", "update": "updated", "delete": "deleted"}

# Where the id of the subject of a domain event is found in its payload.
_SUBJECT_KEYS = (
    "{kind}_id",
    "approval_id",
    "invoice_id",
    "request_id",
    "assignment_id",
    "vacancy_id",
    "person_id",
)

# Hashes in a payload that point at evidence kept elsewhere.
_REF_KEYS = ("statement_hash", "quote_hash", "snapshot_hash", "document_sha256")

TransactionalHandler = Callable[[AsyncSession, StreamEvent], Awaitable[None]]
AfterCommitHandler = Callable[[StreamEvent], Awaitable[None]]

ANY = "*"

_transactional: dict[str, list[TransactionalHandler]] = defaultdict(list)
_after_commit: dict[str, list[AfterCommitHandler]] = defaultdict(list)
_order = itertools.count()
_running: set[asyncio.Task[None]] = set()

_PENDING = "grip_events_pending"
_CORRELATION = "grip_events_correlation"
_COUNT = "grip_events_count"
# The subject kinds of the events a session wrote, in order.
KINDS_WRITTEN = "grip_events_kinds"


# -- handlers ---------------------------------------------------------------


def on_event(event_type: str, handler: TransactionalHandler) -> None:
    """Run ``handler`` in the transaction of every event of this type."""
    if handler not in _transactional[event_type]:
        _transactional[event_type].append(handler)


def after_commit(event_type: str, handler: AfterCommitHandler) -> None:
    """Run ``handler`` after an event of this type is durable. ``*`` is all."""
    if handler not in _after_commit[event_type]:
        _after_commit[event_type].append(handler)


def remove_handler(event_type: str, handler: Callable[..., Any]) -> None:
    for registry in (_transactional, _after_commit):
        if handler in registry[event_type]:
            registry[event_type].remove(handler)


def clear_handlers() -> None:
    """Remove every handler. For tests."""
    _transactional.clear()
    _after_commit.clear()


# -- writing ----------------------------------------------------------------


def _uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _subject_from_payload(
    event_type: str, payload: Mapping[str, Any]
) -> tuple[str, str]:
    kind = TYPE_SUBJECTS.get(event_type, event_type.split(".", 1)[0])
    for key in _SUBJECT_KEYS:
        value = payload.get(key.format(kind=kind))
        if value:
            return kind, str(value)
    return kind, "-"


def append(
    session: AsyncSession | Session,
    event_type: str | None = None,
    *,
    subject: tuple[str, UUID | str] | None = None,
    action: str | None = None,
    actor_person_id: UUID | None = None,
    assignment_id: UUID | str | None = None,
    vacancy_id: UUID | str | None = None,
    person_id: UUID | str | None = None,
    old: Mapping[str, Any] | None = None,
    new: Mapping[str, Any] | None = None,
    payload: Mapping[str, Any] | None = None,
    note: str | None = None,
    refs: Mapping[str, Any] | None = None,
    purpose: str | None = None,
    existence_class: str | None = None,
    field_classes: Mapping[str, str | None] | None = None,
) -> StreamEvent:
    """Add an event to the transaction of ``session``. Does not flush.

    ``subject`` is the kind and id of the thing the event is about. A plain
    change record gives ``action`` and no type; its type becomes
    ``<kind>.created``, ``.updated`` or ``.deleted``. Pass ``assignment_id``,
    ``vacancy_id`` and ``person_id`` when known; otherwise they are looked
    up from the values and the subject when the event is written.
    """
    if subject is None:
        if event_type is None or payload is None:
            raise ValueError("an event needs a subject, or a type and a payload")
        subject = _subject_from_payload(event_type, payload)
    kind, subject_id = subject[0], str(subject[1])
    if event_type is None:
        if action is None:
            raise ValueError("an event needs a type or an action")
        event_type = f"{kind}.{_VERBS.get(action, action)}"
    event = (AuditLog if action is not None else StreamEvent)(
        id=uuid4(),
        type=event_type,
        action=action,
        subject_kind=kind,
        subject_id=subject_id,
        actor_person_id=actor_person_id,
        old_value=chain.plain(old) if old is not None else None,
        new_value=chain.plain(new) if new is not None else None,
        payload=chain.plain(payload) if payload is not None else None,
        note=note,
        refs=chain.plain(refs) if refs is not None else None,
        purpose=purpose,
    )
    if existence_class is not None or field_classes is not None:
        event.existence_class = existence_class
        event.field_classes = dict(field_classes or {})
    if vacancy_id is not None:
        event.case_kind, event.case_id = CASE_VACANCY, _uuid(vacancy_id)
    elif assignment_id is not None:
        event.case_kind, event.case_id = CASE_ASSIGNMENT, _uuid(assignment_id)
    event.person_id = _uuid(person_id)
    session.add(event)
    return event


async def record(
    session: AsyncSession, event_type: str | None = None, **fields: Any
) -> StreamEvent:
    """Write an event and call the transactional handlers of its type.

    A handler that raises aborts the change the event belongs to: an event
    that cannot be handled must not be lost silently.
    """
    event = append(session, event_type, **fields)
    # Handlers get the payload as the caller gave it, not its stored form.
    event._raw_payload = fields.get("payload")  # type: ignore[attr-defined]
    for handler in [*_transactional[event.type], *_transactional[ANY]]:
        await handler(session, event)
    return event


# -- sealing: position, chain and everything the caller left out -------------

_tables: dict[str, type] | None = None


def _model_of(kind: str) -> type | None:
    global _tables
    if _tables is None:
        _tables = {
            mapper.local_table.name: mapper.class_
            for mapper in Base.registry.mappers
            if getattr(mapper.local_table, "name", None)
        }
    return _tables.get(kind)


# A row that belongs to a case through another row.
_LINKS = (
    ("budget_line_id", "budget_line"),
    ("quote_id", "quote"),
    ("allocation_id", "allocation"),
    ("vacancy_id", "vacancy"),
    ("month_close_id", "month_close"),
    ("outgoing_invoice_id", "outgoing_invoice"),
    ("invoice_id", "outgoing_invoice"),
)


def _load(session: Session, kind: str, key: Any) -> Any:
    model, row_id = _model_of(kind), _uuid(key)
    if model is None or row_id is None:
        return None
    try:
        primary = sa_inspect(model).primary_key
        if len(primary) != 1 or primary[0].type.python_type is not UUID:
            return None
        return session.get(model, row_id)
    except Exception:  # never let a lookup stand in the way of the record
        logger.debug("no %s with id %s", kind, key, exc_info=True)
        return None


def _facts(source: Any) -> dict[str, Any]:
    """assignment_id, vacancy_id, person_id and links, from a row or a dict."""
    names = ("assignment_id", "vacancy_id", "person_id", *(n for n, _ in _LINKS))
    if isinstance(source, Mapping):
        return {name: source[name] for name in names if source.get(name)}
    return {
        name: value
        for name in names
        if (value := getattr(source, name, None)) is not None
    }


def _resolve(session: Session, event: StreamEvent) -> None:
    """Find the case and the person of an event that did not name them."""
    kind, subject_id = event.subject_kind, event.subject_id
    found: dict[str, Any] = {}
    for values in (event.new_value, event.old_value, event.payload):
        for name, value in _facts(values or {}).items():
            found.setdefault(name, value)
    if kind == "assignment":
        found.setdefault("assignment_id", subject_id)
    elif kind == "vacancy":
        found.setdefault("vacancy_id", subject_id)
    elif kind == "person":
        found.setdefault("person_id", subject_id)
    else:
        row = _load(session, kind, subject_id)
        if row is not None:
            for name, value in _facts(row).items():
                found.setdefault(name, value)
        elif kind.startswith("person") and "person_id" not in found:
            # Some records about a person carry the person's id as their own.
            if _load(session, "person", subject_id) is not None:
                found["person_id"] = subject_id
    # Follow one link at a time until a case turns up.
    followed: set[str] = set()
    for _ in range(4):
        if "assignment_id" in found:
            break
        name, linked_kind = next(
            (link for link in _LINKS if link[0] in found and link[0] not in followed),
            (None, None),
        )
        if name is None or linked_kind is None:
            break
        followed.add(name)
        row = _load(session, linked_kind, found[name])
        if row is not None:
            for key, value in _facts(row).items():
                found.setdefault(key, value)
    if event.case_id is None:
        # A vacancy is the case of what is done on it, even when it hangs
        # on a budget line of an assignment.
        if found.get("vacancy_id") and kind.startswith("vacancy"):
            event.case_kind = CASE_VACANCY
            event.case_id = _uuid(found["vacancy_id"])
        elif found.get("assignment_id"):
            event.case_kind = CASE_ASSIGNMENT
            event.case_id = _uuid(found["assignment_id"])
        elif found.get("vacancy_id"):
            event.case_kind = CASE_VACANCY
            event.case_id = _uuid(found["vacancy_id"])
        if event.case_id is None:
            event.case_kind = None
    if event.person_id is None:
        event.person_id = _uuid(found.get("person_id"))


def _complete(session: Session, event: StreamEvent) -> None:
    current = context.current()
    if event.type is None:
        # A change record made without ``append``.
        verb = _VERBS.get(event.action or "", event.action or "changed")
        event.type = f"{event.subject_kind}.{verb}"
    if event.actor_kind is None:
        if event.actor_person_id is not None:
            event.actor_kind = ACTOR_PERSON
        elif current.actor_kind is not None:
            event.actor_kind = current.actor_kind
            event.actor_person_id = current.actor_person_id
            event.actor_ref = current.actor_ref
        else:
            event.actor_kind = ACTOR_SYSTEM
    if event.actor_kind == ACTOR_SYSTEM and event.actor_ref is None:
        event.actor_ref = current.actor_ref or "system"
    if event.origin is None:
        payload_origin = (event.payload or {}).get("origin")
        event.origin = (
            payload_origin
            if payload_origin in ("local", "remote")
            else current.origin or ORIGIN_LOCAL
        )
        if event.origin_peer is None:
            event.origin_peer = current.origin_peer
    if event.purpose is None:
        event.purpose = current.purpose
    if event.correlation_id is None:
        correlation = current.correlation_id
        if correlation is None:
            correlation = session.info.setdefault(_CORRELATION, secrets.token_hex(16))
        event.correlation_id = correlation
    _resolve(session, event)
    if event.refs is None and event.payload:
        # Evidence that is kept elsewhere (the statement someone signed, the
        # quote as it was issued) is tied into the chain by its hash.
        refs = {key: event.payload[key] for key in _REF_KEYS if event.payload.get(key)}
        event.refs = refs or None
    if event.field_classes is None:
        event.existence_class, event.field_classes = classify(
            event.subject_kind, event.old_value, event.new_value
        )
    if event.id is None:
        event.id = uuid4()
    event.salt = secrets.token_hex(16)
    event.old_digest = chain.digest(event.salt, event.old_value)
    event.new_digest = chain.digest(event.salt, event.new_value)
    event.payload_digest = chain.digest(event.salt, event.payload)
    event.note_digest = chain.digest(event.salt, event.note)


def columns_of(event: StreamEvent) -> dict[str, Any]:
    return {
        column.key: getattr(event, column.key)
        for column in StreamEvent.__table__.columns
    }


@sa_event.listens_for(StreamEvent, "init")
def _number(target: StreamEvent, args: Any, kwargs: Any) -> None:
    target._order = next(_order)  # type: ignore[attr-defined]


@sa_event.listens_for(Session, "before_flush")
def _seal(session: Session, flush_context: Any, instances: Any) -> None:
    pending = sorted(
        (
            obj
            for obj in session.new
            if isinstance(obj, StreamEvent) and obj.seq is None
        ),
        key=lambda obj: getattr(obj, "_order", 0),
    )
    if not pending:
        return
    for event in pending:
        _complete(session, event)
    connection = session.connection()
    # From here until this transaction ends no other transaction can add
    # to the stream, so positions are given out in commit order.
    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
    head = connection.execute(
        text("SELECT seq, hash FROM stream_event ORDER BY seq DESC LIMIT 1")
    ).first()
    seq, prev = (head[0], head[1]) if head is not None else (0, chain.GENESIS)
    now: datetime = connection.execute(text("SELECT now()")).scalar_one()
    for event in pending:
        seq += 1
        # A row that was removed behind the session's back (a table that
        # was emptied) must not stand in the way of the new one.
        stale = session.identity_map.get(identity_key(StreamEvent, seq))
        if stale is not None and stale is not event:
            session.expunge(stale)
        event.seq = seq
        if event.occurred_at is None:
            event.occurred_at = now
        event.prev_hash = prev
        event.hash = prev = chain.hash_of(columns_of(event))
    # A copy of the facts: after the commit the row itself may be expired.
    session.info.setdefault(_PENDING, []).extend(
        (event, columns_of(event)) for event in pending
    )
    session.info[_COUNT] = session.info.get(_COUNT, 0) + len(pending)
    session.info.setdefault(KINDS_WRITTEN, []).extend(e.subject_kind for e in pending)


def events_written(session: AsyncSession | Session) -> int:
    """How many events this session wrote since it was created."""
    return int(session.info.get(_COUNT, 0))


async def _run_after_commit(events: list[StreamEvent]) -> None:
    for event in events:
        for handler in [*_after_commit[event.type], *_after_commit[ANY]]:
            try:
                await handler(event)
            except Exception:
                # The change is durable; a failing reaction must not undo it
                # or stop the other reactions. The stream still has the
                # event, so a handler can catch up from its cursor.
                logger.exception(
                    "after-commit handler failed for %s (seq %s)",
                    event.type,
                    event.seq,
                )


async def drain() -> None:
    """Wait for the after-commit handlers that are running. For tests and shutdown."""
    while _running:
        await asyncio.gather(*list(_running), return_exceptions=True)


@sa_event.listens_for(Session, "after_commit")
def _dispatch(session: Session) -> None:
    if session.in_nested_transaction():
        # A savepoint was released: the work can still roll back.
        return
    session.info.pop(_CORRELATION, None)
    pending: list[tuple[StreamEvent, dict[str, Any]]] = session.info.pop(_PENDING, [])
    # An event written inside a savepoint that rolled back is not durable.
    durable = [
        StreamEvent(**facts) for event, facts in pending if sa_inspect(event).persistent
    ]
    if not durable or not any(_after_commit.values()):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("no event loop: after-commit handlers not run")
        return
    task = loop.create_task(_run_after_commit(durable))
    _running.add(task)
    task.add_done_callback(_running.discard)


@sa_event.listens_for(Session, "after_rollback")
def _discard(session: Session) -> None:
    if session.in_nested_transaction():
        # Only a savepoint went: what was written before it still stands,
        # and what was written inside it is no longer persistent.
        return
    session.info.pop(_PENDING, None)
    session.info.pop(_CORRELATION, None)
