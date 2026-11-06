"""The chronicle of an assignment: its moments, and how things stood at each.

Rights are those of now. Nothing here writes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.config import Settings, get_settings
from grip.schema.chronicle import MomentsOut, StandOut
from grip.services import chronicle

router = APIRouter(tags=["chronicle"])

_CLASSES = schema_classes(StandOut)


async def _reader(
    access: RequestAccess, assignment_id: UUID
) -> tuple[chronicle.Reader, frozenset[DataClass]]:
    resource = Resource.assignment(assignment_id)
    await access.require(
        Action.READ, resource, DataClass.ASSIGNMENT_BASIC, hide_existence=True
    )
    classes = await access.classes(resource, _CLASSES)
    return (
        chronicle.Reader(manages=await access.may(Action.ISSUE_QUOTE, resource)),
        classes,
    )


@router.get("/assignments/{assignment_id}/chronicle", response_model=None)
async def read_moments(
    assignment_id: UUID, access: RequestAccess, db: DbSession
) -> dict[str, Any]:
    """The moments of an assignment, oldest first."""
    reader, classes = await _reader(access, assignment_id)
    moments: MomentsOut = await chronicle.moments(db, assignment_id, reader)
    return build_response(moments, classes)


@router.get("/assignments/{assignment_id}/chronicle/{seq}", response_model=None)
async def read_stand(
    assignment_id: UUID,
    seq: int,
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """How the assignment stood at one of its moments."""
    reader, classes = await _reader(access, assignment_id)
    stand = await chronicle.stand(
        db,
        assignment_id,
        seq,
        reader,
        instance_base_uri=settings.INSTANCE_BASE_URI,
    )
    return build_response(stand, classes)
