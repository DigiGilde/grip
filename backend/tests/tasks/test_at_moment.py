"""The course of a case at a moment, from inputs alone.

No database and no reader: the same rules as the live course, given what held
at that moment, told in the voice of someone with no part in the case.
"""

from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy

from grip.services.quote_approval import (
    ApprovalState,
    current_request,
    requirement_from,
)
from grip.tasks import course, engine, telling
from grip.tasks.cases import (
    AssignmentInputs,
    assignment_snapshot,
    is_client_of,
    outdated_matters,
    quote_in_view,
    quote_open,
)
from grip.tasks.plan import current_plan

TODAY = date(2026, 11, 4)
ASSIGNMENT = uuid.uuid4()
QUOTE = uuid.uuid4()
LINE = uuid.uuid4()
MAKER = uuid.uuid4()
HASH = "a" * 64
REFERENCE = "OFF-2026-0007"
ISSUED_AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
ASKED_AT = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
DECIDED_AT = datetime(2026, 11, 3, 11, 0, tzinfo=UTC)

OWNER = "De eigenaar van de opdracht"


@dataclass(frozen=True)
class _Line:
    id: uuid.UUID = LINE
    kind: str = "personnel"
    position: int = 0
    fte: Decimal | None = Decimal("1")
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = "Ontwikkelaar"
    role: str | None = "Ontwikkelaar"


@dataclass(frozen=True)
class _Quote:
    id: uuid.UUID = QUOTE
    status: str = "issued"
    issued_at: datetime = ISSUED_AT


@dataclass(frozen=True)
class _Request:
    id: uuid.UUID = uuid.UUID(int=1)
    quote_id: uuid.UUID = QUOTE
    status: str = "requested"
    quote_hash: str = HASH
    requested_by_id: uuid.UUID | None = MAKER
    requested_at: datetime = ASKED_AT
    decided_at: datetime | None = None
    reference: str | None = REFERENCE


@dataclass(frozen=True)
class _Allocation:
    start_date: date
    end_date: date
    fte_pct: Decimal = Decimal(100)


def _approval(
    *history: _Request, mode: str = "always", available: bool = True
) -> ApprovalState:
    return ApprovalState(
        requirement=requirement_from(mode, 0, 100_000),
        current=current_request(history, HASH),
        history=history,
        approver_available=available,
        offered=False,
        quote_hash=HASH,
    )


def _inputs(**changes: Any) -> AssignmentInputs:
    return AssignmentInputs(
        **{
            "id": ASSIGNMENT,
            "kind": "external",
            "status": "draft",
            "is_client": False,
            **changes,
        }
    )


def _quoted(**changes: Any) -> AssignmentInputs:
    return _inputs(
        **{
            "status": "quoted",
            "lines": [_Line()],
            "quotes": [_Quote()],
            "valid_until": "2026-12-31",
            **changes,
        }
    )


def _main(inputs: AssignmentInputs) -> course.CourseView:
    return _courses(inputs)[0]


def _courses(inputs: AssignmentInputs) -> list[course.CourseView]:
    plan = current_plan()
    snapshot = assignment_snapshot(inputs, today=TODAY)
    return course.at_moment(snapshot, plan, engine.asked_for(snapshot, plan))


def _steps(found: course.CourseView) -> list[tuple[str, str]]:
    return [(step.key, step.state) for step in found.steps]


def _done(*keys: str) -> list[tuple[str, str]]:
    return [(key, "done") for key in keys]


def _future(*keys: str) -> list[tuple[str, str]]:
    return [(key, "future") for key in keys]


_REQUESTED = _Request()
_APPROVED = replace(_REQUESTED, status="approved", decided_at=DECIDED_AT)
_SENT_BACK = replace(_REQUESTED, status="sent_back", decided_at=DECIDED_AT)

