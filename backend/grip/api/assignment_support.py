"""Shared plumbing for the routes of the assignment slice.

``Access`` wraps the decider for one request and remembers its answers, so a
list of rows about the same assignment and person does not ask the same
question again and again.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import (
    Action,
    Context,
    DataClass,
    Decider,
    Resource,
    Subject,
    decide,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.access.sql import SqlRelationSource
from grip.core import clock
from grip.core.config import Settings, get_settings
from grip.core.database import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]


class Access:
    def __init__(
        self,
        decider: Decider,
        subject: Subject,
        db: AsyncSession,
        settings: Settings,
    ) -> None:
        self._decider = decider
        self._db = db
        self._settings = settings
        self.subject = subject
        self._memo: dict[tuple[Action, Resource, DataClass | None, Context], bool] = {}

    async def may(
        self,
        action: Action,
        resource: Resource,
        data_class: DataClass | None = None,
        context: Context | None = None,
    ) -> bool:
        key = (action, resource, data_class, context or Context())
        if key not in self._memo:
            decision = await decide(
                self._decider, self.subject, action, resource, data_class, context
            )
            self._memo[key] = decision.allowed
        return self._memo[key]

    def forget(self) -> None:
        """Drop remembered answers. Call after a change that moves relations."""
        self._memo.clear()

    async def classes(
        self,
        resource: Resource,
        data_classes: Iterable[DataClass],
        context: Context | None = None,
    ) -> frozenset[DataClass]:
        """The classes among ``data_classes`` the subject may read on the resource."""
        permitted = set()
        for data_class in dict.fromkeys(data_classes):
            if await self.may(Action.READ, resource, data_class, context):
                permitted.add(data_class)
        return frozenset(permitted)

    async def require(
        self,
        action: Action,
        resource: Resource,
        data_class: DataClass | None = None,
        *,
        hide_existence: bool = False,
    ) -> None:
        await require(
            self._decider,
            self.subject,
            action,
            resource,
            data_class,
            hide_existence=hide_existence,
        )

    async def own_assignment_ids(self) -> set[UUID]:
        """Assignments the person owns, manages or is a member of."""
        if self.subject.person_id is None:
            return set()
        source = SqlRelationSource(
            self._db, instance_base_uri=self._settings.INSTANCE_BASE_URI
        )
        return await source.assignment_ids_for_person(
            self.subject.person_id, clock.today()
        )

    async def require_closed_year_override(self, requested: bool) -> bool:
        """Changing a closed year is for the beheerder only."""
        if requested:
            await self.require(Action.MANAGE_RATES, Resource.rate_card())
        return requested


def get_access(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> Access:
    return Access(decider, subject, db, settings)


RequestAccess = Annotated[Access, Depends(get_access)]


def parse_year(value: str | None) -> int | None:
    """The year filter: a year, ``all`` for the whole period, or the current year."""
    if value is None or value == "":
        return clock.today().year
    if value == "all":
        return None
    try:
        year = int(value)
    except ValueError:
        year = 0
    if not 2000 <= year <= 2100:
        raise HTTPException(
            status_code=422,
            detail="Het jaar is een jaartal, of 'all' voor de hele looptijd.",
        )
    return year


YearFilter = Annotated[
    str | None,
    Query(
        alias="year",
        description="A year, or 'all' for the whole period. Default: this year.",
    ),
]
