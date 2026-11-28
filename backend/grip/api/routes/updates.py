"""The feed of updates: what happened that the reader would want to know.

A selection of the event stream in sentences (``grip.events.news``), with
which of it is new since the reader last looked.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import DataClass, build_response
from grip.access.deps import AccessDecider, CurrentSubject, get_relation_source
from grip.access.relations import RelationSource
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.events import news
from grip.events.reading import EventAccess
from grip.schema.updates import (
    UpdateFeedOut,
    UpdateFiltersOut,
    UpdateItemOut,
    UpdateOptionOut,
    UpdatePartOut,
    UpdatePersonOut,
)

router = APIRouter(prefix="/updates", tags=["events"])

# Each item was decided per event before it became one; see grip.schema.updates.
_CLASSES = frozenset({DataClass.ASSIGNMENT_BASIC})


def _item(item: news.Item) -> UpdateItemOut:
    return UpdateItemOut(
        id=item.id,
        seq=item.seq,
        kind=item.kind,
        rank=item.rank,
        when=item.when,
        when_text=item.when_text,
        day=item.day,
        parts=[UpdatePartOut(text=part.text, href=part.href) for part in item.parts],
        text=item.text,
        count=item.count,
        new=item.new,
    )


@router.get("", response_model=None)
async def list_updates(
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    relations: RelationSource = Depends(get_relation_source),
    db: AsyncSession = Depends(get_db),
    na: Annotated[int | None, Query(ge=1)] = None,
    limiet: Annotated[int, Query(ge=1, le=news.MAX_ITEMS)] = 10,
    opdracht: UUID | None = None,
    persoon: UUID | None = None,
) -> dict[str, Any]:
    """The news for the reader, newest first.

    ``na`` is the cursor of an earlier answer (``next``) and reads further
    back. ``new_count`` is how many items are new since the reader last
    looked; it is given on the first page only.

    ``opdracht`` keeps the items about that assignment and its parts,
    ``persoon`` the items that say that person did it. An assignment or a
    person the reader cannot see in the feed finds nothing, exactly as one
    that does not exist: the answer never says which of the two it was.
    """
    feed = await news.read(
        db,
        EventAccess(db, decider, subject),
        relations,
        cursor=na,
        limit=limiet,
        assignment_id=opdracht,
        actor_id=persoon,
    )
    return build_response(
        UpdateFeedOut(
            items=[_item(item) for item in feed.items],
            new_count=feed.new_count,
            next=feed.next_cursor,
        ),
        _CLASSES,
    )


@router.get("/filters", response_model=None)
async def list_update_filters(
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    relations: RelationSource = Depends(get_relation_source),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """What the feed of the reader can be narrowed to: the assignments it is
    about, and who it says did something. Taken from the reader's own feed,
    so it holds nothing the feed does not show."""
    options = await news.filter_options(
        db, EventAccess(db, decider, subject), relations
    )
    return build_response(
        UpdateFiltersOut(
            assignments=[
                UpdateOptionOut(id=option.id, name=option.name)
                for option in options.assignments
            ],
            people=[
                UpdatePersonOut(id=option.id, name=option.name)
                for option in options.people
            ],
        ),
        _CLASSES,
    )


@router.post("/seen", status_code=204)
async def mark_seen(person: CurrentPerson, db: AsyncSession = Depends(get_db)) -> None:
    """The reader has looked: nothing that is there now is new any more."""
    await news.mark_seen(db, person.id)