_WALK = [
    pytest.param(
        _inputs(),
        "akkoord",
        [
            ("begroting", "current"),
            *_future("offerte", "aanbieden", "akkoord"),
        ],
        "1 van 4",
        f"{OWNER} is aan zet: de begroting.",
        id="0-created",
    ),
    pytest.param(
        _inputs(lines=[_Line()]),
        "akkoord",
        [
            *_done("begroting"),
            ("offerte", "current"),
            *_future("aanbieden", "akkoord"),
        ],
        "2 van 4",
        f"{OWNER} is aan zet: de offerte.",
        id="1-first-line",
    ),
    pytest.param(
        _quoted(approval=_approval(mode="never")),
        "akkoord",
        [
            *_done("begroting", "offerte"),
            ("aanbieden", "current"),
            *_future("akkoord"),
        ],
        "3 van 4",
        f"{OWNER} is aan zet: het aanbieden van de offerte.",
        id="2a-issued-no-approval-needed",
    ),
    pytest.param(
        _quoted(approval=_approval()),
        "akkoord",
        [
            *_done("begroting", "offerte"),
            ("goedkeuring", "current"),
            *_future("aanbieden", "akkoord"),
        ],
        "3 van 5",
        f"{OWNER} is aan zet: het vragen van interne goedkeuring.",
        id="2b-issued-approval-needed",
    ),
    pytest.param(
        _quoted(approval=_approval(_REQUESTED), approvals=[_REQUESTED]),
        "akkoord",
        [
            *_done("begroting", "offerte"),
            ("goedkeuring", "current"),
            *_future("aanbieden", "akkoord"),
        ],
        "3 van 5",
        "Een interne goedkeurder van offertes is aan zet: "
        f"interne goedkeuring van offerte {REFERENCE}.",
        id="3-approval-requested",
    ),
    pytest.param(
        _quoted(approval=_approval(_APPROVED), approvals=[_APPROVED]),
        "akkoord",
        [
            *_done("begroting", "offerte", "goedkeuring"),
            ("aanbieden", "current"),
            *_future("akkoord"),
        ],
        "4 van 5",
        f"{OWNER} is aan zet: het aanbieden van de offerte.",
        id="4a-approved",
    ),
    pytest.param(
        _quoted(approval=_approval(_SENT_BACK), approvals=[_SENT_BACK]),
        "akkoord",
        [
            *_done("begroting"),
            ("offerte", "current"),
            *_future("goedkeuring", "aanbieden", "akkoord"),
        ],
        "2 van 5",
        "De maker van de offerte is aan zet: een nieuwe offerte.",
        id="4b-sent-back",
    ),
    pytest.param(
        _quoted(approval=_approval(_APPROVED), approvals=[_APPROVED], offered={QUOTE}),
        "akkoord",
        [
            *_done("begroting", "offerte", "goedkeuring", "aanbieden"),
            ("akkoord", "current"),
        ],
        "5 van 5",
        "De opdrachtgever is aan zet: akkoord van de opdrachtgever.",
        id="5-offered",
    ),
    pytest.param(
        _quoted(
            status="accepted",
            quotes=[_Quote(status="accepted")],
            approvals=[_APPROVED],
            offered={QUOTE},
        ),
        "uitvoering",
        [
            *_done("akkoord"),
            ("starten", "current"),
            *_future("uitvoeren", "verantwoorden"),
        ],
        "2 van 4",
        f"{OWNER} is aan zet: de start van de opdracht.",
        id="6-accepted",
    ),
]


@pytest.mark.parametrize(("inputs", "key", "steps", "position", "sentence"), _WALK)
def test_each_step_of_the_winning_path(inputs, key, steps, position, sentence):
    found = _main(inputs)

    assert found.key == key
    assert _steps(found) == steps
    assert found.position == position
    assert found.current_key == next(k for k, state in steps if state == "current")
    assert found.ended is None
    told = found.next
    assert told is not None
    assert told.sentence == sentence
    assert told.part == course.WATCHES
    assert told.who is not None


@pytest.mark.parametrize(("inputs", "key", "steps", "position", "sentence"), _WALK)
def test_the_watcher_hears_no_action_deadline_or_missing_list(
    inputs, key, steps, position, sentence
):
    told = _main(inputs).next

    assert told is not None
    assert told.mine is False
    assert told.action_text is None
    assert told.action_href is None
    assert told.due_on is None
    assert told.overdue is False
    assert told.missing == ()
    assert told.blocked is None
    assert told.may_take_over is False
    assert told.task_id is None
    assert told.since is None
    assert "wacht" not in told.sentence.lower()


def test_a_deadline_the_plan_asks_for_is_not_told_to_a_watcher():
    inputs = _quoted(approval=_approval(_REQUESTED), approvals=[_REQUESTED])
    plan = current_plan()
    snapshot = assignment_snapshot(inputs, today=TODAY)
    review = next(
        item
        for item in engine.asked_for(snapshot, plan)
        if item.template.key == "offerte.intern_beoordelen"
    )

    assert review.due_on == date(2026, 11, 5)
    assert _main(inputs).next.due_on is None


