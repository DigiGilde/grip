"""Who may make a quote: the right to, on the contractor's side only.

``Action.ISSUE_QUOTE`` is also asked for the other direction (a quote that
comes in from a contractor), so the decider cannot say no to the client side.
The routes that make or change a quote ask here instead.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Action, Decider, Resource, Subject, decide
from grip.access.deps import require
from grip.models.assignment import Assignment
from grip.services.client_side import own_organisation_ids


async def _is_client_side(db: AsyncSession, assignment_id: UUID | None) -> bool:
    if assignment_id is None:
        return False
    assignment = await db.get(Assignment, assignment_id)
    return assignment is not None and (
        assignment.client_organisation_id in await own_organisation_ids(db)
    )


async def may_issue_quote(
    db: AsyncSession, decider: Decider, subject: Subject, resource: Resource
) -> bool:
    if await _is_client_side(db, resource.assignment_id):
        return False
    return bool(await decide(decider, subject, Action.ISSUE_QUOTE, resource))


async def require_issue_quote(
    db: AsyncSession, decider: Decider, subject: Subject, resource: Resource
) -> None:
    if await _is_client_side(db, resource.assignment_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Je hebt hier geen toegang toe",
        )
    await require(decider, subject, Action.ISSUE_QUOTE, resource)
