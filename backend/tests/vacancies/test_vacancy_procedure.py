"""The steps of the recruitment procedure and the five-working-day minimum."""

from __future__ import annotations

from datetime import date

import pytest

from grip.models.vacancy import StepKind, VacancyType
from grip.services.vacancies.procedure import (
    MIN_OPENING_WORKING_DAYS,
    STEP_ORDER,
    ProcedureError,
    StepDates,
    applicable_steps,
    earliest_end,
    next_steps,
    step_position,
    validate_step,
    working_days_between,
)

MONDAY = date(2026, 10, 5)
FRIDAY = date(2026, 10, 9)


def _day(steps: dict[StepKind, StepDates], kind: StepKind, start, end=None):
    steps[kind] = StepDates(start, end)


def _approved_request() -> dict[StepKind, StepDates]:
    steps: dict[StepKind, StepDates] = {}
    _day(steps, StepKind.request, date(2026, 9, 28), date(2026, 9, 28))
    _day(steps, StepKind.hr_advice, date(2026, 9, 29), date(2026, 9, 29))
    _day(steps, StepKind.control_advice, date(2026, 9, 30), date(2026, 9, 30))
    _day(steps, StepKind.approval, date(2026, 10, 1), date(2026, 10, 1))
    return steps


def test_step_order_follows_the_form():
    assert [kind.value for kind in STEP_ORDER] == [
        "request",
        "hr_advice",
        "control_advice",
        "approval",
        "internal_opening",
        "priority_candidates",
        "government_wide_opening",
        "external_market",
    ]
    assert step_position(StepKind.request) == 1
    assert step_position(StepKind.external_market) == 8


def test_working_days_count_both_ends_and_skip_the_weekend():
    assert working_days_between(MONDAY, FRIDAY) == 5
    assert working_days_between(MONDAY, date(2026, 10, 11)) == 5
    assert working_days_between(MONDAY, date(2026, 10, 12)) == 6
    assert working_days_between(FRIDAY, MONDAY) == 0
    assert working_days_between(date(2026, 10, 10), date(2026, 10, 11)) == 0


def test_earliest_end_of_an_opening():
    assert MIN_OPENING_WORKING_DAYS == 5
    assert earliest_end(MONDAY) == FRIDAY
    # Opened on a Wednesday: the fifth working day is the next Tuesday.
    assert earliest_end(date(2026, 10, 7)) == date(2026, 10, 13)
    # Opened on a Saturday: counting starts on Monday.
    assert earliest_end(date(2026, 10, 10)) == date(2026, 10, 16)


def test_internal_opening_shorter_than_five_working_days_is_refused():
    steps = _approved_request()
    with pytest.raises(ProcedureError, match="minimaal 5 werkdagen"):
        validate_step(
            VacancyType.regulier,
            steps,
            StepKind.internal_opening,
            MONDAY,
            date(2026, 10, 8),
            approved=True,
        )
    validate_step(
        VacancyType.regulier,
        steps,
        StepKind.internal_opening,
        MONDAY,
        FRIDAY,
        approved=True,
    )


def test_an_opening_needs_an_agreed_approval():
    steps = _approved_request()
    with pytest.raises(ProcedureError, match="akkoord"):
        validate_step(VacancyType.regulier, steps, StepKind.internal_opening, MONDAY)
    del steps[StepKind.approval]
    with pytest.raises(ProcedureError, match="Akkoord"):
        validate_step(
            VacancyType.regulier,
            steps,
            StepKind.internal_opening,
            MONDAY,
            approved=True,
        )


def test_approval_needs_both_advices():
    steps: dict[StepKind, StepDates] = {}
    _day(steps, StepKind.request, date(2026, 9, 28))
    _day(steps, StepKind.hr_advice, date(2026, 9, 29))
    with pytest.raises(ProcedureError, match="Advies concern control"):
        validate_step(VacancyType.regulier, steps, StepKind.approval, date(2026, 10, 1))


def test_nothing_before_the_request():
    with pytest.raises(ProcedureError, match="Aanvraag"):
        validate_step(VacancyType.regulier, {}, StepKind.hr_advice, MONDAY)
    steps = {StepKind.request: StepDates(MONDAY)}
    with pytest.raises(ProcedureError, match="voor de aanvraag"):
        validate_step(
            VacancyType.regulier, steps, StepKind.hr_advice, date(2026, 10, 2)
        )


def test_priority_candidates_only_after_the_internal_opening_ended():
    steps = _approved_request()
    _day(steps, StepKind.internal_opening, MONDAY)
    with pytest.raises(ProcedureError, match="nog niet afgesloten"):
        validate_step(
            VacancyType.regulier,
            steps,
            StepKind.priority_candidates,
            date(2026, 10, 12),
            approved=True,
        )
    _day(steps, StepKind.internal_opening, MONDAY, FRIDAY)
    with pytest.raises(ProcedureError, match="dag na"):
        validate_step(
            VacancyType.regulier,
            steps,
            StepKind.priority_candidates,
            FRIDAY,
            approved=True,
        )
    validate_step(
        VacancyType.regulier,
        steps,
        StepKind.priority_candidates,
        date(2026, 10, 12),
        approved=True,
    )


def test_government_wide_and_external_follow_the_priority_candidates():
    steps = _approved_request()
    _day(steps, StepKind.internal_opening, MONDAY, FRIDAY)
    for kind in (StepKind.government_wide_opening, StepKind.external_market):
        with pytest.raises(ProcedureError, match="Voorrangskandidaten"):
            validate_step(
                VacancyType.regulier, steps, kind, date(2026, 10, 19), approved=True
            )
    _day(steps, StepKind.priority_candidates, date(2026, 10, 12), date(2026, 10, 16))
    for kind in (StepKind.government_wide_opening, StepKind.external_market):
        validate_step(
            VacancyType.regulier, steps, kind, date(2026, 10, 19), approved=True
        )


def test_specialist_vacancy_may_go_internal_and_external_at_once():
    steps = _approved_request()
    for kind in (StepKind.internal_opening, StepKind.external_market):
        validate_step(VacancyType.specialistisch, steps, kind, MONDAY, approved=True)


@pytest.mark.parametrize("vacancy_type", [VacancyType.beoogd, VacancyType.gerede])
def test_intended_and_ready_candidate_have_no_openings(vacancy_type):
    assert applicable_steps(vacancy_type) == STEP_ORDER[:4]
    with pytest.raises(ProcedureError, match="aparte procedure"):
        validate_step(
            vacancy_type,
            _approved_request(),
            StepKind.internal_opening,
            MONDAY,
            approved=True,
        )


def test_next_steps_in_order():
    assert next_steps(VacancyType.regulier, ["request", "hr_advice"])[:2] == [
        StepKind.control_advice,
        StepKind.approval,
    ]
    assert next_steps(VacancyType.gerede, [k.value for k in STEP_ORDER[:4]]) == []
