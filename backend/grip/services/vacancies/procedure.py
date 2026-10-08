"""The recruitment procedure: which steps, in which order, how long.

Pure rules, no database. The procedure comes from the request form:

1. Request, advice from HR and concern control, approval.
2. Internal opening for at least five working days.
3. If nobody suitable was found: priority candidates for at least five
   working days, then the government-wide opening and or the external market.

A specialist vacancy may be opened internally and externally at once, with
advice from HR. A vacancy for an intended or ready candidate follows a
separate procedure without openings.

Working days are Monday to Friday. Public holidays are not taken into
account; the minimum is a lower bound, so that errs on the short side by at
most the holidays in the period.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from grip.models.vacancy import StepKind, VacancyType

MIN_OPENING_WORKING_DAYS = 5

# The order of the steps as the form gives them.
STEP_ORDER: tuple[StepKind, ...] = (
    StepKind.request,
    StepKind.hr_advice,
    StepKind.control_advice,
    StepKind.approval,
    StepKind.internal_opening,
    StepKind.priority_candidates,
    StepKind.government_wide_opening,
    StepKind.external_market,
)

_REQUEST_STEPS = STEP_ORDER[:4]

# Steps that must run for a minimum number of working days.
MINIMUM_DURATION: Mapping[StepKind, int] = {
    StepKind.internal_opening: MIN_OPENING_WORKING_DAYS,
    StepKind.priority_candidates: MIN_OPENING_WORKING_DAYS,
}

STEP_LABELS: Mapping[StepKind, str] = {
    StepKind.request: "Aanvraag",
    StepKind.hr_advice: "Advies HR",
    StepKind.control_advice: "Advies concern control",
    StepKind.approval: "Akkoord",
    StepKind.internal_opening: "Interne openstelling",
    StepKind.priority_candidates: "Voorrangskandidaten",
    StepKind.government_wide_opening: "Rijksbrede openstelling",
    StepKind.external_market: "Externe arbeidsmarkt",
}


class ProcedureError(ValueError):
    """A step does not fit the procedure. The message is shown to the user."""


@dataclass(frozen=True)
class StepDates:
    """The dates of a step that was already recorded."""

    started_on: date
    ended_on: date | None = None


def step_position(kind: StepKind) -> int:
    return STEP_ORDER.index(kind) + 1


def applicable_steps(vacancy_type: VacancyType | str) -> tuple[StepKind, ...]:
    """The steps a vacancy of this type goes through."""
    vacancy_type = VacancyType(vacancy_type)
    if vacancy_type in (VacancyType.beoogd, VacancyType.gerede):
        return _REQUEST_STEPS
    return STEP_ORDER


def is_working_day(day: date) -> bool:
    return day.weekday() < 5


def working_days_between(start: date, end: date) -> int:
    """Number of working days from start to end, both included."""
    if end < start:
        return 0
    full_weeks, rest = divmod((end - start).days + 1, 7)
    count = full_weeks * 5
    for offset in range(rest):
        if is_working_day(start + timedelta(days=full_weeks * 7 + offset)):
            count += 1
    return count


def earliest_end(start: date, working_days: int = MIN_OPENING_WORKING_DAYS) -> date:
    """The first day on which a step that started on ``start`` may end."""
    if working_days < 1:
        raise ValueError("working_days must be at least 1")
    day = start
    counted = 1 if is_working_day(day) else 0
    while counted < working_days:
        day += timedelta(days=1)
        if is_working_day(day):
            counted += 1
    return day


def _require(
    existing: Mapping[StepKind, StepDates], needed: StepKind, for_step: StepKind
) -> StepDates:
    if needed not in existing:
        raise ProcedureError(
            f"De stap '{STEP_LABELS[for_step]}' kan pas na de stap "
            f"'{STEP_LABELS[needed]}'."
        )
    return existing[needed]


def _require_finished(
    existing: Mapping[StepKind, StepDates],
    needed: StepKind,
    for_step: StepKind,
    started_on: date,
) -> None:
    previous = _require(existing, needed, for_step)
    if previous.ended_on is None:
        raise ProcedureError(
            f"De stap '{STEP_LABELS[needed]}' is nog niet afgesloten; "
            f"'{STEP_LABELS[for_step]}' kan daarna pas beginnen."
        )
    if started_on <= previous.ended_on:
        raise ProcedureError(
            f"De stap '{STEP_LABELS[for_step]}' begint op zijn vroegst op de dag na "
            f"het einde van '{STEP_LABELS[needed]}'."
        )


def validate_step(
    vacancy_type: VacancyType | str,
    existing: Mapping[StepKind, StepDates],
    kind: StepKind | str,
    started_on: date,
    ended_on: date | None = None,
    *,
    approved: bool = False,
) -> None:
    """Check that a step fits the procedure; raise ProcedureError otherwise.

    ``existing`` holds the other steps of the vacancy (not the one being
    set). ``approved`` says whether the approval was recorded as agreed.
    """
    vacancy_type = VacancyType(vacancy_type)
    kind = StepKind(kind)

    if kind not in applicable_steps(vacancy_type):
        raise ProcedureError(
            f"Een vacature van het type '{vacancy_type.value}' kent de stap "
            f"'{STEP_LABELS[kind]}' niet; daarvoor geldt een aparte procedure."
        )
    if ended_on is not None and ended_on < started_on:
        raise ProcedureError("De einddatum ligt voor de begindatum.")

    minimum = MINIMUM_DURATION.get(kind)
    if minimum and ended_on is not None:
        if working_days_between(started_on, ended_on) < minimum:
            raise ProcedureError(
                f"De stap '{STEP_LABELS[kind]}' duurt minimaal {minimum} werkdagen; "
                f"op zijn vroegst tot en met "
                f"{earliest_end(started_on, minimum).isoformat()}."
            )

    if kind is StepKind.request:
        return

    request = _require(existing, StepKind.request, kind)
    if started_on < request.started_on:
        raise ProcedureError(
            f"De stap '{STEP_LABELS[kind]}' kan niet voor de aanvraag liggen."
        )
    if kind in (StepKind.hr_advice, StepKind.control_advice):
        return
    if kind is StepKind.approval:
        for advice in (StepKind.hr_advice, StepKind.control_advice):
            given = _require(existing, advice, kind)
            if started_on < given.started_on:
                raise ProcedureError(
                    f"Het akkoord kan niet voor de stap '{STEP_LABELS[advice]}' liggen."
                )
        return

    # Everything below is an opening: only after an agreed approval.
    approval = _require(existing, StepKind.approval, kind)
    if not approved:
        raise ProcedureError(
            "De vacature kan pas worden opengesteld als het akkoord is gegeven."
        )
    if started_on < approval.started_on:
        raise ProcedureError(
            f"De stap '{STEP_LABELS[kind]}' kan niet voor het akkoord liggen."
        )
    if kind is StepKind.internal_opening:
        return
    if vacancy_type is VacancyType.specialistisch:
        # May go out internally and externally at once.
        return
    if kind is StepKind.priority_candidates:
        _require_finished(existing, StepKind.internal_opening, kind, started_on)
        return
    _require_finished(existing, StepKind.priority_candidates, kind, started_on)


def next_steps(
    vacancy_type: VacancyType | str, existing: Iterable[StepKind | str]
) -> list[StepKind]:
    """The steps of this vacancy that were not recorded yet, in order."""
    done = {StepKind(kind) for kind in existing}
    return [kind for kind in applicable_steps(vacancy_type) if kind not in done]