@pytest.mark.parametrize("status", ["in_progress", "completed", "accounted"])
def test_started_tells_the_steps_and_not_whose_turn_it_is(status):
    allocation = _Allocation(date(2026, 1, 1), date(2026, 12, 31))
    inputs = _quoted(
        status=status,
        quotes=[_Quote(status="accepted")],
        offered={QUOTE},
        role_allocations={LINE: [allocation]},
        month_allocations=[allocation],
    )

    courses = _courses(inputs)

    assert courses[0].steps
    for found in courses:
        assert found.next is None
        assert found.more_to_do == 0
        assert found.more_waiting == 0


def test_started_keeps_the_course_where_it_stands():
    found = _main(
        _quoted(
            status="in_progress",
            quotes=[_Quote(status="accepted")],
            offered={QUOTE},
        )
    )

    assert found.key == "uitvoering"
    assert found.position == "3 van 4"
    assert _steps(found) == [
        *_done("akkoord", "starten"),
        ("uitvoeren", "current"),
        ("verantwoorden", "future"),
    ]


def test_what_waits_behind_the_step_is_counted_until_the_start():
    found = _main(
        _quoted(status="accepted", quotes=[_Quote(status="accepted")], offered={QUOTE})
    )

    # Starting is next; the open role of the next step waits behind it.
    assert found.next.task_key == "uitvoering.starten"
    assert found.more_to_do == 0
    assert found.more_waiting == 1


def test_a_rejected_quote_is_a_step_back_with_a_note():
    found = _main(_quoted(status="rejected", quotes=[_Quote(status="rejected")]))

    assert found.current_key == "offerte"
    assert found.position == "2 van 4"
    assert next(s.note for s in found.steps if s.key == "offerte") == (
        "Vorige offerte afgewezen"
    )
    assert found.next.sentence == (
        f"{OWNER} is aan zet: een nieuwe offerte na de afwijzing."
    )


def test_a_new_quote_after_a_rejection_is_a_new_round():
    rejected = _Quote(id=uuid.uuid4(), status="rejected")
    later = _Quote(issued_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC))
    snapshot = assignment_snapshot(
        _quoted(quotes=[rejected, later], approval=_approval(mode="never")),
        today=TODAY,
    )

    assert snapshot.subjects_of("quote_round")[0].repeat_key == "ronde-2"
    assert snapshot.subjects_of("rejected_quote")[0].facts["quote_superseded"] is True
    assert _main(
        _quoted(quotes=[rejected, later], approval=_approval(mode="never"))
    ).next.headline == ("Het aanbieden van de offerte")


def test_an_outdated_quote_leads_back_with_its_own_words():
    found = _main(
        _quoted(approval=_approval(mode="never"), offered={QUOTE}, budget_moved=True)
    )

    assert found.current_key == "offerte"
    assert next(s.note for s in found.steps if s.key == "offerte") == (
        "Begroting gewijzigd na de offerte"
    )
    assert found.next.headline == "Een nieuwe offerte"
    # The quote that was offered stays offered: the step behind reads done.
    assert ("aanbieden", "done") in _steps(found)


def test_an_expired_quote_leads_back_with_its_own_words():
    found = _main(_quoted(approval=_approval(mode="never"), valid_until="2026-11-03"))

    assert found.current_key == "offerte"
    assert next(s.note for s in found.steps if s.key == "offerte") == "Offerte verlopen"
    assert found.next.headline == "Een nieuwe offerte"


def test_a_quote_valid_through_today_has_not_expired():
    found = _main(_quoted(approval=_approval(mode="never"), valid_until="2026-11-04"))

    assert found.current_key == "aanbieden"


def test_a_verbal_agreement_is_noted_and_changes_what_is_awaited():
    found = _main(
        _quoted(
            status="verbally_agreed",
            approval=_approval(mode="never"),
            offered={QUOTE},
        )
    )

    assert found.current_key == "akkoord"
    assert next(s.note for s in found.steps if s.key == "akkoord") == (
        "Mondeling akkoord"
    )
    assert found.next.sentence == (
        "De opdrachtgever is aan zet: het getekende akkoord."
    )


def test_nobody_to_approve_is_a_fact_of_the_moment():
    inputs = _quoted(approval=_approval(available=False))
    snapshot = assignment_snapshot(inputs, today=TODAY)

    assert snapshot.facts["no_approver"] is True
    wanted = engine.asked_for(snapshot, current_plan())
    assert {item.situation for item in wanted} >= {"no_approver"}
    assert _main(inputs).next.headline == "Het vragen van interne goedkeuring"


def test_a_cancelled_case_says_how_it_ended_and_nothing_else():
    found = _main(_inputs(status="cancelled"))

    assert found.ended == "Niet doorgegaan"
    assert found.next is None


