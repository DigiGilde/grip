"""Inzet with what the assignment's status says about it.

Staffing a potential assignment is tentative: the work may not come. Views
on occupancy and capacity show firm and tentative inzet apart, and take the
distinction from here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.services.phase import (
    Commitment,
    Phase,
    commitment_of,
    is_tentative,
    phase_of,
    statuses_with_commitment,
)


@dataclass(frozen=True)
class StaffedAllocation:
    """One allocation with the standing of its assignment (data class C)."""

    allocation_id: UUID
    person_id: UUID
    budget_line_id: UUID
    assignment_id: UUID
    assignment_status: str
    start_date: date
    end_date: date
    fte_pct: Decimal

    @property
    def phase(self) -> Phase:
        return phase_of(self.assignment_status)

    @property
    def tentative(self) -> bool:
        """True while the assignment is still potential."""
        return is_tentative(self.assignment_status)

    @property
    def verbally_agreed(self) -> bool:
        """Tentative, but the client has said yes."""
        return commitment_of(self.assignment_status) is Commitment.VERBAL


async def staffed_allocations(
    session: AsyncSession,
    *,
    person_ids: Iterable[UUID] | None = None,
    assignment_ids: Iterable[UUID] | None = None,
    start: date | None = None,
    end: date | None = None,
    include_closed: bool = False,
) -> list[StaffedAllocation]:
    """Allocations with their firmness, optionally for a period.

    Inzet on an assignment that was cancelled is left out unless
    ``include_closed`` is set: it will not happen. Inzet on a completed or
    accounted assignment is firm and always included.
    """
    stmt = (
        select(Allocation, BudgetLine.assignment_id, Assignment.status)
        .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
        .join(Assignment, Assignment.id == BudgetLine.assignment_id)
        .order_by(Allocation.start_date, Allocation.id)
    )
    if person_ids is not None:
        ids = list(set(person_ids))
        if not ids:
            return []
        stmt = stmt.where(Allocation.person_id.in_(ids))
    if assignment_ids is not None:
        ids = list(set(assignment_ids))
        if not ids:
            return []
        stmt = stmt.where(BudgetLine.assignment_id.in_(ids))
    if start is not None:
        stmt = stmt.where(Allocation.end_date >= start)
    if end is not None:
        stmt = stmt.where(Allocation.start_date <= end)
    if not include_closed:
        stmt = stmt.where(
            Assignment.status.notin_(statuses_with_commitment(Commitment.NONE))
        )
    return [
        StaffedAllocation(
            allocation_id=allocation.id,
            person_id=allocation.person_id,
            budget_line_id=allocation.budget_line_id,
            assignment_id=assignment_id,
            assignment_status=status,
            start_date=allocation.start_date,
            end_date=allocation.end_date,
            fte_pct=allocation.fte_pct,
        )
        for allocation, assignment_id, status in (await session.execute(stmt)).all()
    ]
