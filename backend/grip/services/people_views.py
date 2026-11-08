"""Which views of the people a reader has something in.

Each question asks only whether the reader sees anything in a view, with the
decisions the view itself takes, and stops at the first yes. Nothing is built.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, DataClass, Resource, Subject
from grip.core import clock
from grip.services import staffing, staffing_board
from grip.services.reports import steering
from grip.services.vacancies import service as vacancies

_C = DataClass.STAFFING
_F = DataClass.PERSON_KPI
BOARD_MONTHS = 12
VIEWS = ("list", "board", "occupancy", "billability")


class Reader(Protocol):
    subject: Subject

    async def may(
        self, action: Action, resource: Resource, data_class: DataClass | None = ...
    ) -> bool: ...


async def _reads(reader: Reader, resource: Resource, data_class: DataClass) -> bool:
    return await reader.may(Action.READ, resource, data_class)


async def _any_person(
    reader: Reader, person_ids: Iterable[UUID], data_class: DataClass
) -> bool:
    for person_id in person_ids:
        if await _reads(reader, Resource.person(person_id), data_class):
            return True
    return False


async def has_list(reader: Reader, person_classes: Iterable[DataClass]) -> bool:
    """Whether the reader sees at least one person, or themselves."""
    me = reader.subject.person_id
    resources = [Resource.person()]
    if me is not None:
        resources.append(Resource.person(me))
    for resource in resources:
        for data_class in person_classes:
            if await _reads(reader, resource, data_class):
                return True
    return False


async def has_board(reader: Reader, db: AsyncSession) -> bool:
    """Whether the board has a row, a bar or an open role for the reader."""
    today = clock.today()
    span = staffing_board.window(staffing_board.default_start(today), BOARD_MONTHS)
    bars = await staffing.staffed_allocations(
        db, start=span[0].first_day, end=span[-1].last_day
    )
    person_ids = await steering.occupancy_person_ids(db, span)
    if await _any_person(reader, person_ids, _C):
        return True
    for bar in bars:
        if await _reads(
            reader, Resource.allocation(bar.assignment_id, bar.person_id), _C
        ):
            return True
    for role in await vacancies.open_roles(db, today=today):
        if staffing_board.role_in_span(role, span) and await _reads(
            reader, Resource.assignment(role.assignment_id), _C
        ):
            return True
    return False


async def has_occupancy(reader: Reader, db: AsyncSession) -> bool:
    """Whether the occupancy block of this year has a person the reader sees."""
    months = steering.months_of(clock.today().year)
    return await _any_person(
        reader, await steering.occupancy_person_ids(db, months), _C
    )


async def has_billability(reader: Reader, db: AsyncSession) -> bool:
    """Whether someone besides the reader has a figure the reader may read."""
    me = reader.subject.person_id
    year = clock.today().year
    return await _any_person(
        reader,
        [
            person_id
            for person_id, _name in await steering.kpi_person_ids(db, year)
            if person_id != me
        ],
        _F,
    )
