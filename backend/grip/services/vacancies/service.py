"""Vacancies: the request, the procedure, the texts and the request form.

The service layer for vacancies. Routes call these functions; nothing here
knows about HTTP. Every function works in the caller's transaction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.core import clock
from grip.core.audit import CREATE, UPDATE, record_audit
from grip.models.assignment import Assignment, BudgetLine
from grip.models.person import Person
from grip.models.vacancy import (
    ContractType,
    DecisionKind,
    FormTemplate,
    StepKind,
    TextKind,
    TextSource,
    Vacancy,
    VacancyChannel,
    VacancyDecision,
    VacancyStatus,
    VacancyStep,
    VacancyText,
    VacancyType,
)
from grip.repositories.vacancy import FormTemplateRepository, VacancyRepository
from grip.services import events
from grip.services import function_framework as framework
from grip.services.errors import DomainError, DomainValidationError, NotFoundError
from grip.services.llm import ChatClient, get_chat_client
from grip.services.phase import Phase, is_tentative, phase_of
from grip.services.vacancies import form as forms
from grip.services.vacancies.drafting import (
    MAX_EXAMPLES,
    PROMPT_VERSION,
    DraftInput,
    DraftInputError,
    build_prompt,
    ensure_no_person_names,
)
from grip.services.vacancies.procedure import (
    ProcedureError,
    StepDates,
    applicable_steps,
    step_position,
    validate_step,
)

VACANCY_REQUEST_FORM = "vacancy_request"

# Emitted when a vacancy with an established text is published.
VACANCY_PUBLISHED = "vacancy.published"

_DECISION_STEP = {
    DecisionKind.hr_advice: StepKind.hr_advice,
    DecisionKind.control_advice: StepKind.control_advice,
    DecisionKind.approval: StepKind.approval,
}


class TextNotEstablishedError(DomainError):
    def __init__(self, kind: str) -> None:
        label = "vacaturetekst" if kind == TextKind.vacancy_text else "motivatie"
        super().__init__(
            f"De {label} is nog niet vastgesteld. Een concept gaat grip niet uit; "
            "lees de tekst, pas hem aan en stel hem vast."
        )
        self.kind = kind


class NoFormTemplateError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Er is geen leeg aanvraagformulier ingesteld. De beheerder levert het "
            "formulier en de veldkoppeling aan."
        )


@dataclass(frozen=True)
class GeneratedForm:
    file_name: str
    content: bytes
    # Sources the form asks for that grip had no value for.
    open_sources: tuple[str, ...]


def _now() -> datetime:
    return datetime.now(UTC)


async def _get(db: AsyncSession, vacancy_id: UUID) -> Vacancy:
    vacancy = await VacancyRepository(db).get(vacancy_id)
    if vacancy is None:
        raise NotFoundError("Vacature", vacancy_id)
    return vacancy


def _wrap(exc: Exception) -> DomainValidationError:
    return DomainValidationError(str(exc))


# --- the vacancy -----------------------------------------------------------


async def create_vacancy(
    db: AsyncSession,
    *,
    actor: Person | None,
    function_title: str,
    fte: Decimal,
    declarable: bool,
    budget_line_id: UUID | None = None,
    vacancy_type: VacancyType | str = VacancyType.regulier,
    contract_type: ContractType | str | None = None,
    fgr_function_name: str | None = None,
    scale: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    addressee_name: str | None = None,
    function_group_id: UUID | None = None,
    scale_deviation_reason: str | None = None,
    addressee_id: UUID | None = None,
) -> Vacancy:
    if not function_title.strip():
        raise DomainValidationError("Een vacature heeft een functie nodig.")
    if fte <= 0:
        raise DomainValidationError("Het aantal fte moet groter zijn dan nul.")
    if declarable and budget_line_id is None:
        raise DomainValidationError(
            "Een declarabele vacature hoort bij een begrotingsregel."
        )
    if start_date and end_date and end_date < start_date:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    if budget_line_id is not None:
        line = await db.get(BudgetLine, budget_line_id)
        if line is None:
            raise NotFoundError("Begrotingsregel", budget_line_id)
        if line.kind != "personnel":
            raise DomainValidationError(
                "Een vacature kan alleen op een personeelsregel van de begroting."
            )

    vacancy = Vacancy(
        budget_line_id=budget_line_id,
        function_title=function_title.strip(),
        fgr_function_name=fgr_function_name,
        scale=scale,
        fte=fte,
        declarable=declarable,
        vacancy_type=VacancyType(vacancy_type).value,
        contract_type=ContractType(contract_type).value if contract_type else None,
        status=VacancyStatus.draft.value,
        channels=[],
        start_date=start_date,
        end_date=end_date,
        requester_id=actor.id if actor else None,
        addressee_name=addressee_name,
    )
    details: dict[str, Any] = {}
    if function_group_id is not None:
        details["function_group_id"] = function_group_id
    if scale_deviation_reason is not None:
        details["scale_deviation_reason"] = scale_deviation_reason
    if addressee_id is not None:
        details["addressee_id"] = addressee_id
    if details:
        await _apply_request_details(db, vacancy, details)
    db.add(vacancy)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="vacancy",
        entity_id=vacancy.id,
        new_value={"function_title": vacancy.function_title, "fte": str(fte)},
    )
    return vacancy


async def create_vacancy_from_budget_line(
    db: AsyncSession,
    *,
    actor: Person | None,
    budget_line_id: UUID,
    vacancy_type: VacancyType | str = VacancyType.regulier,
    contract_type: ContractType | str | None = None,
    fgr_function_name: str | None = None,
    scale: int | None = None,
    addressee_name: str | None = None,
    function_group_id: UUID | None = None,
    scale_deviation_reason: str | None = None,
    addressee_id: UUID | None = None,
) -> Vacancy:
    """An open role on a budget line becomes a vacancy.

    Function, FTE and period come from the line. The vacancy is declarable
    when the assignment has an external client.
    """
    line = await db.get(BudgetLine, budget_line_id)
    if line is None:
        raise NotFoundError("Begrotingsregel", budget_line_id)
    if line.kind != "personnel" or line.fte is None:
        raise DomainValidationError(
            "Een vacature kan alleen op een personeelsregel van de begroting."
        )
    assignment = await db.get(Assignment, line.assignment_id)
    return await create_vacancy(
        db,
        actor=actor,
        function_title=line.role or line.description,
        fte=Decimal(line.fte),
        declarable=assignment is not None and assignment.kind == "external",
        budget_line_id=line.id,
        vacancy_type=vacancy_type,
        contract_type=contract_type,
        fgr_function_name=fgr_function_name,
        scale=scale,
        start_date=line.start_date,
        end_date=line.end_date,
        addressee_name=addressee_name,
        function_group_id=function_group_id,
        scale_deviation_reason=scale_deviation_reason,
        addressee_id=addressee_id,
    )


async def _apply_request_details(
    db: AsyncSession, vacancy: Vacancy, values: dict[str, Any]
) -> None:
    """Set the function group, the scale and the addressee, and keep them sound.

    - Choosing a function group prints its name on the vacancy. The printed
      name is not touched again when the group is renamed later.
    - A free-text FGR name without a group drops the link to a group.
    - A group with one scale fills in that scale. A scale outside the scales
      of the group is refused unless a reason says why it deviates.
    - An addressee with an account is stored with the name at this moment; a
      free-text name drops the link to an account.
    """
    # Everything is worked out first and assigned at the end, so a refused
    # change leaves the vacancy as it was.
    group_id = vacancy.function_group_id
    fgr_name = vacancy.fgr_function_name
    if "function_group_id" in values:
        group_id = values.pop("function_group_id")
        if group_id is not None:
            chosen = await framework.get_group(db, group_id)
            if not chosen.is_valid_on(clock.today()):
                raise DomainValidationError(
                    f"De functiegroep {chosen.name} is niet meer geldig."
                )
            fgr_name = chosen.name
            values.pop("fgr_function_name", None)
    elif "fgr_function_name" in values:
        group_id = None
    if "fgr_function_name" in values:
        fgr_name = (values.pop("fgr_function_name") or "").strip() or None
    scale = values.pop("scale") if "scale" in values else vacancy.scale
    reason = values.pop("scale_deviation_reason", vacancy.scale_deviation_reason)

    if group_id is None:
        reason = None
    else:
        group = await framework.get_group(db, group_id)
        if scale is None and len(group.scales) == 1:
            scale = group.scales[0]
        reason = framework.check_scale(group, scale, reason)

    addressee_id = vacancy.addressee_id
    addressee_name = vacancy.addressee_name
    if "addressee_id" in values:
        addressee_id = values.pop("addressee_id")
        if addressee_id is not None:
            person = await db.get(Person, addressee_id)
            if person is None or not person.is_active:
                raise NotFoundError("Persoon", addressee_id)
            addressee_name = person.name
            values.pop("addressee_name", None)
    elif "addressee_name" in values:
        addressee_id = None
    if "addressee_name" in values:
        addressee_name = (values.pop("addressee_name") or "").strip() or None

    vacancy.function_group_id = group_id
    vacancy.fgr_function_name = fgr_name
    vacancy.scale = scale
    vacancy.scale_deviation_reason = reason
    vacancy.addressee_id = addressee_id
    vacancy.addressee_name = addressee_name


_REQUEST_DETAILS = (
    "function_group_id",
    "fgr_function_name",
    "scale",
    "scale_deviation_reason",
    "addressee_id",
    "addressee_name",
)

_EDITABLE = (
    "function_title",
    "fgr_function_name",
    "scale",
    "fte",
    "vacancy_type",
    "contract_type",
    "start_date",
    "end_date",
    "addressee_name",
    "function_group_id",
    "scale_deviation_reason",
    "addressee_id",
)


async def update_vacancy(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    actor: Person | None,
    changes: dict[str, Any],
) -> Vacancy:
    """Change the details of a vacancy.

    ``changes`` holds only the fields to change. Once the approval is given
    the request is fixed: the details that went on the form no longer change.
    """
    vacancy = await _get(db, vacancy_id)
    unknown = set(changes) - set(_EDITABLE)
    if unknown:
        raise DomainValidationError(
            "Deze gegevens van een vacature zijn niet te wijzigen: "
            + ", ".join(sorted(unknown))
            + "."
        )
    if vacancy.status not in (
        VacancyStatus.draft.value,
        VacancyStatus.requested.value,
    ):
        raise DomainValidationError(
            "Na het akkoord liggen de gegevens van de aanvraag vast."
        )
    values = dict(changes)
    if "function_title" in values:
        title = (values["function_title"] or "").strip()
        if not title:
            raise DomainValidationError("Een vacature heeft een functie nodig.")
        values["function_title"] = title
    if "fte" in values:
        if values["fte"] is None or values["fte"] <= 0:
            raise DomainValidationError("Het aantal fte moet groter zijn dan nul.")
    if "vacancy_type" in values:
        values["vacancy_type"] = VacancyType(values["vacancy_type"]).value
    if "contract_type" in values and values["contract_type"] is not None:
        values["contract_type"] = ContractType(values["contract_type"]).value
    start = values.get("start_date", vacancy.start_date)
    end = values.get("end_date", vacancy.end_date)
    if start and end and end < start:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")

    touched = list(values)
    old = {name: getattr(vacancy, name) for name in touched}
    details = {name: values.pop(name) for name in _REQUEST_DETAILS if name in values}
    # The details can be refused, so they go first.
    if details:
        await _apply_request_details(db, vacancy, details)
    for name, value in values.items():
        setattr(vacancy, name, value)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy",
        entity_id=vacancy.id,
        old_value={name: _plain(value) for name, value in old.items()},
        new_value={name: _plain(getattr(vacancy, name)) for name in touched},
    )
    return vacancy


def _plain(value: Any) -> Any:
    if isinstance(value, date | Decimal | UUID):
        return str(value)
    return value


async def get_vacancy(db: AsyncSession, vacancy_id: UUID) -> Vacancy:
    vacancy = await _get(db, vacancy_id)
    # Who was asked to review a text: a fact the access rules need, carried
    # on the loaded object (see grip.access.vacancies).
    from grip.models.vacancy_text_flow import VacancyTextReview, VacancyTextVerdict

    rows = await db.scalars(
        select(VacancyTextVerdict.reviewer_id)
        .join(VacancyTextReview, VacancyTextReview.id == VacancyTextVerdict.review_id)
        .where(
            VacancyTextReview.vacancy_id == vacancy.id,
            VacancyTextReview.withdrawn_at.is_(None),
        )
    )
    vacancy.text_reviewer_ids = tuple(set(rows))  # type: ignore[attr-defined]
    return vacancy


async def list_vacancies(
    db: AsyncSession, *, status: VacancyStatus | str | None = None
) -> list[Vacancy]:
    """Every vacancy, newest first, with steps, decisions and texts."""
    value = VacancyStatus(status).value if status else None
    return await VacancyRepository(db).list_full(status=value)


@dataclass(frozen=True)
class UnfilledRole:
    """A personnel budget line that is not fully staffed."""

    budget_line_id: UUID
    assignment_id: UUID
    assignment_name: str
    description: str
    role: str | None
    fte: Decimal
    unfilled_fte: Decimal
    start_date: date | None
    end_date: date | None
    declarable: bool
    # The assignment is not agreed yet: the role may not happen.
    tentative: bool = False
    # The colleague the line is meant for, when one is named.
    intended_person_id: UUID | None = None
    # The stretch of the line's period in which something is unfilled: the
    # whole period, or what is left after someone who stops earlier.
    open_from: date | None = None
    open_until: date | None = None


# A line without an end is looked at this many months ahead at most.
_MONTHS_AHEAD = 120


def _open_stretch(line: Any, day: date) -> tuple[Decimal, date | None, date | None]:
    """What of a personnel line is unfilled from a day on, and in which stretch.

    Counted per month of the line's own period, as the staffing of an
    assignment does: a month that is partly covered counts as covered. The
    amount is the most that is open in any month. Inzet that stops before
    the line ends leaves the rest of the period open; counting everyone who
    has not left yet as filling the whole line hid that.
    """
    asked = Decimal(line.fte)
    live = [a for a in line.allocations if a.end_date >= day]
    if line.end_date is None:
        staffed = sum((Decimal(a.fte_pct) / Decimal(100) for a in live), Decimal(0))
        return asked - staffed, line.start_date, None
    month = Month.of(max(line.start_date or day, day))
    last = Month.of(line.end_date)
    most = Decimal(0)
    first_open: Month | None = None
    last_open: Month | None = None
    for _ in range(_MONTHS_AHEAD):
        if month > last:
            break
        filled = sum(
            (
                Decimal(a.fte_pct) / Decimal(100)
                for a in live
                if a.start_date <= month.last_day and a.end_date >= month.first_day
            ),
            Decimal(0),
        )
        if asked - filled > 0:
            most = max(most, asked - filled)
            first_open = first_open or month
            last_open = month
        month = month.next()
    if first_open is None or last_open is None:
        return Decimal(0), None, None
    start = max(first_open.first_day, line.start_date or first_open.first_day)
    return most, start, min(last_open.last_day, line.end_date)


@dataclass(frozen=True)
class RoleFiller:
    person_id: UUID
    person_name: str
    until: date


@dataclass(frozen=True)
class FilledRole:
    """A personnel budget line that is fully staffed. A vacancy for it is how
    a replacement or a successor starts."""

    budget_line_id: UUID
    assignment_id: UUID
    assignment_name: str
    description: str
    role: str | None
    fte: Decimal
    start_date: date | None
    end_date: date | None
    declarable: bool
    tentative: bool
    filled_by: tuple[RoleFiller, ...]
    intended_person_id: UUID | None = None


_LIVE_STATUSES = (
    VacancyStatus.draft.value,
    VacancyStatus.requested.value,
    VacancyStatus.approved.value,
    VacancyStatus.open.value,
)


async def unfilled_roles(
    db: AsyncSession, *, today: date | None = None
) -> list[UnfilledRole]:
    """Personnel budget lines with room left and no vacancy running yet.

    The staffing of a line is the sum of the allocations that have not ended.
    A line whose own period is over is left out.
    """
    day = today or clock.today()
    repo = VacancyRepository(db)
    taken = await repo.budget_lines_with_vacancy(_LIVE_STATUSES)
    roles: list[UnfilledRole] = []
    for line, assignment in await repo.personnel_lines():
        if line.id in taken or line.fte is None:
            continue
        if line.end_date is not None and line.end_date < day:
            continue
        unfilled, open_from, open_until = _open_stretch(line, day)
        if unfilled <= 0:
            continue
        roles.append(
            UnfilledRole(
                budget_line_id=line.id,
                assignment_id=assignment.id,
                assignment_name=assignment.name,
                description=line.description,
                role=line.role,
                fte=Decimal(line.fte),
                unfilled_fte=unfilled,
                start_date=line.start_date,
                end_date=line.end_date,
                open_from=open_from,
                open_until=open_until,
                declarable=assignment.kind == "external",
                tentative=is_tentative(assignment.status),
                intended_person_id=line.intended_person_id,
            )
        )
    return roles


async def filled_roles(
    db: AsyncSession, *, today: date | None = None
) -> list[FilledRole]:
    """Personnel budget lines without room left and no vacancy running yet.

    The counterpart of ``unfilled_roles``, by the same count. Lines whose own
    period is over and lines of an assignment that has ended are left out.
    """
    day = today or clock.today()
    repo = VacancyRepository(db)
    taken = await repo.budget_lines_with_vacancy(_LIVE_STATUSES)
    found: list[tuple[BudgetLine, Assignment, list[Any]]] = []
    for line, assignment in await repo.personnel_lines():
        if line.id in taken or line.fte is None:
            continue
        if line.end_date is not None and line.end_date < day:
            continue
        if phase_of(assignment.status) is Phase.CLOSED:
            continue
        current = [a for a in line.allocations if a.end_date >= day]
        if not current or _open_stretch(line, day)[0] > 0:
            continue
        found.append((line, assignment, current))
    person_ids = {a.person_id for _, _, current in found for a in current}
    names: dict[UUID, str] = {}
    if person_ids:
        rows = await db.execute(
            select(Person.id, Person.name).where(Person.id.in_(person_ids))
        )
        names = {row[0]: row[1] for row in rows}
    return [
        FilledRole(
            budget_line_id=line.id,
            assignment_id=assignment.id,
            assignment_name=assignment.name,
            description=line.description,
            role=line.role,
            fte=Decimal(line.fte),
            start_date=line.start_date,
            end_date=line.end_date,
            declarable=assignment.kind == "external",
            tentative=is_tentative(assignment.status),
            filled_by=tuple(
                RoleFiller(a.person_id, names.get(a.person_id, ""), a.end_date)
                for a in sorted(current, key=lambda a: (a.end_date, str(a.person_id)))
            ),
            intended_person_id=line.intended_person_id,
        )
        for line, assignment, current in found
    ]


KNOWN_CANDIDATE_TYPES = frozenset({VacancyType.beoogd.value, VacancyType.gerede.value})


async def candidate_of(db: AsyncSession, vacancy: Vacancy) -> tuple[UUID, str] | None:
    """Who a vacancy for a known candidate is for: the intended person of its
    budget line. One fact, kept on the line; a vacancy holds no copy."""
    if vacancy.vacancy_type not in KNOWN_CANDIDATE_TYPES:
        return None
    if vacancy.budget_line_id is None:
        return None
    line = await db.get(BudgetLine, vacancy.budget_line_id)
    if line is None or line.intended_person_id is None:
        return None
    person = await db.get(Person, line.intended_person_id)
    return (person.id, person.name) if person is not None else None


# --- the procedure ---------------------------------------------------------


async def set_step(
    db: AsyncSession,
    vacancy_id: UUID,
    kind: StepKind | str,
    *,
    started_on: date,
    ended_on: date | None = None,
    note: str | None = None,
) -> VacancyStep:
    """Record a step of the procedure, or change its dates."""
    kind = StepKind(kind)
    vacancy = await _get(db, vacancy_id)
    others = {
        StepKind(step.kind): StepDates(step.started_on, step.ended_on)
        for step in vacancy.steps
        if step.kind != kind.value
    }
    approval = next(
        (d for d in vacancy.decisions if d.kind == DecisionKind.approval.value), None
    )
    try:
        validate_step(
            vacancy.vacancy_type,
            others,
            kind,
            started_on,
            ended_on,
            approved=bool(approval and approval.agreed),
        )
    except ProcedureError as exc:
        raise _wrap(exc) from exc

    step = next((s for s in vacancy.steps if s.kind == kind.value), None)
    old = (
        {
            "started_on": step.started_on.isoformat(),
            "ended_on": step.ended_on.isoformat() if step.ended_on else None,
        }
        if step is not None
        else None
    )
    if step is None:
        step = VacancyStep(
            vacancy_id=vacancy.id,
            kind=kind.value,
            position=step_position(kind),
            started_on=started_on,
            ended_on=ended_on,
            note=note,
        )
        vacancy.steps.append(step)
    else:
        step.started_on = started_on
        step.ended_on = ended_on
        if note is not None:
            step.note = note
    await db.flush()
    # The actor is whoever makes the request (grip.events.context).
    record_audit(
        db,
        actor=None,
        action=CREATE if old is None else UPDATE,
        entity="vacancy_step",
        entity_id=step.id,
        old_value=old,
        new_value={
            "kind": kind.value,
            "started_on": started_on.isoformat(),
            "ended_on": ended_on.isoformat() if ended_on else None,
        },
        vacancy_id=vacancy.id,
    )
    return step


# What the request form asks for on the vacancy itself, with the words a
# person reads when it is missing.
REQUEST_FIELDS: tuple[tuple[str, str], ...] = (
    ("fgr_function_name", "FGR-functienaam"),
    ("scale", "schaal"),
    ("contract_type", "type contract"),
    ("addressee_name", "aan wie de aanvraag gericht is"),
)
MOTIVATION_MISSING = "een vastgestelde aanleiding en motivatie"


async def request_missing(db: AsyncSession, vacancy: Vacancy) -> list[str]:
    """What a vacancy still lacks before it can be requested and its request
    form made: the fields the form asks for and a settled motivation, which is
    printed on it. The one list for the service, the screen and the tasks."""
    missing = [
        label for name, label in REQUEST_FIELDS if getattr(vacancy, name) in (None, "")
    ]
    if await established_text(db, vacancy.id, TextKind.motivation) is None:
        missing.append(MOTIVATION_MISSING)
    return missing


def missing_sentence(missing: list[str]) -> str:
    return "Ontbreekt nog: " + ", ".join(missing) + "."


async def submit_request(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    actor: Person | None,
    requested_on: date | None = None,
) -> Vacancy:
    """The requester asks for approval to open the vacancy."""
    vacancy = await _get(db, vacancy_id)
    if vacancy.status != VacancyStatus.draft.value:
        raise DomainValidationError("Deze vacature is al aangevraagd.")
    missing = await request_missing(db, vacancy)
    if missing:
        raise DomainValidationError(
            "De vacature kan nog niet worden aangevraagd. " + missing_sentence(missing)
        )
    day = requested_on or clock.today()
    vacancy.requested_on = day
    vacancy.status = VacancyStatus.requested.value
    if vacancy.requester_id is None and actor is not None:
        vacancy.requester_id = actor.id
    await set_step(db, vacancy.id, StepKind.request, started_on=day, ended_on=day)
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy",
        entity_id=vacancy.id,
        old_value={"status": VacancyStatus.draft.value},
        new_value={"status": vacancy.status},
    )
    return vacancy


async def record_decision(
    db: AsyncSession,
    vacancy_id: UUID,
    kind: DecisionKind | str,
    *,
    actor: Person | None,
    person_name: str,
    agreed: bool | None = None,
    note: str | None = None,
    decided_on: date | None = None,
    person_id: UUID | None = None,
) -> VacancyDecision:
    """Record who advises or approves, and their decision once it is there.

    ``agreed=None`` records only the name, so the form can be generated with
    the adviser filled in and the decision left open.
    """
    kind = DecisionKind(kind)
    if not person_name.strip():
        raise DomainValidationError("Vul in wie adviseert of akkoord geeft.")
    vacancy = await _get(db, vacancy_id)
    if vacancy.status == VacancyStatus.draft.value:
        raise DomainValidationError(
            "Advies en akkoord kunnen pas na de aanvraag worden vastgelegd."
        )

    # Advice and approval are someone else's than the requester's.
    if (
        agreed is not None
        and person_id is not None
        and person_id == vacancy.requester_id
    ):
        raise DomainValidationError(
            "De aanvrager kan niet zelf adviseren of akkoord geven op de eigen "
            "aanvraag. Leg vast wie dat deed."
        )

    decided_at = None
    if agreed is not None:
        day = decided_on or clock.today()
        decided_at = datetime(day.year, day.month, day.day, tzinfo=UTC)
        await set_step(
            db, vacancy.id, _DECISION_STEP[kind], started_on=day, ended_on=day
        )

    decision = next((d for d in vacancy.decisions if d.kind == kind.value), None)
    old = None
    if decision is None:
        decision = VacancyDecision(vacancy_id=vacancy.id, kind=kind.value)
        vacancy.decisions.append(decision)
    else:
        old = {"person_name": decision.person_name, "agreed": decision.agreed}
    decision.person_name = person_name.strip()
    decision.person_id = person_id
    decision.agreed = agreed
    decision.note = note
    decision.decided_at = decided_at
    decision.recorded_by_id = actor.id if actor else None

    if kind is DecisionKind.approval and agreed is not None:
        vacancy.status = (
            VacancyStatus.approved.value if agreed else VacancyStatus.rejected.value
        )
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE if old else CREATE,
        entity="vacancy_decision",
        entity_id=decision.id,
        old_value=old,
        new_value={"kind": kind.value, "agreed": agreed},
    )
    return decision


# --- texts -----------------------------------------------------------------


async def add_text(
    db: AsyncSession,
    vacancy_id: UUID,
    kind: TextKind | str,
    *,
    actor: Person | None,
    body: str,
    based_on_id: UUID | None = None,
) -> VacancyText:
    """A version written or rewritten by a person."""
    kind = TextKind(kind)
    if not body.strip():
        raise DomainValidationError("De tekst is leeg.")
    vacancy = await _get(db, vacancy_id)
    if based_on_id is not None:
        base = await VacancyRepository(db).text(based_on_id)
        if base is None or base.vacancy_id != vacancy.id or base.kind != kind.value:
            raise DomainValidationError(
                "De tekst waarop dit is gebaseerd hoort niet bij deze vacature."
            )
    text = VacancyText(
        vacancy_id=vacancy.id,
        kind=kind.value,
        body=body.strip(),
        source=TextSource.human.value,
        based_on_id=based_on_id,
        created_by_id=actor.id if actor else None,
    )
    db.add(text)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="vacancy_text",
        entity_id=text.id,
        new_value={
            "kind": kind.value,
            "source": TextSource.human.value,
            "based_on_id": str(based_on_id) if based_on_id else None,
        },
        vacancy_id=vacancy.id,
    )
    return text


async def build_draft_input(
    db: AsyncSession,
    vacancy: Vacancy,
    *,
    assignment_summary: str | None = None,
    organisation_description: str | None = None,
    with_examples: bool = True,
) -> DraftInput:
    """Collect what a draft may be based on, and nothing else.

    The summary of the assignment and the description of the organisation are
    given by the caller on purpose: grip does not send free-text notes of an
    assignment to the model on its own.
    """
    repo = VacancyRepository(db)
    assignment_name = None
    if vacancy.budget_line_id is not None:
        line = await db.get(BudgetLine, vacancy.budget_line_id)
        if line is not None:
            assignment = await db.get(Assignment, line.assignment_id)
            assignment_name = assignment.name if assignment else None
    examples: tuple[str, ...] = ()
    if with_examples:
        examples = tuple(
            await repo.example_texts(
                exclude_vacancy_id=vacancy.id,
                kind=TextKind.vacancy_text.value,
                limit=MAX_EXAMPLES,
            )
        )
    return DraftInput(
        role=vacancy.function_title,
        scale_band=f"schaal {vacancy.scale}" if vacancy.scale is not None else None,
        fte=Decimal(vacancy.fte),
        period_start=vacancy.start_date,
        period_end=vacancy.end_date,
        contract_type=(
            ContractType(vacancy.contract_type) if vacancy.contract_type else None
        ),
        assignment_name=assignment_name,
        assignment_summary=assignment_summary,
        organisation_description=organisation_description,
        examples=examples,
    )


async def draft_text(
    db: AsyncSession,
    vacancy_id: UUID,
    kind: TextKind | str,
    *,
    actor: Person | None,
    assignment_summary: str | None = None,
    organisation_description: str | None = None,
    client: ChatClient | None = None,
    extra_names: Iterable[str] = (),
) -> VacancyText:
    """Ask the language model for a draft and store it with its provenance.

    The draft is a proposal. It is not established and cannot leave grip
    until a person establishes it (or a version based on it).
    Raises LlmNotConfiguredError when the instance has no model set up.
    """
    kind = TextKind(kind)
    vacancy = await _get(db, vacancy_id)
    # Fail on missing configuration before anything is collected.
    client = client or get_chat_client()
    try:
        draft_input = await build_draft_input(
            db,
            vacancy,
            assignment_summary=assignment_summary,
            organisation_description=organisation_description,
        )
        names = [*await VacancyRepository(db).person_names(), *extra_names]
        ensure_no_person_names(draft_input, names)
    except DraftInputError as exc:
        raise _wrap(exc) from exc

    system, user = build_prompt(kind, draft_input)
    body = await client.complete(system=system, user=user)
    text = VacancyText(
        vacancy_id=vacancy.id,
        kind=kind.value,
        body=body.strip(),
        source=TextSource.model.value,
        model_id=client.model_id,
        prompt_version=PROMPT_VERSION,
        created_by_id=actor.id if actor else None,
    )
    db.add(text)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="vacancy_text",
        entity_id=text.id,
        new_value={
            "kind": kind.value,
            "source": TextSource.model.value,
            "model_id": client.model_id,
            "prompt_version": PROMPT_VERSION,
        },
    )
    return text


async def establish_text(
    db: AsyncSession, text_id: UUID, *, actor: Person
) -> VacancyText:
    """A person takes responsibility for this version of the text."""
    text = await VacancyRepository(db).text(text_id)
    if text is None:
        raise NotFoundError("Tekst", text_id)
    if text.is_established:
        return text
    text.established_by_id = actor.id
    text.established_at = _now()
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy_text",
        entity_id=text.id,
        new_value={"established": True, "source": text.source},
    )
    return text


async def established_text(
    db: AsyncSession, vacancy_id: UUID, kind: TextKind | str
) -> VacancyText | None:
    return await VacancyRepository(db).established_text(
        vacancy_id, TextKind(kind).value
    )


async def text_for_release(
    db: AsyncSession, vacancy_id: UUID, kind: TextKind | str
) -> VacancyText:
    """The text that may leave grip, or an error when none is established."""
    kind = TextKind(kind)
    text = await established_text(db, vacancy_id, kind)
    if text is None:
        raise TextNotEstablishedError(kind.value)
    return text


async def model_assisted(db: AsyncSession, text: VacancyText) -> VacancyText | None:
    """The model draft this text goes back to, if a model was involved.

    Walks back over the versions a text was based on. Used to show with every
    text whether a language model drafted it, with which model and when.
    """
    repo = VacancyRepository(db)
    seen: set[UUID] = set()
    current: VacancyText | None = text
    while current is not None and current.id not in seen:
        if current.source == TextSource.model.value:
            return current
        seen.add(current.id)
        if current.based_on_id is None:
            return None
        current = await repo.text(current.based_on_id)
    return None


# --- publishing ------------------------------------------------------------


async def publish_vacancy(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    actor: Person | None,
    channels: Iterable[VacancyChannel | str],
    opened_on: date | None = None,
) -> Vacancy:
    """Open the vacancy on the given channels.

    Needs an agreed approval and an established vacancy text. A model draft
    that nobody established blocks publishing.
    """
    vacancy = await _get(db, vacancy_id)
    chosen = sorted({VacancyChannel(channel).value for channel in channels})
    if not chosen:
        raise DomainValidationError("Kies minstens een kanaal.")
    if StepKind.internal_opening not in applicable_steps(vacancy.vacancy_type):
        raise DomainValidationError(
            "Een vacature voor een beoogde of gerede kandidaat wordt niet "
            "opengesteld; daarvoor geldt een aparte procedure."
        )
    if vacancy.status not in (VacancyStatus.approved.value, VacancyStatus.open.value):
        raise DomainValidationError(
            "De vacature kan pas worden opengesteld als het akkoord is gegeven."
        )
    text = await text_for_release(db, vacancy.id, TextKind.vacancy_text)

    day = opened_on or clock.today()
    if not any(s.kind == StepKind.internal_opening.value for s in vacancy.steps):
        await set_step(db, vacancy.id, StepKind.internal_opening, started_on=day)
    old_status = vacancy.status
    vacancy.channels = sorted(set(vacancy.channels or []) | set(chosen))
    vacancy.status = VacancyStatus.open.value
    if vacancy.published_at is None:
        vacancy.published_at = _now()
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy",
        entity_id=vacancy.id,
        old_value={"status": old_status},
        new_value={"status": vacancy.status, "channels": vacancy.channels},
    )
    # The seam with the federation module (ADR 0015). The event type has to
    # be listed in grip.services.events before anything is emitted; until
    # then this is the one call site that will carry it.
    if VACANCY_PUBLISHED in events.EVENT_TYPES:
        await events.emit(
            db,
            VACANCY_PUBLISHED,
            {
                "vacancy_id": str(vacancy.id),
                "text_id": str(text.id),
                "channels": list(vacancy.channels),
            },
        )
    return vacancy


# Where a vacancy can still go. A filled or withdrawn vacancy is final.
_WITHDRAWABLE = (
    VacancyStatus.draft,
    VacancyStatus.requested,
    VacancyStatus.approved,
    VacancyStatus.rejected,
    VacancyStatus.open,
)
# A vacancy for a candidate who is already known is never opened, so it is
# filled straight from the approval.
_FILLABLE = (VacancyStatus.approved, VacancyStatus.open)


async def _close(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    actor: Person | None,
    target: VacancyStatus,
    allowed_from: tuple[VacancyStatus, ...],
    refusal: str,
    note: str | None,
) -> Vacancy:
    vacancy = await _get(db, vacancy_id)
    if vacancy.status not in {status.value for status in allowed_from}:
        raise DomainValidationError(refusal)
    old_status = vacancy.status
    vacancy.status = target.value
    await db.flush()
    new_value: dict[str, Any] = {"status": vacancy.status}
    if note:
        new_value["note"] = note
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="vacancy",
        entity_id=vacancy.id,
        old_value={"status": old_status},
        new_value=new_value,
    )
    return vacancy


async def withdraw_vacancy(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    actor: Person | None,
    note: str | None = None,
) -> Vacancy:
    """Stop the vacancy without filling it. It disappears from the open roles."""
    return await _close(
        db,
        vacancy_id,
        actor=actor,
        target=VacancyStatus.withdrawn,
        allowed_from=_WITHDRAWABLE,
        refusal="Een vervulde of ingetrokken vacature kan niet worden ingetrokken.",
        note=(note or "").strip() or None,
    )


async def fill_vacancy(
    db: AsyncSession,
    vacancy_id: UUID,
    *,
    actor: Person | None,
    note: str | None = None,
) -> Vacancy:
    """Mark the vacancy as filled. It disappears from the open roles.

    Who fills it is not recorded here: the person appears as an allocation on
    the budget line, or as a hire.
    """
    return await _close(
        db,
        vacancy_id,
        actor=actor,
        target=VacancyStatus.filled,
        allowed_from=_FILLABLE,
        refusal=(
            "Een vacature kan pas als vervuld worden gemeld als het akkoord is gegeven."
        ),
        note=(note or "").strip() or None,
    )


# --- the request form ------------------------------------------------------


async def upload_form_template(
    db: AsyncSession,
    *,
    actor: Person | None,
    name: str,
    file_name: str,
    content: bytes,
    mapping: dict[str, Any],
    activate: bool = True,
    clear_values: bool = False,
) -> FormTemplate:
    """Store the blank form of this instance with its field mapping.

    A form that is already filled in is refused, because it holds names of
    people. With ``clear_values`` the values are removed first.
    """
    try:
        parsed = forms.parse_mapping(mapping)
        if clear_values:
            content = forms.clear_form(content)
        forms.check_template(content, parsed)
    except (forms.FormMappingError, forms.FormTemplateError) as exc:
        raise _wrap(exc) from exc

    repo = FormTemplateRepository(db)
    if activate:
        await repo.deactivate_all(VACANCY_REQUEST_FORM)
        await db.flush()
    template = FormTemplate(
        kind=VACANCY_REQUEST_FORM,
        name=name,
        file_name=file_name,
        content=content,
        mapping=mapping,
        uploaded_by_id=actor.id if actor else None,
        is_active=activate,
    )
    db.add(template)
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="form_template",
        entity_id=template.id,
        new_value={"name": name, "file_name": file_name, "is_active": activate},
    )
    return template


async def list_form_templates(db: AsyncSession) -> list[FormTemplate]:
    """The templates of the request form, newest first, without file contents."""
    return await FormTemplateRepository(db).list(VACANCY_REQUEST_FORM)


async def activate_form_template(
    db: AsyncSession, template_id: UUID, *, actor: Person | None
) -> FormTemplate:
    """Make this template the one new forms are generated from."""
    repo = FormTemplateRepository(db)
    template = await repo.get(template_id)
    if template is None:
        raise NotFoundError("Formuliersjabloon", template_id)
    if template.is_active:
        return template
    await repo.deactivate_all(template.kind)
    await db.flush()
    template.is_active = True
    await db.flush()
    record_audit(
        db,
        actor=actor,
        action=UPDATE,
        entity="form_template",
        entity_id=template.id,
        new_value={"is_active": True},
    )
    return template


async def has_active_form_template(db: AsyncSession) -> bool:
    return await FormTemplateRepository(db).active(VACANCY_REQUEST_FORM) is not None


def _decision_values(
    prefix_name: str,
    prefix: str,
    decision: VacancyDecision | None,
    *,
    with_note: bool = True,
) -> dict[str, Any]:
    if decision is None:
        return {}
    values: dict[str, Any] = {prefix_name: decision.person_name}
    if decision.agreed is not None:
        values[f"{prefix}_decision"] = decision.agreed
        if with_note and decision.note:
            values[f"{prefix}_note"] = decision.note
    return values


def form_values(vacancy: Vacancy, *, motivation: str | None) -> dict[str, Any]:
    """The values of a vacancy for the request form, keyed by source name.

    Only what grip knows is included; the rest stays open on the form.
    ``motivation`` must be the established text, never a draft.
    """
    values: dict[str, Any] = {
        "request_date": vacancy.requested_on,
        "addressee_name": vacancy.addressee_name,
        "declarable": vacancy.declarable,
        "vacancy_type": vacancy.vacancy_type,
        "contract_type": vacancy.contract_type,
        "function_title": vacancy.function_title,
        "fgr_function_name": vacancy.fgr_function_name,
        "scale": vacancy.scale,
        "fte": Decimal(vacancy.fte),
        "motivation": motivation,
    }
    if vacancy.requester is not None:
        values["requester_name"] = vacancy.requester.name
    by_kind = {decision.kind: decision for decision in vacancy.decisions}
    values |= _decision_values(
        "hr_adviser_name", "hr", by_kind.get(DecisionKind.hr_advice.value)
    )
    values |= _decision_values(
        "controller_name", "control", by_kind.get(DecisionKind.control_advice.value)
    )
    values |= _decision_values(
        "approver_name",
        "approval",
        by_kind.get(DecisionKind.approval.value),
        with_note=False,
    )
    return {source: value for source, value in values.items() if value is not None}


async def build_request_form(db: AsyncSession, vacancy_id: UUID) -> GeneratedForm:
    """Fill the instance's request form for this vacancy.

    The result stays fillable. It holds names of colleagues, so it belongs
    to data class C and is generated on demand, not stored.
    """
    vacancy = await _get(db, vacancy_id)
    template = await FormTemplateRepository(db).active(VACANCY_REQUEST_FORM)
    if template is None:
        raise NoFormTemplateError()
    motivation = await established_text(db, vacancy.id, TextKind.motivation)
    values = form_values(vacancy, motivation=motivation.body if motivation else None)
    try:
        mapping = forms.parse_mapping(template.mapping)
        content = forms.fill_form(template.content, mapping, values)
    except (forms.FormMappingError, forms.FormTemplateError) as exc:
        raise _wrap(exc) from exc
    open_sources = tuple(sorted({rule.source for rule in mapping.fields} - set(values)))
    slug = "".join(
        ch if ch.isalnum() else "-" for ch in vacancy.function_title.lower()
    ).strip("-")
    return GeneratedForm(
        file_name=f"aanvraagformulier-vacature-{slug or vacancy.id}.pdf",
        content=content,
        open_sources=open_sources,
    )
