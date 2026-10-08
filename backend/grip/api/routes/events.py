"""The event stream, read two ways.

``/events`` is the audit log for people: the history of a case, what a
person did, what was done to a person's data, and everything in the
instance. Every event is decided on by the access model, per field.

``/gebeurtenissen`` is the feed for other systems: CloudEvents in the NL
GOV profile, in order, read with a cursor. It is closed until a key is
configured.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.deps import AccessDecider, CurrentSubject
from grip.access.machine_deps import require_feed_key
from grip.access.types import Action, Resource
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.events import check, cloudevents, reading
from grip.events.classification import SPECS
from grip.events.reading import EventAccess, Filters
from grip.models.stream_event import StreamEvent

router = APIRouter(prefix="/events", tags=["events"])
feed_router = APIRouter(prefix="/gebeurtenissen", tags=["events"])

_FEED_MAX = 500


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@router.get("")
async def list_events(
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    case_kind: Annotated[str | None, Query(pattern="^(assignment|vacancy)$")] = None,
    case_id: UUID | None = None,
    person_id: UUID | None = None,
    actor_id: UUID | None = None,
    type: Annotated[list[str] | None, Query(max_length=20)] = None,  # noqa: A002
    subject_kind: str | None = None,
    subject_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    correlation_id: str | None = None,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=reading.MAX_PAGE)] = 50,
) -> dict[str, Any]:
    """Events the reader may know of, newest first.

    No total is given and an event the reader may not know of leaves no
    trace: a filter that matches nothing visible answers like one that
    matches nothing at all.
    """
    page = await reading.read(
        db,
        EventAccess(db, decider, subject),
        Filters(
            case_kind=case_kind,
            case_id=case_id,
            person_id=person_id,
            actor_person_id=actor_id,
            types=tuple(type or ()),
            subject_kind=subject_kind,
            subject_id=subject_id,
            since=since,
            until=until,
            correlation_id=correlation_id,
        ),
        before=before,
        limit=limit,
    )
    return {
        "items": [_jsonable(asdict(view)) for view in page.events],
        "next_before": page.next_before,
    }


async def _require_manager(decider: Any, subject: Any) -> None:
    from grip.access.deps import require

    await require(decider, subject, Action.MANAGE_USERS, Resource.instance())


@router.get("/kinds")
async def list_kinds(person: CurrentPerson) -> dict[str, Any]:
    """The kinds of subject an event can be about, for a filter."""
    return {"items": sorted(SPECS)}


@router.get("/chain")
async def check_chain(
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Whether the hash chain of the stream is whole, for the beheerder."""
    await _require_manager(decider, subject)
    verdict = await check.verify_stream(db)
    return {
        "intact": verdict.intact,
        "checked": verdict.checked,
        "head_seq": verdict.head_seq,
        "head_hash": verdict.head_hash,
        "breaks": [{"seq": b.seq, "reason": b.reason} for b in verdict.breaks],
    }


@feed_router.get("", dependencies=[Depends(require_feed_key)])
async def feed(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    na: Annotated[int, Query(ge=0)] = 0,
    limiet: Annotated[int, Query(ge=1, le=_FEED_MAX)] = 100,
) -> dict[str, Any]:
    """Everything after event ``na``, in order.

    ``volgende`` is the cursor for the next call: pass it as ``na``. It is
    the position of the last event given, or ``na`` itself when there was
    nothing new. The order of the stream is the order in which changes
    became durable, so a reader that follows the cursor misses nothing.
    """
    if not settings.EVENTS_FEED_KEY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "De stroom staat dicht")
    rows = (
        await db.scalars(
            select(StreamEvent)
            .where(StreamEvent.seq > na)
            .order_by(StreamEvent.seq)
            .limit(limiet)
        )
    ).all()
    return {
        "gebeurtenissen": [cloudevents.to_cloudevent(row, settings) for row in rows],
        "volgende": rows[-1].seq if rows else na,
        "meer": len(rows) == limiet,
    }
