"""Vacancies: the request, the procedure, the texts and the request form.

Every route decides through ``grip.access``; the rules are in
``grip.access.vacancies``. A vacancy the viewer may not see at all answers
404, so its existence does not leak.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from openai import OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import (
    Action,
    DataClass,
    Decider,
    Resource,
    Subject,
    build_response,
    decide,
    permitted_classes,
    schema_classes,
)
from grip.access.deps import AccessDecider, CurrentSubject, require
from grip.access.vacancies import (
    form_template_resource,
    language_model_resource,
    vacancy_resource,
)
from grip.core import clock
from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.core.problem import problem_response
from grip.models.assignment import BudgetLine
from grip.models.vacancy import (
    ContractType,
    DecisionKind,
    StepKind,
    TextKind,
    TextSource,
    Vacancy,
    VacancyChannel,
    VacancyStatus,
    VacancyText,
    VacancyType,
)
from grip.repositories.vacancy import VacancyRepository
from grip.schema.vacancies import (
    CloseIn,
    DecisionIn,
    DecisionOut,
    DraftIn,
    FilledRoleOut,
    LanguageModelOut,
    OpenFormFieldOut,
    OpenRoleOut,
    OptionOut,
    ProcedureStepOut,
    PublishedTextOut,
    PublishIn,
    RequestFormStatusOut,
    RoleFillerOut,
    StepIn,
    StepOptionOut,
    SubmitRequest,
    TextIn,
    TextOut,
    UnfilledRoleOut,
    VacancyCreate,
    VacancyOptionsOut,
    VacancyOut,
    VacancyPermissionsOut,
    VacancySummaryOut,
    VacancyUpdate,
)
from grip.services import budget_intent
from grip.services import function_framework as framework
from grip.services.errors import DomainValidationError, NotFoundError
from grip.services.llm import (
    LlmNotConfiguredError,
    LlmResponseError,
    get_chat_client,
    is_llm_configured,
    vlam_missing_settings,
)
from grip.services.vacancies import service
from grip.services.vacancies.procedure import (
    MINIMUM_DURATION,
    STEP_LABELS,
    STEP_ORDER,
    applicable_steps,
    earliest_end,
    next_steps,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vacancies", tags=["vacancies"])

_VIEWS = (DataClass.STAFFING, DataClass.STAFFING_COUNTS, DataClass.OPEN_ROLE)

VACANCY_TYPE_LABELS = {
    VacancyType.regulier: "Regulier",
    VacancyType.specialistisch: "Specialistisch",
    VacancyType.beoogd: "Beoogde kandidaat",
    VacancyType.gerede: "Gerede kandidaat",
}
CONTRACT_TYPE_LABELS = {
    ContractType.temporary_project: "Tijdelijk (projectcontract)",
    ContractType.temporary_before_permanent: "Tijdelijk voorafgaand aan vast",
}
STATUS_LABELS = {
    VacancyStatus.draft: "Concept",
    VacancyStatus.requested: "Aangevraagd",
    VacancyStatus.approved: "Akkoord",
    VacancyStatus.rejected: "Afgewezen",
    VacancyStatus.open: "Opengesteld",
    VacancyStatus.filled: "Vervuld",
    VacancyStatus.withdrawn: "Ingetrokken",
}
CHANNEL_LABELS = {
    VacancyChannel.internal: "Intern, binnen de eigen organisatie",
    VacancyChannel.federated: "Andere instanties van grip",
    VacancyChannel.recruitment: "Werving via recruitment",
}
DECISION_LABELS = {
    DecisionKind.hr_advice: "Advies HR",
    DecisionKind.control_advice: "Advies concern control",
    DecisionKind.approval: "Akkoord",
}
TEXT_KIND_LABELS = {
    TextKind.vacancy_text: "Vacaturetekst",
    TextKind.motivation: "Aanleiding en motivatie",
}
# What the request form asks for, by the source name used in a mapping.
FORM_SOURCE_LABELS = {
    "requester_name": "Vacatureaanvrager",
    "request_date": "Datum van de aanvraag",
    "addressee_name": "Aan",
    "declarable": "Declarabele vacature",
    "vacancy_type": "Type vacature",
    "contract_type": "Type contract",
    "function_title": "Functie",
    "fgr_function_name": "FGR-functienaam",
    "scale": "Schaal",
    "fte": "Aantal fte",
    "motivation": "Aanleiding en motivatie (vastgesteld)",
    "hr_adviser_name": "Naam HR-adviseur",
    "hr_decision": "Advies HR",
    "hr_note": "Toelichting HR",
    "controller_name": "Naam controller",
    "control_decision": "Advies concern control",
    "control_note": "Toelichting concern control",
    "approver_name": "Naam van wie akkoord geeft",
    "approval_decision": "Akkoord",
}
# Steps that are set directly. The request and the decisions get their step
# from submitting and from recording a decision.
_OPENING_STEPS = (
    StepKind.internal_opening,
    StepKind.priority_candidates,
    StepKind.government_wide_opening,
    StepKind.external_market,
)


# --- building responses ------------------------------------------------------


def _established(vacancy: Vacancy, kind: TextKind) -> VacancyText | None:
    """The version of a text that was established last, from the loaded texts."""
    candidates = [
        text
        for text in vacancy.texts
        if text.kind == kind.value and text.established_at is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda text: (text.established_at, text.created_at))


def _is_open_role(vacancy: Vacancy) -> bool:
    return (
        vacancy.status == VacancyStatus.open.value
        and vacancy.published_at is not None
        and _established(vacancy, TextKind.vacancy_text) is not None
    )


def _resource(
    vacancy: Vacancy,
    assignment_id: UUID | None,
    *,
    decision_kind: DecisionKind | None = None,
) -> Resource:
    return vacancy_resource(
        vacancy.id,
        assignment_id=assignment_id,
        open_role=_is_open_role(vacancy),
        named={decision.kind: decision.person_id for decision in vacancy.decisions},
        decision_kind=decision_kind.value if decision_kind else None,
        text_reviewers=getattr(vacancy, "text_reviewer_ids", ()),
    )


def _origin(vacancy: Vacancy, text: VacancyText) -> VacancyText | None:
    """The model draft a text goes back to, walking the loaded versions."""
    by_id = {version.id: version for version in vacancy.texts}
    seen: set[UUID] = set()
    current: VacancyText | None = text
    while current is not None and current.id not in seen:
        if current.source == TextSource.model.value:
            return current
        seen.add(current.id)
        current = by_id.get(current.based_on_id) if current.based_on_id else None
    return None


def _published_text(vacancy: Vacancy) -> PublishedTextOut | None:
    text = _established(vacancy, TextKind.vacancy_text)
    if text is None or text.established_at is None:
        return None
    origin = _origin(vacancy, text)
    return PublishedTextOut(
        body=text.body,
        established_at=text.established_at,
        model_assisted=origin is not None,
        model_id=origin.model_id if origin else None,
        drafted_at=origin.created_at if origin else None,
    )


def _procedure(vacancy: Vacancy) -> list[ProcedureStepOut]:
    recorded = {step.kind: step for step in vacancy.steps}
    steps: list[ProcedureStepOut] = []
    for kind in applicable_steps(vacancy.vacancy_type):
        step = recorded.get(kind.value)
        minimum = MINIMUM_DURATION.get(kind)
        steps.append(
            ProcedureStepOut(
                kind=kind,
                label=STEP_LABELS[kind],
                position=STEP_ORDER.index(kind) + 1,
                recorded=step is not None,
                started_on=step.started_on if step else None,
                ended_on=step.ended_on if step else None,
                minimum_working_days=minimum,
                earliest_end=(
                    earliest_end(step.started_on, minimum) if step and minimum else None
                ),
                note=step.note if step else None,
            )
        )
    return steps


def _step_labels(vacancy: Vacancy) -> tuple[str | None, str | None]:
    """Label of the last recorded step and of the step that comes next."""
    recorded = [StepKind(step.kind) for step in vacancy.steps]
    current = max(recorded, key=STEP_ORDER.index) if recorded else None
    upcoming = next_steps(vacancy.vacancy_type, recorded)
    return (
        STEP_LABELS[current] if current else None,
        STEP_LABELS[upcoming[0]] if upcoming else None,
    )


def _standing(vacancy: Vacancy) -> tuple[str | None, str | None, date | None]:
    """The step a vacancy is at, what it waits on, and since when.

    The step is one of the five of the step bar on the vacancy page
    (prepare, submit, decide, open, fill), so the list and the page use the
    same words. No name is part of the detail.
    """
    status = vacancy.status
    created = clock.local_date(vacancy.created_at) if vacancy.created_at else None
    decisions = {decision.kind: decision for decision in vacancy.decisions}
    opens = StepKind.internal_opening in applicable_steps(vacancy.vacancy_type)

    if status == VacancyStatus.draft.value:
        missing = sum(
            1
            for value in (
                vacancy.fgr_function_name,
                vacancy.scale,
                vacancy.contract_type,
                vacancy.addressee_name,
            )
            if value in (None, "")
        )
        if missing:
            detail = (
                "Nog 1 gegeven in te vullen"
                if missing == 1
                else f"Nog {missing} gegevens in te vullen"
            )
            return "prepare", detail, created
        return "submit", "Klaar om aan te vragen", created

    if status == VacancyStatus.requested.value:
        since = vacancy.requested_on
        for kind, waits_on in (
            (DecisionKind.hr_advice, "Wacht op advies HR"),
            (DecisionKind.control_advice, "Wacht op advies concern control"),
            (DecisionKind.approval, "Wacht op akkoord"),
        ):
            decision = decisions.get(kind.value)
            if decision is None or decision.agreed is None:
                return "decide", waits_on, since
            if decision.decided_at is not None:
                since = clock.local_date(decision.decided_at)
        return "decide", "Wacht op akkoord", since

    approval = decisions.get(DecisionKind.approval.value)
    approved_on = (
        clock.local_date(approval.decided_at)
        if approval and approval.decided_at
        else None
    )
    if status == VacancyStatus.approved.value:
        if opens:
            return "open", "Akkoord gegeven, nog niet opengesteld", approved_on
        return "fill", "Akkoord gegeven", approved_on

    if status == VacancyStatus.open.value:
        recorded = [StepKind(step.kind) for step in vacancy.steps]
        running = max(recorded, key=STEP_ORDER.index) if recorded else None
        detail = (
            f"{STEP_LABELS[running]} loopt"
            if running in MINIMUM_DURATION or running in _OPENING_STEPS
            else "Staat open"
        )
        opened = (
            clock.local_date(vacancy.published_at)
            if vacancy.published_at
            else approved_on
        )
        return "fill", detail, opened

    # Ended: nothing is next. The date is when it got there, as far as known.
    ended = clock.local_date(vacancy.updated_at) if vacancy.updated_at else None
    return None, None, ended


def _decisions(vacancy: Vacancy) -> list[DecisionOut]:
    order = [kind.value for kind in DecisionKind]
    return [
        DecisionOut(
            kind=DecisionKind(decision.kind),
            label=DECISION_LABELS[DecisionKind(decision.kind)],
            agreed=decision.agreed,
            decided_on=clock.local_date(decision.decided_at)
            if decision.decided_at
            else None,
            person_name=decision.person_name,
            has_account=decision.person_id is not None,
            note=decision.note,
        )
        for decision in sorted(vacancy.decisions, key=lambda d: order.index(d.kind))
    ]


def _texts(vacancy: Vacancy, names: dict[UUID, str]) -> list[TextOut]:
    current = {
        kind: _established(vacancy, kind)
        for kind in (TextKind.vacancy_text, TextKind.motivation)
    }
    result: list[TextOut] = []
    for text in vacancy.texts:
        origin = _origin(vacancy, text)
        latest = current[TextKind(text.kind)]
        result.append(
            TextOut(
                id=text.id,
                kind=TextKind(text.kind),
                body=text.body,
                source=text.source,
                model_id=text.model_id,
                prompt_version=text.prompt_version,
                created_at=text.created_at,
                based_on_id=text.based_on_id,
                established_at=text.established_at,
                model_assisted=origin is not None,
                origin_model_id=origin.model_id if origin else None,
                origin_drafted_at=origin.created_at if origin else None,
                is_current=latest is not None and latest.id == text.id,
                created_by_name=names.get(text.created_by_id)
                if text.created_by_id
                else None,
                established_by_name=names.get(text.established_by_id)
                if text.established_by_id
                else None,
            )
        )
    return result


async def _permitted(
    decider: Decider, subject: Subject, resource: Resource
) -> frozenset[DataClass]:
    return await permitted_classes(decider, subject, resource, _VIEWS)


async def _assignment_of(
    db: AsyncSession, vacancy: Vacancy
) -> tuple[UUID | None, str | None]:
    if vacancy.budget_line_id is None:
        return None, None
    found = await VacancyRepository(db).assignments_of_budget_lines(
        [vacancy.budget_line_id]
    )
    return found.get(vacancy.budget_line_id, (None, None))


_WITHDRAWABLE = frozenset(
    {
        VacancyStatus.draft.value,
        VacancyStatus.requested.value,
        VacancyStatus.approved.value,
        VacancyStatus.rejected.value,
        VacancyStatus.open.value,
    }
)
_FILLABLE = frozenset({VacancyStatus.approved.value, VacancyStatus.open.value})


async def _permissions(
    decider: Decider,
    subject: Subject,
    vacancy: Vacancy,
    assignment_id: UUID | None,
    permitted: frozenset[DataClass],
) -> VacancyPermissionsOut:
    can_edit = bool(
        await decide(decider, subject, Action.EDIT, _resource(vacancy, assignment_id))
    )
    recordable = vacancy.status != VacancyStatus.draft.value
    can_record: dict[DecisionKind, bool] = {}
    for kind in DecisionKind:
        can_record[kind] = recordable and bool(
            await decide(
                decider,
                subject,
                Action.RECORD_DECISION,
                _resource(vacancy, assignment_id, decision_kind=kind),
            )
        )
    return VacancyPermissionsOut(
        can_edit=can_edit,
        can_record_hr_advice=can_record[DecisionKind.hr_advice],
        can_record_control_advice=can_record[DecisionKind.control_advice],
        can_record_approval=can_record[DecisionKind.approval],
        can_download_form=DataClass.STAFFING in permitted,
        can_withdraw=can_edit and vacancy.status in _WITHDRAWABLE,
        can_fill=can_edit and vacancy.status in _FILLABLE,
    )


async def _vacancy_response(
    db: AsyncSession, decider: Decider, subject: Subject, vacancy: Vacancy
) -> dict[str, Any]:
    assignment_id, assignment_name = await _assignment_of(db, vacancy)
    resource = _resource(vacancy, assignment_id)
    permitted = await _permitted(decider, subject, resource)
    without_names = DataClass.STAFFING_COUNTS in permitted
    names: dict[UUID, str] = {}
    if DataClass.STAFFING in permitted:
        names = await VacancyRepository(db).person_names_by_id(
            pid
            for text in vacancy.texts
            for pid in (text.created_by_id, text.established_by_id)
            if pid is not None
        )
    group = (
        await framework.get_group(db, vacancy.function_group_id)
        if vacancy.function_group_id and without_names
        else None
    )
    # Read now: loading the whole list below refreshes the group.
    family_name = group.family.name if group else None
    group_scales = list(group.scales) if group else None
    line_scales = (
        await framework.budget_line_scales(db, vacancy.budget_line_id)
        if without_names
        else None
    )
    suggested: list[UUID] = []
    if line_scales:
        suggested = [
            candidate.id
            for family in await framework.list_families(db)
            for candidate in family.groups
            if candidate.is_valid_on(clock.today())
            and set(candidate.scales) & set(line_scales)
        ]
    candidate = await service.candidate_of(db, vacancy)
    out = VacancyOut(
        id=vacancy.id,
        function_title=vacancy.function_title,
        fgr_function_name=vacancy.fgr_function_name,
        scale=vacancy.scale,
        fte=Decimal(vacancy.fte),
        start_date=vacancy.start_date,
        end_date=vacancy.end_date,
        status=VacancyStatus(vacancy.status),
        published_at=vacancy.published_at,
        published_text=_published_text(vacancy),
        declarable=vacancy.declarable,
        vacancy_type=VacancyType(vacancy.vacancy_type),
        contract_type=ContractType(vacancy.contract_type)
        if vacancy.contract_type
        else None,
        channels=[VacancyChannel(channel) for channel in vacancy.channels or []],
        budget_line_id=vacancy.budget_line_id,
        assignment_id=assignment_id,
        assignment_name=assignment_name,
        candidate_person_id=candidate[0] if candidate else None,
        candidate_name=candidate[1] if candidate else None,
        requested_on=vacancy.requested_on,
        created_at=vacancy.created_at,
        has_openings=StepKind.internal_opening
        in applicable_steps(vacancy.vacancy_type),
        request_missing=await service.request_missing(db, vacancy),
        function_group_id=vacancy.function_group_id,
        function_family_name=family_name,
        function_group_scales=group_scales,
        scale_deviation_reason=vacancy.scale_deviation_reason,
        suggested_function_group_ids=suggested,
        budget_line_scales=line_scales,
        scale_fits_budget_line=(
            vacancy.scale in line_scales
            if line_scales and vacancy.scale is not None
            else None
        ),
        # The lists below would show how many steps, decisions and versions
        # exist even with every field left out, so they stay empty for a
        # viewer who only gets the public view.
        procedure=_procedure(vacancy) if without_names else [],
        decisions=_decisions(vacancy) if without_names else [],
        texts=_texts(vacancy, names) if without_names else [],
        requester_id=vacancy.requester_id,
        requester_name=vacancy.requester.name if vacancy.requester else None,
        addressee_name=vacancy.addressee_name,
        addressee_has_account=vacancy.addressee_id is not None,
        permissions=await _permissions(
            decider, subject, vacancy, assignment_id, permitted
        ),
    )
    return build_response(out, permitted)


async def _load(
    db: AsyncSession,
    decider: Decider,
    subject: Subject,
    vacancy_id: UUID,
) -> tuple[Vacancy, UUID | None]:
    """The vacancy and its assignment, or 404 when the viewer may not see it."""
    try:
        vacancy = await service.get_vacancy(db, vacancy_id)
    except NotFoundError:
        vacancy = None
    if vacancy is None:
        # Same answer as for a vacancy the viewer may not see.
        await require(
            decider,
            subject,
            Action.READ,
            vacancy_resource(vacancy_id),
            DataClass.STAFFING,
            hide_existence=True,
        )
        raise NotFoundError("Vacature", vacancy_id)
    assignment_id, _name = await _assignment_of(db, vacancy)
    await require(
        decider,
        subject,
        Action.READ,
        _resource(vacancy, assignment_id),
        DataClass.OPEN_ROLE,
        hide_existence=True,
    )
    return vacancy, assignment_id


async def _load_for_edit(
    db: AsyncSession, decider: Decider, subject: Subject, vacancy_id: UUID
) -> tuple[Vacancy, UUID | None]:
    vacancy, assignment_id = await _load(db, decider, subject, vacancy_id)
    await require(decider, subject, Action.EDIT, _resource(vacancy, assignment_id))
    return vacancy, assignment_id


async def _reloaded(
    db: AsyncSession, decider: Decider, subject: Subject, vacancy_id: UUID
) -> dict[str, Any]:
    vacancy = await service.get_vacancy(db, vacancy_id)
    return await _vacancy_response(db, decider, subject, vacancy)


def _options(labels: dict[Any, str]) -> list[OptionOut]:
    return [OptionOut(value=key.value, label=label) for key, label in labels.items()]


# --- collections and value lists ---------------------------------------------


@router.get("", response_model=None)
async def list_vacancies(
    subject: CurrentSubject,
    decider: AccessDecider,
    vacancy_status: VacancyStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """The vacancies the viewer may see, each with the fields they may see.

    Someone without a function or a role on an assignment gets the
    published vacancies only, in their public form.
    """
    vacancies = await service.list_vacancies(db, status=vacancy_status)
    assignments = await VacancyRepository(db).assignments_of_budget_lines(
        v.budget_line_id for v in vacancies if v.budget_line_id is not None
    )
    result: list[dict[str, Any]] = []
    for vacancy in vacancies:
        assignment_id, assignment_name = (
            assignments.get(vacancy.budget_line_id, (None, None))
            if vacancy.budget_line_id
            else (None, None)
        )
        permitted = await _permitted(
            decider, subject, _resource(vacancy, assignment_id)
        )
        if not permitted:
            continue
        current, upcoming = _step_labels(vacancy)
        step, detail, since = _standing(vacancy)
        summary = VacancySummaryOut(
            id=vacancy.id,
            function_title=vacancy.function_title,
            scale=vacancy.scale,
            fte=Decimal(vacancy.fte),
            start_date=vacancy.start_date,
            end_date=vacancy.end_date,
            status=VacancyStatus(vacancy.status),
            vacancy_type=VacancyType(vacancy.vacancy_type),
            declarable=vacancy.declarable,
            budget_line_id=vacancy.budget_line_id,
            assignment_name=assignment_name,
            requested_on=vacancy.requested_on,
            current_step=current,
            next_step=upcoming,
            step=step,
            step_detail=detail,
            step_since=since,
            requester_name=vacancy.requester.name if vacancy.requester else None,
        )
        result.append(build_response(summary, permitted))
    return result


@router.get("/open-roles", response_model=None)
async def list_open_roles(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Published vacancies with their established text, for everyone."""
    vacancies = await service.list_vacancies(db, status=VacancyStatus.open)
    result: list[dict[str, Any]] = []
    for vacancy in vacancies:
        text = _published_text(vacancy)
        if text is None or not _is_open_role(vacancy):
            continue
        # The public view does not depend on the assignment.
        resource = _resource(vacancy, None)
        permitted = await permitted_classes(
            decider, subject, resource, schema_classes(OpenRoleOut)
        )
        if not permitted:
            continue
        role = OpenRoleOut(
            id=vacancy.id,
            function_title=vacancy.function_title,
            fgr_function_name=vacancy.fgr_function_name,
            scale=vacancy.scale,
            fte=Decimal(vacancy.fte),
            start_date=vacancy.start_date,
            end_date=vacancy.end_date,
            published_at=vacancy.published_at,
            text=text,
        )
        result.append(build_response(role, permitted))
    return result


