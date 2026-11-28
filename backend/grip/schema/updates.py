"""The feed of updates: sentences about what happened, and what it narrows to.

Every field is class A of what it is about, as a task is (``grip.schema.tasks``).
An item is only there when the reader may know each event in it, which the
access model decides per event in ``grip.events.news``, and its sentence names
only what the reader may see. A filter option is something the feed already
shows: an assignment an item is about that the reader may open, or the person
a sentence says did it, by the name the sentence gives.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

A = in_class(DataClass.ASSIGNMENT_BASIC)


class UpdatePartOut(BaseModel):
    text: Annotated[str, A]
    # Where the thing is to be seen; null for a part that is no link.
    href: Annotated[str | None, A] = None


class UpdateItemOut(BaseModel):
    id: Annotated[str, A]
    seq: Annotated[int, A]
    kind: Annotated[str, A]
    rank: Annotated[int, A]
    when: Annotated[datetime, A]
    when_text: Annotated[str, A]
    day: Annotated[str, A]
    parts: Annotated[list[UpdatePartOut], nested()]
    text: Annotated[str, A]
    count: Annotated[int, A]
    new: Annotated[bool, A]


class UpdateFeedOut(BaseModel):
    items: Annotated[list[UpdateItemOut], nested()]
    # Given on the first page only.
    new_count: Annotated[int, A]
    # Pass as ``na`` to read further back; null when there is nothing older.
    next: Annotated[int | None, A] = None


class UpdateOptionOut(BaseModel):
    """An assignment an item is about, which the reader may read class A of."""

    id: Annotated[UUID, A]
    name: Annotated[str, A]


class UpdatePersonOut(BaseModel):
    """Who did something the reader may know of, as the sentence names them.

    Not the roster class of the person (``STAFFING_ROSTER``, as in a list of
    people): it is the actor of an event, which goes with the event, as the
    history gives it and as a moment of the chronicle does
    (``MomentOut.actor_name``, class A).
    """

    id: Annotated[UUID, A]
    name: Annotated[str, A]


class UpdateFiltersOut(BaseModel):
    assignments: Annotated[list[UpdateOptionOut], nested()]
    people: Annotated[list[UpdatePersonOut], nested()]
