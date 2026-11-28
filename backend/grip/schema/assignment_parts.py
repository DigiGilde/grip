"""The parts of one assignment."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel

from grip.access import DataClass, in_class, nested

A = DataClass.ASSIGNMENT_BASIC
C = DataClass.STAFFING

PartKey = Literal["close", "budget", "quote", "team", "report", "details", "history"]


class AssignmentPartOut(BaseModel):
    """One row. ``parts_of`` only makes a row and a notice from classes the
    reader may read, so the fields themselves are as open as the assignment."""

    key: Annotated[PartKey, in_class(A)]
    label: Annotated[str, in_class(A)]
    notice: Annotated[str | None, in_class(A)]


class AssignmentPartsOut(BaseModel):
    assignment_id: Annotated[UUID, in_class(A)]
    parts: Annotated[list[AssignmentPartOut], nested()]
    tasks_link: Annotated[bool, in_class(A)]
    # This instance is the client: the work of the contractor is not here.
    is_client: Annotated[bool, in_class(A)]
    # About the reader's own inzet, decided on the reader's own allocation.
    own_line: Annotated[str | None, in_class(C)]
