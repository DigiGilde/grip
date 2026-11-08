"""Search results: a name and a way to open the thing, nothing more."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class

_ASSIGNMENT = in_class(DataClass.ASSIGNMENT_BASIC)
_VACANCY = in_class(DataClass.OPEN_ROLE)
_PERSON = in_class(DataClass.STAFFING_ROSTER)


class SearchAssignmentOut(BaseModel):
    id: Annotated[UUID, _ASSIGNMENT]
    name: Annotated[str, _ASSIGNMENT]
    client_name: Annotated[str | None, _ASSIGNMENT]
    phase: Annotated[str, _ASSIGNMENT]


class SearchVacancyOut(BaseModel):
    id: Annotated[UUID, _VACANCY]
    title: Annotated[str, _VACANCY]


class SearchPersonOut(BaseModel):
    id: Annotated[UUID, _PERSON]
    name: Annotated[str, _PERSON]
