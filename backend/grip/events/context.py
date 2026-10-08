"""Who is acting and what ties events together, for the length of one request.

A web request, an incoming message or a job sets this once; every event
written while it is set takes its actor, origin and correlation id from it,
so the code that makes a change does not have to pass them along.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from uuid import UUID

from grip.models.stream_event import (
    ACTOR_GUEST,
    ACTOR_PEER,
    ACTOR_PERSON,
    ACTOR_SYSTEM,
    ORIGIN_LOCAL,
    ORIGIN_REMOTE,
)

_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")
_NO_TRACE = "0" * 32


@dataclass(frozen=True)
class EventContext:
    correlation_id: str | None = None
    actor_kind: str | None = None
    actor_person_id: UUID | None = None
    actor_ref: str | None = None
    origin: str = ORIGIN_LOCAL
    origin_peer: str | None = None
    purpose: str | None = None


_current: ContextVar[EventContext] = ContextVar("grip_event_context")


def current() -> EventContext:
    return _current.get(EventContext())


def new_correlation_id() -> str:
    return secrets.token_hex(16)


def correlation_from_traceparent(header: str | None) -> str | None:
    """The trace id of a W3C ``traceparent`` header, or None."""
    match = _TRACEPARENT.match((header or "").strip().lower())
    if match is None or match.group(1) == _NO_TRACE:
        return None
    return match.group(1)


def update(**changes: object) -> None:
    """Change the context of the running request or job."""
    _current.set(replace(current(), **changes))  # type: ignore[arg-type]


def set_person(person_id: UUID) -> None:
    update(actor_kind=ACTOR_PERSON, actor_person_id=person_id, actor_ref=None)


def set_guest(reference: str | None) -> None:
    update(actor_kind=ACTOR_GUEST, actor_person_id=None, actor_ref=reference)


def set_peer(peer_id: str) -> None:
    """An incoming message of another instance: actor and origin."""
    update(
        actor_kind=ACTOR_PEER,
        actor_person_id=None,
        actor_ref=peer_id,
        origin=ORIGIN_REMOTE,
        origin_peer=peer_id,
    )


def set_job(name: str) -> None:
    update(actor_kind=ACTOR_SYSTEM, actor_person_id=None, actor_ref=name)


@contextmanager
def scope(
    *, correlation_id: str | None = None, job: str | None = None
) -> Iterator[EventContext]:
    """A fresh context: one unit of work with its own correlation id."""
    context = EventContext(correlation_id=correlation_id or new_correlation_id())
    if job is not None:
        context = replace(context, actor_kind=ACTOR_SYSTEM, actor_ref=job)
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)
