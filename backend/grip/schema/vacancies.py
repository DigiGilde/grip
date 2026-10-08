"""Request and response schemas for vacancies.

Every response field carries one data class (see ``grip.access.vacancies``
for what the three views on a vacancy mean):

- ``PUBLIC`` (open_role): what every person sees of a published vacancy.
- ``NO_NAMES`` (staffing_counts): the vacancy without any name.
- ``FULL`` (staffing): names, notes, and who requested.
- ``LISTS`` (master_data): value lists and what the viewer may do.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from grip.access import DataClass, in_class, nested
from grip.models.vacancy import (
    ContractType,
    DecisionKind,
    StepKind,
    TextKind,
    VacancyChannel,
    VacancyStatus,
    VacancyType,
)

PUBLIC = in_class(DataClass.OPEN_ROLE)
NO_NAMES = in_class(DataClass.STAFFING_COUNTS)
FULL = in_class(DataClass.STAFFING)
LISTS = in_class(DataClass.MASTER_DATA)


# --- responses ---------------------------------------------------------------


class PublishedTextOut(BaseModel):
    """The established vacancy text, with whether a model drafted it."""

    body: Annotated[str, PUBLIC]
    established_at: Annotated[datetime, PUBLIC]
    model_assisted: Annotated[bool, PUBLIC]
    model_id: Annotated[str | None, PUBLIC] = None
    drafted_at: Annotated[datetime | None, PUBLIC] = None


class ProcedureStepOut(BaseModel):
    """One step of the procedure, recorded or still to come."""

    kind: Annotated[StepKind, NO_NAMES]
    label: Annotated[str, NO_NAMES]
    position: Annotated[int, NO_NAMES]
    recorded: Annotated[bool, NO_NAMES]
    started_on: Annotated[date | None, NO_NAMES] = None
    ended_on: Annotated[date | None, NO_NAMES] = None
    # Set for the steps with a minimum duration (five working days).
    minimum_working_days: Annotated[int | None, NO_NAMES] = None
    # The first day a running step with a minimum duration may end.
    earliest_end: Annotated[date | None, NO_NAMES] = None
    # Free text can hold a name.
    note: Annotated[str | None, FULL] = None


class DecisionOut(BaseModel):
    kind: Annotated[DecisionKind, NO_NAMES]
    label: Annotated[str, NO_NAMES]
    agreed: Annotated[bool | None, NO_NAMES] = None
    decided_on: Annotated[date | None, NO_NAMES] = None
    person_name: Annotated[str, FULL]
    has_account: Annotated[bool, FULL]
    note: Annotated[str | None, FULL] = None


class TextOut(BaseModel):
    """One version of a text, with its origin."""

    id: Annotated[UUID, NO_NAMES]
    kind: Annotated[TextKind, NO_NAMES]
    body: Annotated[str, NO_NAMES]
    # ``human`` or ``model``.
    source: Annotated[str, NO_NAMES]
    model_id: Annotated[str | None, NO_NAMES] = None
    prompt_version: Annotated[str | None, NO_NAMES] = None
    created_at: Annotated[datetime, NO_NAMES]
    based_on_id: Annotated[UUID | None, NO_NAMES] = None
    established_at: Annotated[datetime | None, NO_NAMES] = None
    # True when this version is, or goes back to, a model draft.
    model_assisted: Annotated[bool, NO_NAMES]
    origin_model_id: Annotated[str | None, NO_NAMES] = None
    origin_drafted_at: Annotated[datetime | None, NO_NAMES] = None
    # The version that may leave grip for its kind.
    is_current: Annotated[bool, NO_NAMES]
    created_by_name: Annotated[str | None, FULL] = None
    established_by_name: Annotated[str | None, FULL] = None


class VacancyPermissionsOut(BaseModel):
    """What the viewer may do with this vacancy. Says nothing about others."""

    can_edit: Annotated[bool, PUBLIC]
    can_record_hr_advice: Annotated[bool, PUBLIC]
    can_record_control_advice: Annotated[bool, PUBLIC]
    can_record_approval: Annotated[bool, PUBLIC]
    can_download_form: Annotated[bool, PUBLIC]
    # Whether the vacancy is in a state that allows it, and the viewer may.
    can_withdraw: Annotated[bool, PUBLIC] = False
    can_fill: Annotated[bool, PUBLIC] = False


class VacancySummaryOut(BaseModel):
    """A vacancy in a list."""

    id: Annotated[UUID, PUBLIC]
    function_title: Annotated[str, PUBLIC]
    scale: Annotated[int | None, PUBLIC] = None
    fte: Annotated[Decimal, PUBLIC]
    start_date: Annotated[date | None, PUBLIC] = None
    end_date: Annotated[date | None, PUBLIC] = None
    status: Annotated[VacancyStatus, PUBLIC]
    vacancy_type: Annotated[VacancyType, NO_NAMES]
    declarable: Annotated[bool, NO_NAMES]
    assignment_name: Annotated[str | None, NO_NAMES] = None
    requested_on: Annotated[date | None, NO_NAMES] = None
    # Label of the last recorded step, and of the one that comes next.
    current_step: Annotated[str | None, NO_NAMES] = None
    next_step: Annotated[str | None, NO_NAMES] = None
    requester_name: Annotated[str | None, FULL] = None


class VacancyOut(BaseModel):
    id: Annotated[UUID, PUBLIC]
    function_title: Annotated[str, PUBLIC]
    fgr_function_name: Annotated[str | None, PUBLIC] = None
    scale: Annotated[int | None, PUBLIC] = None
    fte: Annotated[Decimal, PUBLIC]
    start_date: Annotated[date | None, PUBLIC] = None
    end_date: Annotated[date | None, PUBLIC] = None
    status: Annotated[VacancyStatus, PUBLIC]
    published_at: Annotated[datetime | None, PUBLIC] = None
    published_text: Annotated[PublishedTextOut | None, nested()] = None

    declarable: Annotated[bool, NO_NAMES]
    vacancy_type: Annotated[VacancyType, NO_NAMES]
    contract_type: Annotated[ContractType | None, NO_NAMES] = None
    channels: Annotated[list[VacancyChannel], NO_NAMES]
    budget_line_id: Annotated[UUID | None, NO_NAMES] = None
    assignment_id: Annotated[UUID | None, NO_NAMES] = None
    assignment_name: Annotated[str | None, NO_NAMES] = None
    requested_on: Annotated[date | None, NO_NAMES] = None
    created_at: Annotated[datetime, NO_NAMES]
    # Whether this type of vacancy is opened at all (not for an intended or
    # ready candidate).
    has_openings: Annotated[bool, NO_NAMES]

    procedure: Annotated[list[ProcedureStepOut], nested()]
    decisions: Annotated[list[DecisionOut], nested()]
    texts: Annotated[list[TextOut], nested()]

    requester_id: Annotated[UUID | None, FULL] = None
    requester_name: Annotated[str | None, FULL] = None
    addressee_name: Annotated[str | None, FULL] = None

    permissions: Annotated[VacancyPermissionsOut, nested()]


class OpenRoleOut(BaseModel):
    """A published vacancy as every person of the instance sees it."""

    id: Annotated[UUID, PUBLIC]
    function_title: Annotated[str, PUBLIC]
    fgr_function_name: Annotated[str | None, PUBLIC] = None
    scale: Annotated[int | None, PUBLIC] = None
    fte: Annotated[Decimal, PUBLIC]
    start_date: Annotated[date | None, PUBLIC] = None
    end_date: Annotated[date | None, PUBLIC] = None
    published_at: Annotated[datetime | None, PUBLIC] = None
    text: Annotated[PublishedTextOut, nested()]


class UnfilledRoleOut(BaseModel):
    """A personnel budget line with room left: a candidate for a vacancy."""

    budget_line_id: Annotated[UUID, NO_NAMES]
    assignment_id: Annotated[UUID, NO_NAMES]
    assignment_name: Annotated[str, NO_NAMES]
    description: Annotated[str, NO_NAMES]
    role: Annotated[str | None, NO_NAMES] = None
    fte: Annotated[Decimal, NO_NAMES]
    unfilled_fte: Annotated[Decimal, NO_NAMES]
    start_date: Annotated[date | None, NO_NAMES] = None
    end_date: Annotated[date | None, NO_NAMES] = None
    declarable: Annotated[bool, NO_NAMES]


class OptionOut(BaseModel):
    value: Annotated[str, LISTS]
    label: Annotated[str, LISTS]


class StepOptionOut(BaseModel):
    value: Annotated[str, LISTS]
    label: Annotated[str, LISTS]
    minimum_working_days: Annotated[int | None, LISTS] = None


class VacancyOptionsOut(BaseModel):
    """Value lists, and what the viewer may do with vacancies in general."""

    vacancy_types: Annotated[list[OptionOut], nested()]
    contract_types: Annotated[list[OptionOut], nested()]
    statuses: Annotated[list[OptionOut], nested()]
    channels: Annotated[list[OptionOut], nested()]
    decision_kinds: Annotated[list[OptionOut], nested()]
    text_kinds: Annotated[list[OptionOut], nested()]
    steps: Annotated[list[StepOptionOut], nested()]
    # Drafting with the language model is only offered when it is set up.
    drafting_available: Annotated[bool, LISTS]
    # A blank request form is set up, so a filled form can be downloaded.
    request_form_available: Annotated[bool, LISTS]
    # The viewer may create a vacancy that hangs on no budget line.
    can_create_without_budget_line: Annotated[bool, LISTS]
    # The viewer manages form templates and the model configuration.
    can_manage_setup: Annotated[bool, LISTS]


class OpenFormFieldOut(BaseModel):
    source: Annotated[str, FULL]
    label: Annotated[str, FULL]


class RequestFormStatusOut(BaseModel):
    """What a download of the request form would contain."""

    available: Annotated[bool, FULL]
    file_name: Annotated[str | None, FULL] = None
    # What the form asks for and grip has no value for yet.
    open_fields: Annotated[list[OpenFormFieldOut], nested()]
    # The motivation on the form is the established one; a draft is left out.
    motivation_established: Annotated[bool, FULL]


class LanguageModelOut(BaseModel):
    configured: Annotated[bool, LISTS]
    model_id: Annotated[str | None, LISTS] = None
    # Names of the settings that are still empty.
    missing_settings: Annotated[list[str], LISTS]
    organisation_description_set: Annotated[bool, LISTS]
    # Filled when the endpoint was asked for its models.
    available_models: Annotated[list[str] | None, LISTS] = None
    # Why the list of models could not be fetched, if it could not.
    check_error: Annotated[str | None, LISTS] = None


# --- requests ----------------------------------------------------------------


class VacancyCreate(BaseModel):
    """A new vacancy.

    With ``budget_line_id`` the function, FTE and period come from the
    budget line and need not be given. Without it the vacancy is not
    declarable and ``function_title`` and ``fte`` are required.
    """

    budget_line_id: UUID | None = None
    function_title: str | None = Field(default=None, max_length=255)
    fte: Decimal | None = Field(default=None, gt=0, le=99)
    vacancy_type: VacancyType = VacancyType.regulier
    contract_type: ContractType | None = None
    fgr_function_name: str | None = Field(default=None, max_length=255)
    scale: int | None = Field(default=None, ge=1, le=19)
    start_date: date | None = None
    end_date: date | None = None
    addressee_name: str | None = Field(default=None, max_length=255)


class VacancyUpdate(BaseModel):
    function_title: str | None = Field(default=None, max_length=255)
    fte: Decimal | None = Field(default=None, gt=0, le=99)
    vacancy_type: VacancyType | None = None
    contract_type: ContractType | None = None
    fgr_function_name: str | None = Field(default=None, max_length=255)
    scale: int | None = Field(default=None, ge=1, le=19)
    start_date: date | None = None
    end_date: date | None = None
    addressee_name: str | None = Field(default=None, max_length=255)


class SubmitRequest(BaseModel):
    requested_on: date | None = None


class DecisionIn(BaseModel):
    """Who advises or approves, and the decision once it is there.

    Leave ``agreed`` out to record only the name. ``person_id`` (or
    ``person_email``) links the name to an account of this instance, so that
    person can record the decision themselves; the name is then taken from
    the person record. Someone without an account is named in
    ``person_name`` alone.
    """

    person_name: str | None = Field(default=None, min_length=1, max_length=255)
    person_id: UUID | None = None
    person_email: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def _someone_is_named(self) -> DecisionIn:
        if self.person_id is None and not (self.person_name or "").strip():
            raise ValueError("Vul in wie adviseert of akkoord geeft.")
        return self

    agreed: bool | None = None
    note: str | None = Field(default=None, max_length=5000)
    decided_on: date | None = None


class StepIn(BaseModel):
    started_on: date
    ended_on: date | None = None
    note: str | None = Field(default=None, max_length=5000)


class PublishIn(BaseModel):
    channels: list[VacancyChannel] = Field(min_length=1)
    opened_on: date | None = None


class CloseIn(BaseModel):
    """Withdrawing a vacancy or marking it filled, with an optional note."""

    note: str | None = Field(default=None, max_length=1000)


class TextIn(BaseModel):
    kind: TextKind
    body: str = Field(min_length=1, max_length=20000)
    based_on_id: UUID | None = None


class DraftIn(BaseModel):
    kind: TextKind
    # Sent to the model only because the user typed it here for that purpose.
    assignment_summary: str | None = Field(default=None, max_length=4000)
