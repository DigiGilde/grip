"""Load an import plan into grip, through the service layer only.

Every write goes through ``grip.services``, so the data is valid by the same
rules as data entered in the screens and the audit log is filled. The Grist
row id of each record is kept in ``grist_import_ref``; a rerun against the
same or a newer download updates what is there instead of adding to it.

A row that disappeared from Grist is reported, never removed from grip. The
only records the loader takes away are ones it puts back in the same breath:
an allocation that moved to another person or line, and a changed invoice
line, because the services have no way to change those in place.

The loader does not commit. The caller commits when there are no errors and
rolls back for a dry run.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.importers.grist.refs import RefIndex
from grip.importers.grist.transform import (
    ERROR,
    INFO,
    WARNING,
    ImportPlan,
    Issue,
    PlanAssignment,
    PlanLine,
)
from grip.models.assignment import Allocation, Assignment, AssignmentRole, BudgetLine
from grip.models.cost import CostCoverage, CostItem, InvoiceLine
from grip.models.person import Person
from grip.models.person_details import BillabilityTarget, PersonScale
from grip.repositories.domain import RateRepository
from grip.services import assignments, costs, rates, team
from grip.services.errors import DomainError

T = TypeVar("T")

E_PERSON = "person"
E_SCALE = "person_scale"
E_ASSIGNMENT = "assignment"
E_LINE = "budget_line"
E_ALLOCATION = "allocation"
E_COST = "cost_item"
E_INVOICE = "invoice_line"
E_COVERAGE = "cost_coverage"
E_TARGET = "billability_target"


@dataclass
class LoadResult:
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    unchanged: dict[str, int] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    # Grist row id to grip id, per logical table, for the reconciliation.
    persons: dict[int, UUID] = field(default_factory=dict)
    assignments: dict[int, UUID] = field(default_factory=dict)
    lines: dict[int, UUID] = field(default_factory=dict)
    allocations: dict[int, UUID] = field(default_factory=dict)
    cost_items: dict[int, UUID] = field(default_factory=dict)
    vanished: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == ERROR]

    def _count(self, bucket: dict[str, int], entity: str) -> None:
        bucket[entity] = bucket.get(entity, 0) + 1


class Loader:
    def __init__(
        self,
        session: AsyncSession,
        plan: ImportPlan,
        *,
        document_key: str,
        actor: Person | None = None,
        allow_closed_year: bool = False,
    ) -> None:
        self.session = session
        self.plan = plan
        self.actor = actor
        self.allow_closed_year = allow_closed_year
        self.refs = RefIndex(session, document_key)
        self.result = LoadResult()

    # -- helpers --------------------------------------------------------------

    def _table(self, logical: str) -> str:
        return self.plan.grist_tables.get(logical, logical)

    def _issue(self, severity: str, where: str, message: str) -> None:
        self.result.issues.append(Issue(severity, where, message))

    async def _try(self, where: str, call: Awaitable[T]) -> T | None:
        """Await one service call in a savepoint; a refusal becomes an issue."""
        try:
            async with self.session.begin_nested():
                return await call
        except DomainError as exc:
            self._issue(ERROR, where, str(exc))
            return None

    async def _try_remove(self, where: str, call: Awaitable[None]) -> bool:
        """Like ``_try`` for a service that returns nothing: True when done."""
        try:
            async with self.session.begin_nested():
                await call
        except DomainError as exc:
            self._issue(ERROR, where, str(exc))
            return False
        return True

    def _where(self, logical: str, row_id: int) -> str:
        return f"{self._table(logical)} rij {row_id}"

    # -- rates ----------------------------------------------------------------

    async def rates(self) -> None:
        plan = self.plan
        if not plan.rate_bands:
            return
        year = plan.year
        where = f"tarievenkaart {year}"
        repo = RateRepository(self.session)
        card = await repo.get_card(year)
        if card is None:
            card = await self._try(
                where,
                rates.create_rate_card(self.session, year, actor=self.actor),
            )
            if card is None:
                return
            self.result._count(self.result.created, "rate_card")
        current_bands = {b.category: b.monthly_rate_cents for b in card.rate_bands}
        current_scales = {b.scale: b.category for b in card.scale_bands}
        for category, cents in sorted(plan.rate_bands.items()):
            if current_bands.get(category) == cents:
                self.result._count(self.result.unchanged, "rate_band")
                continue
            done = await self._try(
                where,
                rates.set_rate_band(
                    self.session,
                    year,
                    category,
                    cents,
                    actor=self.actor,
                    allow_closed_year=self.allow_closed_year,
                ),
            )
            if done is not None:
                bucket = (
                    self.result.updated
                    if category in current_bands
                    else self.result.created
                )
                self.result._count(bucket, "rate_band")
        for scale, category in sorted(plan.scale_bands.items()):
            if current_scales.get(scale) == category:
                self.result._count(self.result.unchanged, "scale_band")
                continue
            mapped = await self._try(
                where,
                rates.set_scale_band(
                    self.session,
                    year,
                    scale,
                    category,
                    actor=self.actor,
                    allow_closed_year=self.allow_closed_year,
                ),
            )
            if mapped is not None:
                bucket = (
                    self.result.updated
                    if scale in current_scales
                    else self.result.created
                )
                self.result._count(bucket, "scale_band")
        card = await repo.get_card(year)
        if card is not None and card.status == "draft":
            # A draft card does not price; the imported year must.
            await self._try(
                where,
                rates.set_rate_card_status(
                    self.session, year, "active", actor=self.actor
                ),
            )

    # -- people ---------------------------------------------------------------

    async def persons(self) -> None:
        table = self._table("team")
        for person in self.plan.persons:
            where = self._where("team", person.row_id)
            person_id = self.refs.get(table, person.row_id, E_PERSON)
            existing = await self.session.get(Person, person_id) if person_id else None
            if existing is None and not person.placeholder_email:
                # Someone who already has an account (a beheerder, or a
                # person proposed from Wies) is adopted, not duplicated.
                existing = await self.session.scalar(
                    select(Person).where(
                        func.lower(Person.email) == person.email.lower()
                    )
                )
            if existing is None:
                created = await self._try(
                    where,
                    team.create_person(
                        self.session,
                        name=person.name,
                        email=person.email,
                        actor=self.actor,
                    ),
                )
                if created is None:
                    continue
                existing = created
                self.result._count(self.result.created, E_PERSON)
            else:
                changes: dict[str, object] = {}
                if existing.name != person.name:
                    changes["name"] = person.name
                if (
                    not person.placeholder_email
                    and existing.email.lower() != person.email.lower()
                ):
                    changes["email"] = person.email
                if changes:
                    done = await self._try(
                        where,
                        team.update_person(
                            self.session, existing.id, actor=self.actor, changes=changes
                        ),
                    )
                    if done is None:
                        continue
                    self.result._count(self.result.updated, E_PERSON)
                else:
                    self.result._count(self.result.unchanged, E_PERSON)
            if not person.active and existing.is_active:
                await self._try(
                    where,
                    team.update_person(
                        self.session,
                        existing.id,
                        actor=self.actor,
                        changes={"is_active": False},
                    ),
                )
            await self.refs.put(table, person.row_id, E_PERSON, existing.id)
            self.result.persons[person.row_id] = existing.id

        for person in self.plan.persons:
            if person.manager_row is None:
                continue
            person_id = self.result.persons.get(person.row_id)
            manager_id = self.result.persons.get(person.manager_row)
            if person_id is None or manager_id is None or person_id == manager_id:
                continue
            current = await self.session.get(Person, person_id)
            if current is not None and current.manager_id != manager_id:
                await self._try(
                    self._where("team", person.row_id),
                    team.update_person(
                        self.session,
                        person_id,
                        actor=self.actor,
                        changes={"manager_id": manager_id},
                    ),
                )

    async def scales(self) -> None:
        table = self._table("team")
        for scale in self.plan.scales:
            person_id = self.result.persons.get(scale.person_row)
            if person_id is None:
                continue
            where = self._where("team", scale.person_row)
            scale_id = self.refs.get(table, scale.person_row, E_SCALE)
            existing = (
                await self.session.get(PersonScale, scale_id) if scale_id else None
            )
            if existing is None:
                # A person adopted by email may already have this scale.
                existing = await self.session.scalar(
                    select(PersonScale).where(
                        PersonScale.person_id == person_id,
                        PersonScale.valid_from == scale.valid_from,
                    )
                )
            if existing is not None:
                if (
                    existing.billing_scale == scale.billing_scale
                    and existing.valid_from == scale.valid_from
                ):
                    self.result._count(self.result.unchanged, E_SCALE)
                else:
                    self._issue(
                        WARNING,
                        where,
                        f"De inzetschaal is nu {scale.billing_scale} vanaf "
                        f"{scale.valid_from.isoformat()}, in grip staat "
                        f"{existing.billing_scale} vanaf "
                        f"{existing.valid_from.isoformat()}. Schaalhistorie wordt "
                        "niet overschreven; pas het aan in het scherm Team.",
                    )
                await self.refs.put(table, scale.person_row, E_SCALE, existing.id)
                continue
            created = await self._try(
                where,
                rates.set_person_scale(
                    self.session,
                    person_id,
                    scale.valid_from,
                    scale.billing_scale,
                    actor=self.actor,
                    allow_closed_year=self.allow_closed_year,
                ),
            )
            if created is not None:
                await self.refs.put(table, scale.person_row, E_SCALE, created.id)
                self.result._count(self.result.created, E_SCALE)

    async def targets(self) -> None:
        for target in self.plan.targets:
            person_id = self.result.persons.get(target.person_row)
            if person_id is None:
                continue
            current = await self.session.scalar(
                select(BillabilityTarget).where(
                    BillabilityTarget.person_id == person_id,
                    BillabilityTarget.year == target.year,
                )
            )
            if current is not None and not _differs(
                current.target_pct, target.target_pct
            ):
                self.result._count(self.result.unchanged, E_TARGET)
                continue
            done = await self._try(
                self._where("team", target.person_row),
                rates.set_billability_target(
                    self.session,
                    person_id,
                    target.year,
                    target.target_pct,
                    actor=self.actor,
                    allow_closed_year=self.allow_closed_year,
                ),
            )
            if done is not None:
                bucket = self.result.updated if current else self.result.created
                self.result._count(bucket, E_TARGET)

    # -- assignments ----------------------------------------------------------

    def _status_path(self, assignment: Assignment, target: str) -> list[str] | None:
        """The shortest legal series of transitions to the target status."""
        if assignment.status == target:
            return []
        extra = (
            assignments._INTERNAL_EXTRA  # noqa: SLF001 - the rule lives there
            if assignment.kind == "internal"
            else {}
        )
        queue: deque[tuple[str, list[str]]] = deque([(assignment.status, [])])
        seen = {assignment.status}
        while queue:
            status, path = queue.popleft()
            options = assignments.TRANSITIONS[status] | extra.get(status, frozenset())
            for option in sorted(options):
                if option in seen:
                    continue
                if option == target:
                    return [*path, option]
                seen.add(option)
                queue.append((option, [*path, option]))
        return None

    async def _apply_status(self, assignment: Assignment, plan: PlanAssignment) -> None:
        where = self._where("assignments", plan.row_id)
        path = self._status_path(assignment, plan.status)
        if path is None:
            self._issue(
                WARNING,
                where,
                f"Status '{plan.status}' is vanuit '{assignment.status}' niet "
                "bereikbaar; de status in grip is niet gewijzigd.",
            )
            return
        for step in path:
            done = await self._try(
                where,
                assignments.transition(
                    self.session,
                    assignment.id,
                    step,
                    actor=self.actor,
                    reason="Import uit Grist",
                    # Grist never had a client organisation or a start date.
                    enforce_readiness=False,
                ),
            )
            if done is None:
                return

    async def assignments(self) -> None:
        table = self._table("assignments")
        for plan in self.plan.assignments:
            where = self._where("assignments", plan.row_id)
            assignment_id = self.refs.get(table, plan.row_id, E_ASSIGNMENT)
            existing = (
                await self.session.get(Assignment, assignment_id)
                if assignment_id
                else None
            )
            owner_id = (
                self.result.persons.get(plan.owner_row)
                if plan.owner_row is not None
                else None
            )
            if existing is None:
                created = await self._try(
                    where,
                    assignments.create_assignment(
                        self.session,
                        name=plan.name,
                        actor=self.actor,
                        kind=plan.kind,
                        client_contact=plan.client_contact,
                        start_date=plan.start_date,
                        end_date=plan.end_date,
                        notes=plan.notes,
                        owner_id=owner_id,
                    ),
                )
                if created is None:
                    continue
                existing = created
                self.result._count(self.result.created, E_ASSIGNMENT)
                changes: dict[str, Any] = {}
            else:
                changes = {
                    name: value
                    for name, value in (
                        ("name", plan.name),
                        ("kind", plan.kind),
                        ("client_contact", plan.client_contact),
                        ("start_date", plan.start_date),
                        ("end_date", plan.end_date),
                        ("notes", plan.notes),
                    )
                    if getattr(existing, name) != value
                }
            if existing.quoted_amount_cents != plan.quoted_amount_cents:
                changes["quoted_amount_cents"] = plan.quoted_amount_cents
            if changes:
                done = await self._try(
                    where,
                    assignments.update_assignment(
                        self.session, existing.id, actor=self.actor, **changes
                    ),
                )
                if done is None:
                    continue
                if assignment_id:
                    self.result._count(self.result.updated, E_ASSIGNMENT)
            elif assignment_id:
                self.result._count(self.result.unchanged, E_ASSIGNMENT)

            if owner_id is not None and assignment_id:
                has_owner = await self.session.scalar(
                    select(AssignmentRole.id).where(
                        AssignmentRole.assignment_id == existing.id,
                        AssignmentRole.person_id == owner_id,
                        AssignmentRole.role == "owner",
                    )
                )
                if not has_owner:
                    await self._try(
                        where,
                        assignments.set_assignment_role(
                            self.session,
                            existing.id,
                            owner_id,
                            "owner",
                            actor=self.actor,
                        ),
                    )
            await self.refs.put(table, plan.row_id, E_ASSIGNMENT, existing.id)
            self.result.assignments[plan.row_id] = existing.id
            await self._apply_status(existing, plan)

    @staticmethod
    def _line_values(line: PlanLine) -> dict[str, Any]:
        if line.kind == "personnel":
            return {
                "description": line.description,
                "kind": "personnel",
                "position": line.position,
                "role": line.role,
                "fte": line.fte,
                "rate_category": line.rate_category,
                "start_date": line.start_date,
                "end_date": line.end_date,
                "amount_cents": None,
                "year": None,
            }
        return {
            "description": line.description,
            "kind": "fixed",
            "position": line.position,
            "role": None,
            "fte": None,
            "rate_category": None,
            "start_date": None,
            "end_date": None,
            "amount_cents": line.amount_cents,
            "year": line.year,
        }

    async def lines(self) -> None:
        table = self._table("budget_lines")
        for line in self.plan.lines:
            assignment_id = self.result.assignments.get(line.assignment_row)
            if assignment_id is None:
                continue
            where = self._where("budget_lines", line.row_id)
            values = self._line_values(line)
            line_id = self.refs.get(table, line.row_id, E_LINE)
            existing = await self.session.get(BudgetLine, line_id) if line_id else None
            if existing is None:
                created = await self._try(
                    where,
                    assignments.add_budget_line(
                        self.session,
                        assignment_id,
                        actor=self.actor,
                        allow_closed_year=self.allow_closed_year,
                        **values,
                    ),
                )
                if created is None:
                    continue
                existing = created
                self.result._count(self.result.created, E_LINE)
            else:
                changes = {
                    name: value
                    for name, value in values.items()
                    if _differs(getattr(existing, name), value)
                }
                if changes:
                    done = await self._try(
                        where,
                        assignments.update_budget_line(
                            self.session,
                            existing.id,
                            actor=self.actor,
                            allow_closed_year=self.allow_closed_year,
                            **changes,
                        ),
                    )
                    if done is None:
                        continue
                    self.result._count(self.result.updated, E_LINE)
                else:
                    self.result._count(self.result.unchanged, E_LINE)
            await self.refs.put(table, line.row_id, E_LINE, existing.id)
            self.result.lines[line.row_id] = existing.id

    async def allocations(self) -> None:
        table = self._table("allocations")
        for allocation in self.plan.allocations:
            person_id = self.result.persons.get(allocation.person_row)
            line_id = self.result.lines.get(allocation.line_row)
            if person_id is None or line_id is None:
                continue
            where = self._where("allocations", allocation.row_id)
            allocation_id = self.refs.get(table, allocation.row_id, E_ALLOCATION)
            existing = (
                await self.session.get(Allocation, allocation_id)
                if allocation_id
                else None
            )
            if existing is not None and (
                existing.person_id != person_id or existing.budget_line_id != line_id
            ):
                # Another person or line: the service cannot move an
                # allocation, so it is replaced.
                removed = await self._try_remove(
                    where,
                    assignments.delete_allocation(
                        self.session,
                        existing.id,
                        actor=self.actor,
                        allow_closed_year=self.allow_closed_year,
                    ),
                )
                if not removed:
                    continue
                existing = None
            if existing is None:
                created = await self._try(
                    where,
                    assignments.add_allocation(
                        self.session,
                        line_id,
                        person_id,
                        start_date=allocation.start_date,
                        end_date=allocation.end_date,
                        fte_pct=allocation.fte_pct,
                        actor=self.actor,
                        allow_closed_year=self.allow_closed_year,
                    ),
                )
                if created is None:
                    continue
                existing = created
                self.result._count(self.result.created, E_ALLOCATION)
            elif (
                existing.start_date != allocation.start_date
                or existing.end_date != allocation.end_date
                or _differs(existing.fte_pct, allocation.fte_pct)
            ):
                done = await self._try(
                    where,
                    assignments.update_allocation(
                        self.session,
                        existing.id,
                        actor=self.actor,
                        start_date=allocation.start_date,
                        end_date=allocation.end_date,
                        fte_pct=allocation.fte_pct,
                        allow_closed_year=self.allow_closed_year,
                    ),
                )
                if done is None:
                    continue
                self.result._count(self.result.updated, E_ALLOCATION)
            else:
                self.result._count(self.result.unchanged, E_ALLOCATION)
            await self.refs.put(table, allocation.row_id, E_ALLOCATION, existing.id)
            self.result.allocations[allocation.row_id] = existing.id

    # -- costs ----------------------------------------------------------------

    async def cost_items(self) -> None:
        table = self._table("cost_items")
        for item in self.plan.cost_items:
            where = self._where("cost_items", item.row_id)
            cost_id = self.refs.get(table, item.row_id, E_COST)
            existing = await self.session.get(CostItem, cost_id) if cost_id else None
            if existing is None:
                created = await self._try(
                    where,
                    costs.create_cost_item(
                        self.session,
                        description=item.description,
                        budgeted_cents=item.budgeted_cents,
                        actor=self.actor,
                    ),
                )
                if created is None:
                    continue
                existing = created
                self.result._count(self.result.created, E_COST)
            elif (
                existing.description != item.description
                or existing.budgeted_cents != item.budgeted_cents
            ):
                done = await self._try(
                    where,
                    costs.update_cost_item(
                        self.session,
                        existing.id,
                        actor=self.actor,
                        description=item.description,
                        budgeted_cents=item.budgeted_cents,
                    ),
                )
                if done is None:
                    continue
                self.result._count(self.result.updated, E_COST)
            else:
                self.result._count(self.result.unchanged, E_COST)
            await self.refs.put(table, item.row_id, E_COST, existing.id)
            self.result.cost_items[item.row_id] = existing.id

    async def invoice_lines(self) -> None:
        table = self._table("invoice_lines")
        for line in self.plan.invoice_lines:
            cost_id = self.result.cost_items.get(line.cost_row)
            if cost_id is None:
                continue
            where = self._where("invoice_lines", line.row_id)
            invoice_id = self.refs.get(table, line.row_id, E_INVOICE)
            existing = (
                await self.session.get(InvoiceLine, invoice_id) if invoice_id else None
            )
            if existing is not None:
                same = (
                    existing.cost_item_id == cost_id
                    and existing.kind == line.kind
                    and existing.amount_cents == line.amount_cents
                    and existing.reference == line.reference
                    and existing.description == line.description
                    and existing.period == line.period
                )
                if same:
                    self.result._count(self.result.unchanged, E_INVOICE)
                    continue
                # There is no service to change an invoice line: replace it.
                removed = await self._try_remove(
                    where,
                    costs.delete_invoice_line(
                        self.session, existing.id, actor=self.actor
                    ),
                )
                if not removed:
                    continue
            created = await self._try(
                where,
                costs.add_invoice_line(
                    self.session,
                    cost_id,
                    kind=line.kind,
                    amount_cents=line.amount_cents,
                    actor=self.actor,
                    reference=line.reference,
                    description=line.description,
                    period=line.period,
                ),
            )
            if created is None:
                continue
            bucket = (
                self.result.updated if existing is not None else self.result.created
            )
            self.result._count(bucket, E_INVOICE)
            await self.refs.put(table, line.row_id, E_INVOICE, created.id)

    async def coverages(self) -> None:
        table = self._table("coverages")
        # Two Grist rows for the same cost item and budget line are one
        # share in grip; their percentages add up.
        combined: dict[tuple[UUID, UUID], tuple[Decimal, list[int]]] = {}
        for coverage in self.plan.coverages:
            cost_id = self.result.cost_items.get(coverage.cost_row)
            line_id = self.result.lines.get(coverage.line_row)
            if cost_id is None or line_id is None:
                continue
            pct, rows = combined.get((cost_id, line_id), (Decimal(0), []))
            combined[(cost_id, line_id)] = (
                pct + coverage.pct,
                [*rows, coverage.row_id],
            )
        for (cost_id, line_id), (pct, rows) in combined.items():
            where = self._where("coverages", rows[0])
            if len(rows) > 1:
                self._issue(
                    INFO,
                    where,
                    f"{len(rows)} rijen dekken dezelfde kostenpost uit dezelfde "
                    "begrotingsregel; de percentages zijn opgeteld.",
                )
            current = await self.session.scalar(
                select(CostCoverage).where(
                    CostCoverage.cost_item_id == cost_id,
                    CostCoverage.budget_line_id == line_id,
                )
            )
            saved: CostCoverage | None
            if current is not None and not _differs(current.pct, pct):
                self.result._count(self.result.unchanged, E_COVERAGE)
                saved = current
            else:
                saved = await self._try(
                    where,
                    costs.set_coverage(
                        self.session, cost_id, line_id, pct, actor=self.actor
                    ),
                )
                if saved is None:
                    continue
                bucket = (
                    self.result.updated if current is not None else self.result.created
                )
                self.result._count(bucket, E_COVERAGE)
            for row_id in rows:
                await self.refs.put(table, row_id, E_COVERAGE, saved.id)

    async def run(self) -> LoadResult:
        await self.refs.load()
        await self.rates()
        await self.persons()
        await self.scales()
        await self.targets()
        await self.assignments()
        await self.lines()
        await self.allocations()
        await self.cost_items()
        await self.invoice_lines()
        await self.coverages()
        for grist_table, row_id, entity, _ in self.refs.unseen():
            self.result.vanished.append((grist_table, row_id, entity))
            self._issue(
                WARNING,
                f"{grist_table} rij {row_id}",
                f"Deze rij is eerder geladen ({entity}) en staat niet meer in het "
                "document of wordt nu overgeslagen. Grip verwijdert niets; "
                "beoordeel het in grip.",
            )
        return self.result


def _differs(current: Any, new: Any) -> bool:
    if isinstance(current, Decimal) or isinstance(new, Decimal):
        if current is None or new is None:
            return current is not new
        return bool(Decimal(current) != Decimal(new))
    return bool(current != new)


async def load_plan(
    session: AsyncSession,
    plan: ImportPlan,
    *,
    document_key: str,
    actor: Person | None = None,
    allow_closed_year: bool = False,
) -> LoadResult:
    """Apply the plan in the caller's transaction. Does not commit."""
    return await Loader(
        session,
        plan,
        document_key=document_key,
        actor=actor,
        allow_closed_year=allow_closed_year,
    ).run()
