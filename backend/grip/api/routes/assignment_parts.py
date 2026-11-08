"""The parts of one assignment and what each one has to say."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from grip.access import Action, DataClass, Resource, build_response
from grip.access.deps import AccessDecider, CurrentSubject
from grip.api.assignment_support import DbSession, RequestAccess
from grip.schema.assignment_parts import AssignmentPartOut, AssignmentPartsOut
from grip.services import assignment_parts as parts
from grip.tasks.access import TaskAccess

router = APIRouter(tags=["assignments"])

A = DataClass.ASSIGNMENT_BASIC
C = DataClass.STAFFING
_CLASSES = {
    A,
    DataClass.ASSIGNMENT_FINANCIAL,
    C,
    DataClass.STAFFING_ROSTER,
    DataClass.RATE_MISMATCH_SIGNAL,
}


@router.get("/assignments/{assignment_id}/parts", response_model=None)
async def get_assignment_parts(
    assignment_id: UUID,
    access: RequestAccess,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: DbSession,
) -> dict[str, Any]:
    """The rows of an assignment and what each one reports to this reader."""
    resource = Resource.assignment(assignment_id)
    await access.require(Action.READ, resource, A, hide_existence=True)
    classes = await access.classes(resource, _CLASSES)
    facts = await parts.load_facts(db, assignment_id, classes)

    person_id = access.subject.person_id
    reads_own = person_id is not None and await access.may(
        Action.READ, Resource.allocation(assignment_id, person_id), C
    )
    own_line = await parts.own_line(db, assignment_id, person_id) if reads_own else None

    return build_response(
        AssignmentPartsOut(
            assignment_id=assignment_id,
            parts=[
                AssignmentPartOut(key=part.key, label=part.label, notice=part.notice)
                for part in parts.parts_of(facts, classes)
            ],
            # The reader may change its tasks: the rule of the task layer.
            tasks_link=(
                await TaskAccess(db, decider, subject).assignment(assignment_id)
            ).edit,
            is_client=facts.is_client,
            own_line=own_line,
        ),
        {A, C} if reads_own else {A},
    )
