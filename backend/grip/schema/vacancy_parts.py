"""The parts of one vacancy.

A reader who only gets the published text keeps the id and an empty list. For
the others a row says where its part stands; a name in ``notice`` is only
there for who runs the vacancy.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

PUBLIC = in_class(DataClass.OPEN_ROLE)
NO_NAMES = in_class(DataClass.STAFFING_COUNTS)

VacancyPartKey = Literal[
    "request", "decisions", "text", "fulfilment", "details", "history"
]
VacancyPartState = Literal["done", "current", "waiting", "future"]


class VacancyPartOut(BaseModel):
    key: Annotated[VacancyPartKey, NO_NAMES]
    label: Annotated[str, NO_NAMES]
    notice: Annotated[str | None, NO_NAMES] = None
    state: Annotated[VacancyPartState | None, NO_NAMES] = None


class VacancyPartsOut(BaseModel):
    vacancy_id: Annotated[UUID, PUBLIC]
    parts: Annotated[list[VacancyPartOut], nested()]
    tasks_link: Annotated[bool, PUBLIC] = False