@router.get("/unfilled-roles", response_model=None)
async def list_unfilled_roles(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Budget lines with room left, for which the viewer may open a vacancy."""
    editable: dict[UUID, bool] = {}
    result: list[dict[str, Any]] = []
    unfilled = await service.unfilled_roles(db)
    intended = await VacancyRepository(db).person_names_by_id(
        role.intended_person_id for role in unfilled if role.intended_person_id
    )
    for role in unfilled:
        if role.assignment_id not in editable:
            editable[role.assignment_id] = bool(
                await decide(
                    decider,
                    subject,
                    Action.EDIT,
                    vacancy_resource(None, assignment_id=role.assignment_id),
                )
            )
        if not editable[role.assignment_id]:
            continue
        out = UnfilledRoleOut(
            budget_line_id=role.budget_line_id,
            assignment_id=role.assignment_id,
            assignment_name=role.assignment_name,
            description=role.description,
            role=role.role,
            fte=role.fte,
            unfilled_fte=role.unfilled_fte,
            start_date=role.start_date,
            end_date=role.end_date,
            declarable=role.declarable,
            tentative=role.tentative,
            intended_person_id=role.intended_person_id,
            intended_person_name=intended.get(role.intended_person_id)
            if role.intended_person_id
            else None,
        )
        permitted = await permitted_classes(
            decider,
            subject,
            vacancy_resource(None, assignment_id=role.assignment_id),
            schema_classes(UnfilledRoleOut),
        )
        result.append(build_response(out, permitted))
    return result


@router.get("/filled-roles", response_model=None)
async def list_filled_roles(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Fully staffed budget lines for which the viewer may open a vacancy.

    A vacancy for a filled role starts a replacement or a successor. Who
    fills the role is only in the answer for who may see staffing.
    """
    editable: dict[UUID, bool] = {}
    result: list[dict[str, Any]] = []
    filled = await service.filled_roles(db)
    intended = await VacancyRepository(db).person_names_by_id(
        role.intended_person_id for role in filled if role.intended_person_id
    )
    for role in filled:
        resource = vacancy_resource(None, assignment_id=role.assignment_id)
        if role.assignment_id not in editable:
            editable[role.assignment_id] = bool(
                await decide(decider, subject, Action.EDIT, resource)
            )
        if not editable[role.assignment_id]:
            continue
        out = FilledRoleOut(
            budget_line_id=role.budget_line_id,
            assignment_id=role.assignment_id,
            assignment_name=role.assignment_name,
            description=role.description,
            role=role.role,
            fte=role.fte,
            start_date=role.start_date,
            end_date=role.end_date,
            declarable=role.declarable,
            tentative=role.tentative,
            filled_by=[
                RoleFillerOut(person_name=f.person_name, until=f.until)
                for f in role.filled_by
            ],
            intended_person_id=role.intended_person_id,
            intended_person_name=intended.get(role.intended_person_id)
            if role.intended_person_id
            else None,
        )
        permitted = await permitted_classes(
            decider, subject, resource, schema_classes(FilledRoleOut)
        )
        result.append(build_response(out, permitted))
    return result


@router.get("/options", response_model=None)
async def get_options(
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Value lists with their Dutch labels, and what is set up."""
    collection = vacancy_resource(None)
    await require(decider, subject, Action.READ, collection, DataClass.MASTER_DATA)
    out = VacancyOptionsOut(
        vacancy_types=_options(VACANCY_TYPE_LABELS),
        contract_types=_options(CONTRACT_TYPE_LABELS),
        statuses=_options(STATUS_LABELS),
        channels=_options(CHANNEL_LABELS),
        decision_kinds=_options(DECISION_LABELS),
        text_kinds=_options(TEXT_KIND_LABELS),
        steps=[
            StepOptionOut(
                value=kind.value,
                label=STEP_LABELS[kind],
                minimum_working_days=MINIMUM_DURATION.get(kind),
            )
            for kind in STEP_ORDER
        ],
        drafting_available=is_llm_configured(settings),
        request_form_available=await service.has_active_form_template(db),
        can_create_without_budget_line=bool(
            await decide(decider, subject, Action.EDIT, collection)
        ),
        can_manage_setup=bool(
            await decide(decider, subject, Action.EDIT, form_template_resource())
        ),
    )
    permitted = await permitted_classes(
        decider, subject, collection, schema_classes(VacancyOptionsOut)
    )
    return build_response(out, permitted)


@router.get("/language-model", response_model=None)
async def get_language_model(
    subject: CurrentSubject,
    decider: AccessDecider,
    check: bool = Query(default=False),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """How the language model is set up. Beheerder only.

    With ``check`` the endpoint is asked which models it offers, which also
    shows whether the address and the key work.
    """
    resource = language_model_resource()
    await require(decider, subject, Action.READ, resource, DataClass.MASTER_DATA)
    missing = vlam_missing_settings(settings)
    models: list[str] | None = None
    error: str | None = None
    if check:
        if missing:
            error = "Het taalmodel is nog niet volledig ingesteld."
        else:
            try:
                models = await get_chat_client(settings).list_models()
            except OpenAIError as exc:
                logger.warning(
                    "Listing the models of the language model failed: %s", exc
                )
                error = (
                    "Het taalmodel is niet bereikbaar met het ingestelde adres en "
                    "de ingestelde sleutel."
                )
    out = LanguageModelOut(
        configured=not missing,
        model_id=settings.VLAM_MODEL_ID or None,
        missing_settings=missing,
        organisation_description_set=bool(
            settings.VACANCY_ORGANISATION_DESCRIPTION.strip()
        ),
        available_models=models,
        check_error=error,
    )
    # Reading the model configuration is granted as a whole (beheerder), so
    # every class of the schema is permitted once ``require`` passed.
    return build_response(out, schema_classes(LanguageModelOut))


# --- one vacancy -------------------------------------------------------------


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
async def create_vacancy(
    body: VacancyCreate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Open a vacancy on an unfilled role, or one without a budget line."""
    assignment_id: UUID | None = None
    if body.budget_line_id is not None:
        found = await VacancyRepository(db).assignments_of_budget_lines(
            [body.budget_line_id]
        )
        if body.budget_line_id in found:
            assignment_id = found[body.budget_line_id][0]
    await require(
        decider,
        subject,
        Action.EDIT,
        vacancy_resource(None, assignment_id=assignment_id),
    )

    known_candidate = body.vacancy_type.value in service.KNOWN_CANDIDATE_TYPES
    if body.candidate_person_id is not None and not known_candidate:
        raise DomainValidationError(
            "Een kandidaat hoort alleen bij een vacature voor een beoogde of "
            "gerede kandidaat."
        )
    if known_candidate and body.budget_line_id is not None:
        # The candidate is the intended person of the line: one fact.
        line = await db.get(BudgetLine, body.budget_line_id)
        current = line.intended_person_id if line is not None else None
        chosen = body.candidate_person_id or current
        if chosen is None:
            raise DomainValidationError(
                "Een vacature voor een beoogde of gerede kandidaat heeft een "
                "kandidaat nodig. Kies wie het is."
            )
        if chosen != current and assignment_id is not None:
            # Naming someone on a role is staffing, as on the budget itself.
            await require(
                decider,
                subject,
                Action.READ,
                Resource.person(),
                DataClass.STAFFING_ROSTER,
            )
            await require(
                decider,
                subject,
                Action.EDIT,
                Resource.allocation(assignment_id, chosen),
                DataClass.STAFFING,
            )
            await budget_intent.update_line(
                db, body.budget_line_id, actor=person, intended_person_id=chosen
            )

    if body.budget_line_id is not None:
        vacancy = await service.create_vacancy_from_budget_line(
            db,
            actor=person,
            budget_line_id=body.budget_line_id,
            vacancy_type=body.vacancy_type,
            contract_type=body.contract_type,
            fgr_function_name=body.fgr_function_name,
            scale=body.scale,
            addressee_name=body.addressee_name,
            function_group_id=body.function_group_id,
            scale_deviation_reason=body.scale_deviation_reason,
            addressee_id=body.addressee_id,
        )
        overrides = body.model_dump(
            include={"function_title", "fte", "start_date", "end_date"},
            exclude_none=True,
        )
        if overrides:
            await service.update_vacancy(
                db, vacancy.id, actor=person, changes=overrides
            )
    else:
        if not body.function_title or body.fte is None:
            raise DomainValidationError(
                "Een vacature zonder begrotingsregel heeft een functie en een "
                "aantal fte nodig."
            )
        vacancy = await service.create_vacancy(
            db,
            actor=person,
            function_title=body.function_title,
            fte=body.fte,
            declarable=False,
            vacancy_type=body.vacancy_type,
            contract_type=body.contract_type,
            fgr_function_name=body.fgr_function_name,
            scale=body.scale,
            start_date=body.start_date,
            end_date=body.end_date,
            addressee_name=body.addressee_name,
            function_group_id=body.function_group_id,
            scale_deviation_reason=body.scale_deviation_reason,
            addressee_id=body.addressee_id,
        )
    return await _reloaded(db, decider, subject, vacancy.id)


@router.get("/{vacancy_id}", response_model=None)
async def get_vacancy(
    vacancy_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    vacancy, _assignment_id = await _load(db, decider, subject, vacancy_id)
    return await _vacancy_response(db, decider, subject, vacancy)


@router.patch("/{vacancy_id}", response_model=None)
async def update_vacancy(
    vacancy_id: UUID,
    body: VacancyUpdate,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Change the details of a vacancy. Only the fields that are sent change."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    changes = body.model_dump(exclude_unset=True)
    if changes:
        await service.update_vacancy(db, vacancy_id, actor=person, changes=changes)
    return await _reloaded(db, decider, subject, vacancy_id)


@router.post("/{vacancy_id}/submit", response_model=None)
async def submit_request(
    vacancy_id: UUID,
    body: SubmitRequest,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ask for approval to open the vacancy."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    await service.submit_request(
        db, vacancy_id, actor=person, requested_on=body.requested_on
    )
    return await _reloaded(db, decider, subject, vacancy_id)


@router.put("/{vacancy_id}/decisions/{kind}", response_model=None)
async def record_decision(
    vacancy_id: UUID,
    kind: DecisionKind,
    body: DecisionIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Name the adviser or approver, or record their decision.

    Naming someone is editing the vacancy. The decision itself is recorded
    by a beheerder, or by the person who was named when that person has an
    account.
    """
    vacancy, assignment_id = await _load(db, decider, subject, vacancy_id)
    existing = next((d for d in vacancy.decisions if d.kind == kind.value), None)
    can_edit = bool(
        await decide(decider, subject, Action.EDIT, _resource(vacancy, assignment_id))
    )
    decides = body.agreed is not None or (
        existing is not None and existing.agreed is not None
    )
    if decides:
        await require(
            decider,
            subject,
            Action.RECORD_DECISION,
            _resource(vacancy, assignment_id, decision_kind=kind),
        )
    else:
        await require(decider, subject, Action.EDIT, _resource(vacancy, assignment_id))

    person_name = (body.person_name or "").strip()
    person_id = existing.person_id if existing else None
    if existing is not None and not can_edit:
        # The named person records their own decision; who is named stays.
        person_name = existing.person_name
    elif body.person_id is not None:
        account = await VacancyRepository(db).active_person(body.person_id)
        if account is None:
            raise DomainValidationError(
                "Deze persoon heeft geen actief account in deze instantie."
            )
        person_id = account.id
        person_name = account.name
    elif body.person_email:
        account = await VacancyRepository(db).person_by_email(body.person_email)
        if account is None:
            raise DomainValidationError(
                "Er is geen account met dit e-mailadres. Laat het e-mailadres "
                "leeg als deze persoon grip niet gebruikt."
            )
        person_id = account.id
    elif existing is not None and existing.person_name != person_name:
        # Another name without an account: the link to the old account goes.
        person_id = None

    await service.record_decision(
        db,
        vacancy_id,
        kind,
        actor=person,
        person_name=person_name,
        agreed=body.agreed,
        note=body.note,
        decided_on=body.decided_on,
        person_id=person_id,
    )
    return await _reloaded(db, decider, subject, vacancy_id)


@router.put("/{vacancy_id}/steps/{kind}", response_model=None)
async def set_step(
    vacancy_id: UUID,
    kind: StepKind,
    body: StepIn,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Record an opening step of the procedure, or change its dates."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    if kind not in _OPENING_STEPS:
        raise DomainValidationError(
            "De aanvraag, de adviezen en het akkoord krijgen hun datum bij het "
            "aanvragen en bij het vastleggen van een advies of akkoord."
        )
    await service.set_step(
        db,
        vacancy_id,
        kind,
        started_on=body.started_on,
        ended_on=body.ended_on,
        note=body.note,
    )
    return await _reloaded(db, decider, subject, vacancy_id)


@router.post("/{vacancy_id}/publish", response_model=None)
async def publish_vacancy(
    vacancy_id: UUID,
    body: PublishIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Open the vacancy on the chosen channels."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    await service.publish_vacancy(
        db,
        vacancy_id,
        actor=person,
        channels=body.channels,
        opened_on=body.opened_on,
    )
    return await _reloaded(db, decider, subject, vacancy_id)


@router.post("/{vacancy_id}/withdraw", response_model=None)
async def withdraw_vacancy(
    vacancy_id: UUID,
    body: CloseIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stop the vacancy without filling it."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    await service.withdraw_vacancy(db, vacancy_id, actor=person, note=body.note)
    return await _reloaded(db, decider, subject, vacancy_id)


@router.post("/{vacancy_id}/fill", response_model=None)
async def fill_vacancy(
    vacancy_id: UUID,
    body: CloseIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mark the vacancy as filled."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    await service.fill_vacancy(db, vacancy_id, actor=person, note=body.note)
    return await _reloaded(db, decider, subject, vacancy_id)


# --- texts -------------------------------------------------------------------


@router.post(
    "/{vacancy_id}/texts", response_model=None, status_code=status.HTTP_201_CREATED
)
async def add_text(
    vacancy_id: UUID,
    body: TextIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """A version written by a person, or a draft rewritten into a new version."""
    await _load_for_edit(db, decider, subject, vacancy_id)
    await service.add_text(
        db,
        vacancy_id,
        body.kind,
        actor=person,
        body=body.body,
        based_on_id=body.based_on_id,
    )
    return await _reloaded(db, decider, subject, vacancy_id)


def _model_problem(
    status_code: int, title: str, detail: str, code: str
) -> JSONResponse:
    return problem_response(status_code, detail, title=title, code=code)


@router.post(
    "/{vacancy_id}/texts/draft",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
)
async def draft_text(
    vacancy_id: UUID,
    body: DraftIn,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Ask the language model for a draft.

    The draft is stored as a version with its origin. It is a proposal: it
    cannot leave grip until a person establishes it. No names are sent to
    the model; a summary of the assignment only when the user typed one.
    """
    await _load_for_edit(db, decider, subject, vacancy_id)
    try:
        await service.draft_text(
            db,
            vacancy_id,
            body.kind,
            actor=person,
            assignment_summary=(body.assignment_summary or "").strip() or None,
            organisation_description=(
                settings.VACANCY_ORGANISATION_DESCRIPTION.strip() or None
            ),
        )
    except LlmNotConfiguredError as exc:
        return _model_problem(
            503, "Taalmodel niet ingesteld", str(exc), "LlmNotConfiguredError"
        )
    except LlmResponseError as exc:
        return _model_problem(
            502, "Taalmodel gaf geen bruikbaar antwoord", str(exc), "LlmResponseError"
        )
    except OpenAIError as exc:
        logger.warning("Drafting with the language model failed: %s", exc)
        return _model_problem(
            502,
            "Taalmodel niet bereikbaar",
            "Het taalmodel gaf geen antwoord. Probeer het later opnieuw, of "
            "schrijf de tekst zelf.",
            "LlmUnavailableError",
        )
    return await _reloaded(db, decider, subject, vacancy_id)


@router.post("/{vacancy_id}/texts/{text_id}/establish", response_model=None)
async def establish_text(
    vacancy_id: UUID,
    text_id: UUID,
    person: CurrentPerson,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Take responsibility for this version; only then may it leave grip."""
    vacancy, _assignment_id = await _load_for_edit(db, decider, subject, vacancy_id)
    if not any(text.id == text_id for text in vacancy.texts):
        raise NotFoundError("Tekst", text_id)
    await service.establish_text(db, text_id, actor=person)
    return await _reloaded(db, decider, subject, vacancy_id)


# --- the request form --------------------------------------------------------


async def _load_for_form(
    db: AsyncSession, decider: Decider, subject: Subject, vacancy_id: UUID
) -> Vacancy:
    vacancy, assignment_id = await _load(db, decider, subject, vacancy_id)
    await require(
        decider,
        subject,
        Action.READ,
        _resource(vacancy, assignment_id),
        DataClass.STAFFING,
    )
    return vacancy


@router.get("/{vacancy_id}/request-form/status", response_model=None)
async def request_form_status(
    vacancy_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Whether the form can be generated, and which fields would stay open."""
    vacancy = await _load_for_form(db, decider, subject, vacancy_id)
    motivation = _established(vacancy, TextKind.motivation) is not None
    if not await service.has_active_form_template(db):
        out = RequestFormStatusOut(
            available=False, open_fields=[], motivation_established=motivation
        )
    else:
        form = await service.build_request_form(db, vacancy_id)
        out = RequestFormStatusOut(
            available=True,
            file_name=form.file_name,
            open_fields=[
                OpenFormFieldOut(
                    source=source, label=FORM_SOURCE_LABELS.get(source, source)
                )
                for source in form.open_sources
            ],
            motivation_established=motivation,
        )
    return build_response(out, {DataClass.STAFFING})


def _attachment(file_name: str) -> str:
    """A Content-Disposition value that survives letters outside ASCII."""
    fallback = file_name.encode("ascii", "ignore").decode("ascii") or "formulier.pdf"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(file_name)}"


@router.get("/{vacancy_id}/request-form", response_model=None)
async def download_request_form(
    vacancy_id: UUID,
    subject: CurrentSubject,
    decider: AccessDecider,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The request form of the instance, filled in for this vacancy.

    Generated on demand and never stored: it holds names of colleagues. The
    file stays fillable, so an adviser can complete it outside grip.
    """
    await _load_for_form(db, decider, subject, vacancy_id)
    form = await service.build_request_form(db, vacancy_id)
    return Response(
        content=form.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _attachment(form.file_name),
            "Cache-Control": "no-store",
        },
    )
