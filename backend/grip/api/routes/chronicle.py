"""The chronicle of an assignment: its moments, and how things stood at each.

Rights are those of now. Reading writes nothing; taking a typed text out of a
moment is the one act here (ADR 0057).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from grip.access import Action, DataClass, Resource, build_response, schema_classes
from grip.api.assignment_support import DbSession, RequestAccess
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.schema.chronicle import MomentsOut, RestatedStandOut, RestateIn, StandOut
from grip.services import chronicle, restatements

router = APIRouter(tags=["chronicle"])

_CLASSES = schema_classes(StandOut)
_RESTATED_CLASSES = schema_classes(RestatedStandOut)


async def _reader(
    access: RequestAccess, assignment_id: UUID
) -> tuple[chronicle.Reader, frozenset[DataClass]]:
    resource = Resource.assignment(assignment_id)
    await access.require(
        Action.READ, resource, DataClass.ASSIGNMENT_BASIC, hide_existence=True
    )
    classes = await access.classes(resource, _CLASSES)
    return (
        chronicle.Reader(
            manages=await access.may(Action.ISSUE_QUOTE, resource),
            restates=await access.may(Action.RESTATE_FACT, resource),
        ),
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


@router.post(
    "/assignments/{assignment_id}/chronicle/{seq}/restate", response_model=None
)
async def restate_moment(
    assignment_id: UUID,
    seq: int,
    body: RestateIn,
    person: CurrentPerson,
    access: RequestAccess,
    db: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Take typed texts out of a moment: it is recorded again without them."""
    resource = Resource.assignment(assignment_id)
    await access.require(
        Action.READ, resource, DataClass.ASSIGNMENT_BASIC, hide_existence=True
    )
    await access.require(Action.RESTATE_FACT, resource)
    done = await restatements.restate_moment(
        db, assignment_id, seq, body.columns, actor=person
    )
    reader, _classes = await _reader(access, assignment_id)
    stand = await chronicle.stand(
        db,
        assignment_id,
        seq,
        reader,
        instance_base_uri=settings.INSTANCE_BASE_URI,
    )
    return build_response(
        RestatedStandOut(stand=stand, kept=done.kept),
        await access.classes(resource, _RESTATED_CLASSES),
    )
