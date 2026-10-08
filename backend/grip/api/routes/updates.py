"""The feed of updates: what happened that the reader would want to know.

A selection of the event stream in sentences (``grip.events.news``), with
which of it is new since the reader last looked.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access.deps import AccessDecider, CurrentSubject, get_relation_source
from grip.access.relations import RelationSource
from grip.core.auth import CurrentPerson
from grip.core.database import get_db
from grip.events import news
from grip.events.reading import EventAccess

router = APIRouter(prefix="/updates", tags=["events"])


@router.get("")
async def list_updates(
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    relations: RelationSource = Depends(get_relation_source),
    db: AsyncSession = Depends(get_db),
    na: Annotated[int | None, Query(ge=1)] = None,
    limiet: Annotated[int, Query(ge=1, le=news.MAX_ITEMS)] = 10,
) -> dict[str, Any]:
    """The news for the reader, newest first.

    ``na`` is the cursor of an earlier answer (``next``) and reads further
    back. ``new_count`` is how many items are new since the reader last
    looked; it is given on the first page only.
    """
    feed = await news.read(
        db, EventAccess(db, decider, subject), relations, cursor=na, limit=limiet
    )
    return {
        "items": [
            {
                **asdict(item),
                "when": item.when.isoformat(),
                "parts": [
                    {"text": part.text, **({"href": part.href} if part.href else {})}
                    for part in item.parts
                ],
            }
            for item in feed.items
        ],
        "new_count": feed.new_count,
        "next": feed.next_cursor,
    }


@router.post("/seen", status_code=204)
async def mark_seen(person: CurrentPerson, db: AsyncSession = Depends(get_db)) -> None:
    """The reader has looked: nothing that is there now is new any more."""
    await news.mark_seen(db, person.id)
