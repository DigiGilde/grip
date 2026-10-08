"""Test helper: bring an assignment to a status a test needs."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.assignment import Assignment
from grip.services import assignments


async def accept(session: AsyncSession, assignment_id: UUID, *, actor=None) -> None:
    """Move an assignment to accepted along the lifecycle, from where it is.

    Months close and billing data exists only from an agreement on, so a test
    about closing months accepts its assignment first.
    """
    assignment = await session.get(Assignment, assignment_id)
    assert assignment is not None
    path = {"draft": ("quoted", "accepted"), "requested": ("quoted", "accepted")}
    for step in path.get(assignment.status, ("accepted",)):
        if assignment.status == "accepted":
            break
        await assignments.transition(
            session, assignment_id, step, actor=actor, enforce_readiness=False
        )
