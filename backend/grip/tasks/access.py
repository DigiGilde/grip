"""Who may see and change the tasks of a case.

A task is data class A of its case: a reader who may see the case sees its
tasks, and nobody else does. Every answer here comes from the access model;
this module only remembers the answers for the length of one request.

- Read: whoever may read the basics of the assignment, or the vacancy
  without names.
- Edit (add a task, hand one over, change any task): whoever may edit the
  basics or the staffing of the assignment, or edit the vacancy.
- The person a task is for may always change its status.
- A task that asks for internal approval of a quote is readable by whoever
  may approve quotes, as the quote itself is.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.access import Action, DataClass, Resource, Subject
from grip.access.decider import Decider, decide
from grip.access.quote_approval import quote_resource
from grip.access.vacancies import vacancy_resource
from grip.models.assignment import AssignmentRole, BudgetLine
from grip.models.task import Task
from grip.models.vacancy import Vacancy
from grip.tasks import catalogue
from grip.tasks.plan import Template, current_plan, plan_for


@dataclass(frozen=True)
class CaseRights:
    read: bool
    edit: bool


_NONE = CaseRights(read=False, edit=False)


def _template_of(task: Task) -> Template | None:
    if not task.template_key:
        return None
    return plan_for(task.plan_version).template(task.template_key) or (
        current_plan().template(task.template_key)
    )


def _template_now(task: Task, name: str) -> bool:
    """A property of the template in the plan of today: a task from an older
    plan is held to what the plan says now about who may decide."""
    template = current_plan().template(task.template_key or "")
    return bool(template is not None and getattr(template, name))


def separated(task: Task) -> bool:
    """Whether the step is one where someone else must decide."""
    template = _template_of(task)
    return bool(template is not None and template.separation) or _template_now(
        task, "separation"
    )


def _asks_for_approval(task: Task) -> bool:
    return (
        task.subject_kind == "quote_approval"
        and task.is_open
        and task.subject_id is not None
        and task.assignment_id is not None
    )


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
            read = await self._may(Action.READ, resource, DataClass.ASSIGNMENT_BASIC)
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
        rights = await self.case(task.case_kind, task.assignment_id, task.vacancy_id)
        if rights.read or not _asks_for_approval(task):
            return rights
        # Whoever may approve quotes reads a quote for which approval was
        # asked, without any other relation to the assignment. The task that
        # asks for that approval is theirs to see; nothing else of the case is.
        assert task.assignment_id is not None and task.subject_id is not None
        resource = quote_resource(
            UUID(task.subject_id), task.assignment_id, approval_requested=True
        )
        read = await self._may(Action.READ, resource, DataClass.ASSIGNMENT_BASIC)
        return CaseRights(read=read, edit=False)

    async def may_record_decision(
        self, vacancy: Vacancy, assignment_id: UUID | None, kind: str
    ) -> bool:
        """Whether the reader may record this advice or approval on the vacancy."""
        resource = vacancy_resource(
            vacancy.id,
            assignment_id=assignment_id,
            named={d.kind: d.person_id for d in vacancy.decisions},
            decision_kind=kind,
        )
        return await self._may(Action.RECORD_DECISION, resource)

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

    async def may_take_over(self, task: Task) -> bool:
        """Whether the reader may do this step for the one whose move it is.

        Taking over never grants a right: the reader must already hold what
        the step itself asks for. And never a step whose point is that
        someone else decides (``separation`` in the plan): an approval, an
        advice, a review, the client's decision.
        """
        if self.subject.person_id is None or not task.is_open:
            return False
        if task.assignee_person_id == self.subject.person_id:
            return False
        if task.status == "waiting" or task.waiting_on:
            return False
        template = _template_of(task)
        if template is None:
            # A task someone made by hand: whoever runs the case.
            return (await self.of_task(task)).edit
        if template.separation or _template_now(task, "separation"):
            return False
        role = template.assignee
        if role in catalogue.FUNCTION_ROLES:
            return role in self.subject.functions
        if task.case_kind == "vacancy":
            # The work of the requester or a writer: who may edit the vacancy.
            return task.vacancy_id is not None and (
                (await self.vacancy(task.vacancy_id)).edit
            )
        if task.assignment_id is None:
            return False
        # The work of the owner, a manager or the maker of a quote: the same
        # right those actions ask for, editing the assignment itself. Being
        # allowed to staff it is not enough.
        resource = Resource.assignment(task.assignment_id)
        return await self._may(
            Action.READ, resource, DataClass.ASSIGNMENT_BASIC
        ) and await self._may(Action.EDIT, resource, DataClass.ASSIGNMENT_BASIC)

    async def is_for_reader(self, task: Task) -> bool:
        """Whether this task is the reader's to do."""
        person_id = self.subject.person_id
        if person_id is None:
            return False
        if task.assignee_person_id is not None:
            return task.assignee_person_id == person_id
        role = task.assignee_role
        if role == "planner" and task.assignment_id is not None:
            # Staffing is the planner's work, and also that of whoever may
            # staff this assignment: its owner or a manager does not wait
            # for a planner to do what she may do herself.
            if role in self.subject.functions:
                return True
            resource = Resource.assignment(task.assignment_id)
            return await self._may(
                Action.READ, resource, DataClass.ASSIGNMENT_BASIC
            ) and await self._may(Action.EDIT, resource, DataClass.STAFFING)
        if role in catalogue.FUNCTION_ROLES:
            if role not in self.subject.functions:
                return False
            # Internal approval is a second person's: not hers who made the
            # quote or asked for the approval, whatever right she holds.
            return not (
                task.subject_kind == "quote_approval"
                and person_id in await self._not_to_decide(task)
            )
        if role in catalogue.ASSIGNMENT_ROLES and task.assignment_id is not None:
            held = (await self.assignment_roles()).get(task.assignment_id)
            return held == "owner" if role == "owner" else held is not None
        return False

    async def _not_to_decide(self, task: Task) -> frozenset[UUID]:
        """Who may not decide on the approval this task asks for."""
        from grip.models.quote import Quote, QuoteApproval
        from grip.services import quote_approval

        try:
            approval_id = UUID(task.repeat_key)
        except ValueError:
            return frozenset()
        approval = await self._db.get(QuoteApproval, approval_id)
        quote = await self._db.get(Quote, approval.quote_id) if approval else None
        if approval is None or quote is None:
            return frozenset()
        return await quote_approval.second_person_excluded(self._db, approval, quote)
