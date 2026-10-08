"""Who may see and change the tasks of a case.

A task is data class A of its case: a reader who may see the case sees its
tasks, and nobody else does. Every answer here comes from the access model;
this module only remembers the answers for the length of one request.

- Read: whoever may read the basics of the assignment, or the vacancy
  without names.
- Edit (add a task, hand one over, change any task): whoever may edit the
  basics or the staffing of the assignment, or edit the vacancy.
- The person a task is for may always change its status.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.access import Action, DataClass, Resource, Subject
from grip.access.decider import Decider, decide
from grip.access.vacancies import vacancy_resource
from grip.models.assignment import AssignmentRole, BudgetLine
from grip.models.task import Task
from grip.models.vacancy import Vacancy
from grip.tasks import catalogue


@dataclass(frozen=True)
class CaseRights:
    read: bool
    edit: bool


_NONE = CaseRights(read=False, edit=False)


class TaskAccess:
    """The rights of one reader on the cases of the tasks at hand."""

    def __init__(self, db: AsyncSession, decider: Decider, subject: Subject) -> None:
        self._db = db
        self._decider = decider
        self.subject = subject
        self._assignments: dict[UUID, CaseRights] = {}
        self._vacancies: dict[UUID, CaseRights] = {}
        self._roles: dict[UUID, str] | None = None

    async def _may(
        self, action: Action, resource: Resource, data_class: DataClass | None = None
    ) -> bool:
        decision = await decide(
            self._decider, self.subject, action, resource, data_class
        )
        return decision.allowed

    async def assignment(self, assignment_id: UUID) -> CaseRights:
        rights = self._assignments.get(assignment_id)
        if rights is None:
            resource = Resource.assignment(assignment_id)
            read = await self._may(
                Action.READ, resource, DataClass.ASSIGNMENT_BASIC
            )
            edit = read and (
                await self._may(Action.EDIT, resource, DataClass.ASSIGNMENT_BASIC)
                or await self._may(Action.EDIT, resource, DataClass.STAFFING)
            )
            rights = CaseRights(read=read, edit=edit)
            self._assignments[assignment_id] = rights
        return rights

    async def prime_vacancies(self, vacancy_ids: set[UUID]) -> None:
        """Decide for several vacancies with one query for their facts."""
        missing = vacancy_ids - self._vacancies.keys()
        if not missing:
            return
        vacancies = (
            await self._db.scalars(
                select(Vacancy)
                .where(Vacancy.id.in_(missing))
                .options(selectinload(Vacancy.decisions))
            )
        ).all()
        line_ids = {v.budget_line_id for v in vacancies} - {None}
        assignment_of: dict[UUID, UUID] = {}
        if line_ids:
            rows = await self._db.execute(
                select(BudgetLine.id, BudgetLine.assignment_id).where(
                    BudgetLine.id.in_(line_ids)
                )
            )
            assignment_of = {row[0]: row[1] for row in rows}
        for vacancy in vacancies:
            resource = vacancy_resource(
                vacancy.id,
                assignment_id=assignment_of.get(vacancy.budget_line_id)
                if vacancy.budget_line_id
                else None,
                named={d.kind: d.person_id for d in vacancy.decisions},
            )
            read = await self._may(Action.READ, resource, DataClass.STAFFING_COUNTS)
            edit = read and await self._may(Action.EDIT, resource)
            self._vacancies[vacancy.id] = CaseRights(read=read, edit=edit)
        for vacancy_id in missing - {v.id for v in vacancies}:
            self._vacancies[vacancy_id] = _NONE

    async def vacancy(self, vacancy_id: UUID) -> CaseRights:
        if vacancy_id not in self._vacancies:
            await self.prime_vacancies({vacancy_id})
        return self._vacancies[vacancy_id]

    async def case(
        self, case_kind: str, assignment_id: UUID | None, vacancy_id: UUID | None
    ) -> CaseRights:
        if case_kind == "vacancy" and vacancy_id is not None:
            return await self.vacancy(vacancy_id)
        if assignment_id is not None:
            return await self.assignment(assignment_id)
        return _NONE

    async def of_task(self, task: Task) -> CaseRights:
        return await self.case(task.case_kind, task.assignment_id, task.vacancy_id)

    async def assignment_roles(self) -> dict[UUID, str]:
        """The assignments this person owns or manages, with the role."""
        if self._roles is None:
            self._roles = {}
            if self.subject.person_id is not None:
                rows = await self._db.execute(
                    select(AssignmentRole.assignment_id, AssignmentRole.role).where(
                        AssignmentRole.person_id == self.subject.person_id
                    )
                )
                self._roles = {row[0]: row[1] for row in rows}
        return self._roles

    async def is_for_reader(self, task: Task) -> bool:
        """Whether this task is the reader's to do."""
        person_id = self.subject.person_id
        if person_id is None:
            return False
        if task.assignee_person_id is not None:
            return task.assignee_person_id == person_id
        role = task.assignee_role
        if role in catalogue.FUNCTION_ROLES:
            return role in self.subject.functions
        if role in catalogue.ASSIGNMENT_ROLES and task.assignment_id is not None:
            held = (await self.assignment_roles()).get(task.assignment_id)
            return held == "owner" if role == "owner" else held is not None
        return False