def test_a_client_is_not_asked_about_approval_or_the_budget():
    inputs = _quoted(
        is_client=True, approval=_approval(), budget_moved=True, approvals=[]
    )
    snapshot = assignment_snapshot(inputs, today=TODAY)

    assert snapshot.facts["client"] is True
    assert snapshot.facts["approval_needed"] is False
    assert snapshot.subjects_of("quote_round")[0].facts["quote_outdated"] is False
    assert snapshot.facts["quote_received"] is True


def test_an_answered_quote_is_not_asked_about_approval_validity_or_the_budget():
    snapshot = assignment_snapshot(
        _quoted(
            status="accepted",
            quotes=[_Quote(status="accepted")],
            approval=_approval(),
            valid_until="2026-01-01",
            budget_moved=True,
        ),
        today=TODAY,
    )

    round_facts = snapshot.subjects_of("quote_round")[0].facts
    assert snapshot.facts["approval_needed"] is False
    assert round_facts["quote_expired"] is False
    assert round_facts["quote_outdated"] is False
    assert round_facts["quote_accepted"] is True


# --- the two uses of allocations ---------------------------------------------------


def test_allocations_for_a_role_do_not_make_months_to_close():
    allocation = _Allocation(date(2026, 1, 1), date(2026, 12, 31))
    snapshot = assignment_snapshot(
        _quoted(
            status="in_progress",
            quotes=[_Quote(status="accepted")],
            role_allocations={LINE: [allocation]},
        ),
        today=TODAY,
    )

    assert snapshot.subjects_of("open_role")[0].facts["role_staffed"] is True
    assert snapshot.subjects_of("month_to_close") == []
    assert snapshot.subjects_of("billing_period") == []


def test_allocations_for_months_do_not_staff_a_role():
    allocation = _Allocation(date(2026, 9, 1), date(2026, 12, 31))
    snapshot = assignment_snapshot(
        _quoted(
            status="in_progress",
            quotes=[_Quote(status="accepted")],
            month_allocations=[allocation],
        ),
        today=TODAY,
    )

    assert snapshot.subjects_of("open_role")[0].facts["role_staffed"] is False
    assert [s.repeat_key for s in snapshot.subjects_of("month_to_close")] == [
        "2026-09",
        "2026-10",
    ]


def test_only_the_first_of_several_months_is_asked_for():
    allocation = _Allocation(date(2026, 9, 1), date(2026, 12, 31))
    plan = current_plan()
    snapshot = assignment_snapshot(
        _quoted(
            status="in_progress",
            quotes=[_Quote(status="accepted")],
            month_allocations=[allocation],
        ),
        today=TODAY,
    )

    asked = [
        item.subject.repeat_key
        for item in engine.asked_for(snapshot, plan)
        if item.template.key == "uitvoering.maand_afsluiten"
    ]
    assert asked == ["2026-09"]


# --- the pure parts on their own --------------------------------------------------


def test_only_what_the_look_back_has_is_needed():
    snapshot = assignment_snapshot(
        AssignmentInputs(
            id=ASSIGNMENT, kind="external", status="draft", is_client=False
        ),
        today=TODAY,
    )

    assert snapshot.case_id == ASSIGNMENT
    assert snapshot.assignment_id == ASSIGNMENT
    assert snapshot.facts["budget_has_line"] is False
    assert snapshot.subjects_of("month_to_close") == []
    assert snapshot.subjects_of("billing_period") == []
    assert snapshot.subjects_of("period_correction") == []


def test_the_selectors_pick_the_latest_live_quote():
    old = _Quote(id=uuid.uuid4(), status="superseded")
    accepted = _Quote(id=uuid.uuid4(), status="accepted")
    issued = _Quote(id=uuid.uuid4(), status="issued")

    assert quote_in_view([]) is None
    assert quote_in_view([old]) is None
    assert quote_in_view([old, issued, accepted]) is accepted
    assert quote_open([old, accepted]) is None
    assert quote_open([old, issued]) is issued


@pytest.mark.parametrize(
    ("status", "quotes", "is_client", "expected"),
    [
        ("quoted", [_Quote()], False, True),
        ("quoted", [_Quote()], True, False),
        ("quoted", [], False, False),
        ("accepted", [_Quote()], False, False),
        ("accepted", [_Quote(status="accepted")], False, False),
    ],
)
def test_the_budget_is_held_against_an_open_quote_of_a_potential_case(
    status, quotes, is_client, expected
):
    assert outdated_matters(status, quotes, is_client) is expected


@pytest.mark.parametrize(
    ("uri", "base", "expected"),
    [
        ("https://grip.example.org", "https://grip.example.org", True),
        ("https://grip.example.org/", "https://grip.example.org", True),
        ("https://ander.example.org", "https://grip.example.org", False),
        (None, "https://grip.example.org", False),
        ("", "https://grip.example.org", False),
    ],
)
def test_is_client_of(uri, base, expected):
    assert is_client_of(uri, base) is expected


