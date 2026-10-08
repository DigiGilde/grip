"""What Wies pulls from grip: assignments, roles, placements and open roles.

Only data classes A and C leave here. The export has no amounts, no rates and
no rate categories, and it has no field to put them in.

Roles
-----
A personnel budget line becomes one role per allocation: the seat that person
fills, with that person's own share and period. Wies counts hours per role,
so this is what makes the hours of a person come out right.

What "open" means
-----------------
On the reference day (today, or the first day of the line when it has not
started yet) the allocations active on that day are added up and compared
with the size of the line. What is left, when it is at least 0.05 FTE, is
exported as one more role that is open and has nobody on it. Its id is the id
of the line followed by ``:open``.

- nothing allocated: one open role for the whole line;
- partly allocated: the filled roles plus an open role for the remainder;
- fully allocated: no open role, unless the line has a published vacancy. The
  vacancy says someone is still being sought, so the line is then open for
  its full size;
- a line that has ended is never open.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings
from grip.models.assignment import (
    ROLE_OWNER,
    Allocation,
    Assignment,
    AssignmentRole,
    BudgetLine,
)
from grip.models.catalogue_role import CatalogueRole
from grip.models.organisation import Organisation
from grip.models.person import Person, person_uri
from grip.models.vacancy import Vacancy, VacancyStatus
from grip.schema.integrations_wies import (
    WiesAssignment,
    WiesExport,
    WiesPlacement,
    WiesRole,
)

# Agreed work, running or done. Drafts, requests, quotes that are still out,
# and rejected or cancelled assignments are no business of Wies.
EXPORTED_STATUSES = ("accepted", "in_progress", "completed", "accounted")
# Below this an unfilled remainder is rounding, not a role someone can take.
OPEN_THRESHOLD = Decimal("0.05")
OPEN_SUFFIX = ":open"


def _fte(value: Decimal) -> str:
    return format(value.normalize(), "f")


def assignment_url(settings: Settings, assignment_id: UUID) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/opdrachten/{assignment_id}"


def _reference_day(line: BudgetLine, today: date) -> date:
    return max(today, line.start_date) if line.start_date else today


def _allocated_fte(allocations: list[Allocation], day: date) -> Decimal:
    return sum(
        (
            a.fte_pct / Decimal(100)
            for a in allocations
            if a.start_date <= day <= a.end_date
        ),
        Decimal(0),
    )


def roles_for_line(
    line: BudgetLine,
    allocations: list[Allocation],
    emails: dict[UUID, str],
    *,
    url: str,
    today: date,
    has_published_vacancy: bool,
    vacancy_title: str | None = None,
    uris: dict[UUID, str] | None = None,
    role_wies_id: str | None = None,
) -> list[WiesRole]:
    """The roles one personnel line becomes in Wies.

    One role per allocation, sized and dated like that allocation, so the
    hours Wies counts for a person are that person's own share of the line.
    Plus one open role for what is left of the line.
    """
    # The role when the line has one. The free text of a line stays in grip
    # then: it may say things about scale or rate that Wies has no business
    # with.
    description = (line.role or line.detail).strip()
    size = line.fte or Decimal(0)
    ended = line.end_date is not None and line.end_date < today

    roles = [
        WiesRole(
            id=str(a.id),
            url=url,
            description=description,
            role_name=line.role,
            role_wies_id=role_wies_id,
            start_date=a.start_date,
            end_date=a.end_date,
            fte=_fte(a.fte_pct / Decimal(100)),
            open=False,
            placements=[
                WiesPlacement(
                    id=str(a.id),
                    # The URI is the key; the address is absent for a
                    # prospective colleague.
                    person_uri=(uris or {}).get(a.person_id),
                    person_email=emails[a.person_id] or None,
                    start_date=a.start_date,
                    end_date=a.end_date,
                )
            ],
        )
        for a in sorted(allocations, key=lambda a: (a.start_date, str(a.id)))
        if a.person_id in emails
    ]
    if ended:
        return roles

    remainder = size - _allocated_fte(allocations, _reference_day(line, today))
    if remainder >= OPEN_THRESHOLD:
        open_fte = remainder
    elif has_published_vacancy:
        open_fte = size
    else:
        return roles
    roles.append(
        WiesRole(
            id=f"{line.id}{OPEN_SUFFIX}",
            url=url,
            description=vacancy_title or description,
            role_name=line.role,
            role_wies_id=role_wies_id,
            start_date=line.start_date,
            end_date=line.end_date,
            fte=_fte(open_fte),
            open=True,
            placements=[],
        )
    )
    return roles


async def build_export(
    db: AsyncSession, settings: Settings, *, today: date | None = None
) -> WiesExport:
    today = today or date.today()

    assignments = (
        (
            await db.execute(
                select(Assignment)
                .where(Assignment.status.in_(EXPORTED_STATUSES))
                .order_by(Assignment.name, Assignment.id)
            )
        )
        .scalars()
        .all()
    )
    assignment_ids = [a.id for a in assignments]

    lines_by_assignment: dict[UUID, list[BudgetLine]] = defaultdict(list)
    allocations_by_line: dict[UUID, list[Allocation]] = defaultdict(list)
    vacancy_by_line: dict[UUID, Vacancy] = {}
    owner_email: dict[UUID, str] = {}
    emails: dict[UUID, str] = {}
    uris: dict[UUID, str] = {}
    tooi: dict[UUID, str | None] = {}
    role_wies_ids: dict[UUID | None, str] = {}
    registry_id: dict[UUID, str | None] = {}

    if assignment_ids:
        lines = (
            (
                await db.execute(
                    select(BudgetLine)
                    .where(
                        BudgetLine.assignment_id.in_(assignment_ids),
                        BudgetLine.kind == "personnel",
                    )
                    .order_by(BudgetLine.position, BudgetLine.id)
                )
            )
            .scalars()
            .all()
        )
        for line in lines:
            lines_by_assignment[line.assignment_id].append(line)
        role_ids = {line.role_id for line in lines if line.role_id}
        if role_ids:
            for role_id, wies_public_id in (
                await db.execute(
                    select(CatalogueRole.id, CatalogueRole.wies_public_id).where(
                        CatalogueRole.id.in_(role_ids),
                        CatalogueRole.wies_public_id.is_not(None),
                    )
                )
            ).all():
                role_wies_ids[role_id] = wies_public_id
        line_ids = [line.id for line in lines]

        if line_ids:
            for allocation in (
                (
                    await db.execute(
                        select(Allocation).where(
                            Allocation.budget_line_id.in_(line_ids)
                        )
                    )
                )
                .scalars()
                .all()
            ):
                allocations_by_line[allocation.budget_line_id].append(allocation)
            for vacancy in (
                (
                    await db.execute(
                        select(Vacancy).where(
                            Vacancy.budget_line_id.in_(line_ids),
                            Vacancy.status == VacancyStatus.open.value,
                            Vacancy.published_at.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            ):
                vacancy_by_line[vacancy.budget_line_id] = vacancy

        person_ids = {
            a.person_id for allocs in allocations_by_line.values() for a in allocs
        }
        owners = (
            await db.execute(
                select(AssignmentRole.assignment_id, AssignmentRole.person_id).where(
                    AssignmentRole.assignment_id.in_(assignment_ids),
                    AssignmentRole.role == ROLE_OWNER,
                )
            )
        ).all()
        person_ids |= {person_id for _, person_id in owners}
        if person_ids:
            for person_id, email, uri in (
                await db.execute(
                    select(Person.id, Person.email, Person.uri).where(
                        Person.id.in_(person_ids)
                    )
                )
            ).all():
                emails[person_id] = (email or "").strip().lower()
                uris[person_id] = uri or person_uri(person_id)
        owner_email = {a_id: emails[p_id] for a_id, p_id in owners if emails.get(p_id)}

        organisation_ids = {a.client_organisation_id for a in assignments} - {None}
        if organisation_ids:
            for org_id, tooi_uri, unit_key, org_registry_id in (
                await db.execute(
                    select(
                        Organisation.id,
                        Organisation.tooi_uri,
                        Organisation.unit_key,
                        Organisation.registry_id,
                    ).where(Organisation.id.in_(organisation_ids))
                )
            ).all():
                tooi[org_id] = tooi_uri
                # A unit added by hand carries the TOOI URI of the registered
                # organisation above it, which is the nearest thing Wies knows.
                if unit_key is None:
                    registry_id[org_id] = org_registry_id

    exported = []
    for assignment in assignments:
        url = assignment_url(settings, assignment.id)
        roles: list[WiesRole] = []
        for line in lines_by_assignment[assignment.id]:
            vacancy = vacancy_by_line.get(line.id)
            roles.extend(
                roles_for_line(
                    line,
                    allocations_by_line[line.id],
                    emails,
                    url=url,
                    today=today,
                    has_published_vacancy=vacancy is not None,
                    vacancy_title=vacancy.function_title if vacancy else None,
                    uris=uris,
                    role_wies_id=role_wies_ids.get(line.role_id),
                )
            )
        exported.append(
            WiesAssignment(
                id=str(assignment.id),
                url=url,
                name=assignment.name,
                status=assignment.status,
                start_date=assignment.start_date,
                end_date=assignment.end_date,
                client_tooi_uri=tooi.get(assignment.client_organisation_id),
                client_registry_id=registry_id.get(assignment.client_organisation_id),
                owner_email=owner_email.get(assignment.id),
                roles=roles,
            )
        )

    return WiesExport(
        generated_at=datetime.now(UTC),
        instance_name=settings.INSTANCE_NAME,
        instance_base_uri=settings.INSTANCE_BASE_URI,
        assignments=exported,
    )