def test_nothing_here_can_wait_for_a_database():
    for function in (assignment_snapshot, engine.asked_for, course.at_moment):
        assert not inspect.iscoroutinefunction(function)


def test_the_tasks_stay_outside_every_session():
    plan = current_plan()
    snapshot = assignment_snapshot(_inputs(), today=TODAY)
    [wanted] = engine.asked_for(snapshot, plan)

    view = course._watching(snapshot, plan, wanted)

    assert sqlalchemy.inspect(view.task).transient
    assert view.task.id is None
    assert view.task.created_at is None
    assert view.is_mine is False
    assert view.has_part is False
    assert view.can_take_over is False


def test_asked_for_leaves_out_what_is_done_or_does_not_apply():
    plan = current_plan()
    snapshot = assignment_snapshot(_inputs(lines=[_Line()]), today=TODAY)

    keys = {item.template.key for item in engine.asked_for(snapshot, plan)}

    assert "offerte.opstellen" in keys
    assert "offerte.aanvraag_uitwerken" not in keys
    assert "offerte.aanbieden" not in keys


# --- the telling -------------------------------------------------------------------


def _task(template_key: str, **changes: Any):
    from grip.models.task import Task

    return Task(
        **{
            "case_kind": "assignment",
            "assignment_id": ASSIGNMENT,
            "origin": "plan",
            "template_key": template_key,
            "plan_version": current_plan().version,
            "title": "Titel uit het plan",
            "track": "offerte",
            "status": "todo",
            "assignee_role": "owner",
            **changes,
        }
    )


def test_a_telling_uses_the_awaited_words_for_the_headline_and_the_title_as_title():
    told = telling.tell_watcher(_task("offerte.opstellen"), {})

    assert told.headline == "De offerte"
    assert told.title == "Maak de offerte"
    assert told.needs_me is False
    assert told.action_text is None
    assert told.work_href is None


def test_a_telling_applies_the_situation():
    told = telling.tell_watcher(
        _task("offerte.opstellen", situation="quote_outdated"), {}
    )

    assert told.headline == "Een nieuwe offerte"
    assert told.title == "Maak een nieuwe offerte"


def test_a_telling_uses_the_variables_of_its_subject():
    told = telling.tell_watcher(
        _task("offerte.intern_beoordelen", assignee_role="offertegoedkeurder"),
        {"kenmerk": REFERENCE},
    )

    assert told.headline == f"Interne goedkeuring van offerte {REFERENCE}"
    assert told.title == f"Beoordeel offerte {REFERENCE}"
    assert told.waits_on == "een interne goedkeurder van offertes"


def test_a_variable_not_at_hand_fills_with_its_stand_in():
    told = telling.tell_watcher(_task("offerte.opstellen"), {})

    assert told.instruction == (
        "Je wacht op de eigenaar van de opdracht, die de offerte voor de "
        "opdrachtgever maakt. Jij hoeft nu niets te doen."
    )
    review = telling.tell_watcher(_task("offerte.intern_beoordelen"), {})
    assert review.headline == "Interne goedkeuring van offerte"


def test_a_waiting_task_waits_on_who_the_plan_says():
    told = telling.tell_watcher(
        _task(
            "offerte.wacht_op_akkoord",
            status="waiting",
            waiting_on="de opdrachtgever",
        ),
        {},
    )
    assert told.waits_on == "de opdrachtgever"

    named = telling.tell_watcher(
        _task(
            "offerte.wacht_op_akkoord",
            status="waiting",
            waiting_on="de opdrachtgever",
        ),
        {"opdrachtgever": "Gemeente Voorbeeldstad"},
    )
    assert named.waits_on == "Gemeente Voorbeeldstad"


def test_a_step_of_a_named_person_is_told_by_its_role_never_by_a_name():
    told = telling.tell_watcher(
        _task(
            "offerte.na_terugsturen_opnieuw_maken",
            assignee_role=None,
            assignee_person_id=MAKER,
        ),
        {"kenmerk": REFERENCE},
    )

    assert told.waits_on == "de maker van de offerte"
    assert str(MAKER) not in told.instruction


def test_a_task_without_guidance_keeps_its_title():
    told = telling.tell_watcher(_task("bestaat.niet"), {})

    assert told.headline == "Titel uit het plan"
    assert told.title == "Titel uit het plan"
    assert told.waits_on == "de eigenaar van de opdracht"
