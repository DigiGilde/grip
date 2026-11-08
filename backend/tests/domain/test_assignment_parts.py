"""The rows of an assignment as a pure function of facts and classes.

The facts here are always complete, also for a reader who would never get them
loaded: a sentence of a class that is not permitted must not come out, whatever
the loader did.
"""

from datetime import date
from decimal import Decimal

import pytest

from grip.access.types import DataClass
from grip.services import phase
from grip.services.assignment_parts import (
    PART_OF_DESTINATION,
    BillingFacts,
    BudgetFacts,
    MonthFacts,
    OwnInzet,
    PartsFacts,
    QuoteFacts,
    QuoteStand,
    own_line_of,
    parts_of,
)
from grip.tasks.plan import known_plans
from grip.tasks.telling import guidance

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
ROSTER = DataClass.STAFFING_ROSTER
SIGNAL = DataClass.RATE_MISMATCH_SIGNAL

READERS = {
    "owner": frozenset({A, B, C, ROSTER, SIGNAL}),
    "lezer": frozenset({A, B}),
    "planner": frozenset({A, C, ROSTER, SIGNAL}),
    "member": frozenset({A, ROSTER}),
}

ORDER = ("close", "budget", "quote", "team", "report", "details", "history")

ROWS_BY_STATUS = {
    "draft": {"budget", "quote", "team", "details", "history"},
    "requested": {"budget", "quote", "team", "details", "history"},
    "quoted": {"budget", "quote", "team", "details", "history"},
    "verbally_agreed": {"close", "budget", "quote", "team", "details", "history"},
    "rejected": {"budget", "quote", "team", "details", "history"},
    "accepted": {"close", "budget", "quote", "team", "details", "history"},
    "in_progress": {"close", "budget", "quote", "team", "details", "history"},
    "completed": {"close", "budget", "quote", "team", "report", "details", "history"},
    "accounted": {"budget", "quote", "team", "report", "details", "history"},
    "cancelled": {"budget", "quote", "team", "details", "history"},
}

CLASSES_OF_ROW = {
    "close": {B, C},
    "budget": {B},
    "quote": {B},
    "team": {C, ROSTER},
    "report": {B},
    "details": {A},
    "history": {A},
}


def full_facts(status: str = "in_progress", kind: str = "external", **changes):
    values = {
        "kind": kind,
        "status": status,
        "owner_name": "Priya Product",
        "months": MonthFacts(overdue=8),
        "budget": BudgetFacts(lines=4, over_budget=1, not_priced=1),
        "quote": QuoteFacts(
            QuoteStand.SIGNED if kind == "external" else QuoteStand.NONE,
            date(2025, 12, 18),
        ),
        "billing": BillingFacts("deliver", "derde kwartaal 2026"),
        "report_issued": False,
        "has_personnel_line": True,
        "open_roles": 1,
        "other_scale": 1,
    }
    return PartsFacts(**{**values, **changes})


def row(facts: PartsFacts, key: str, classes=READERS["owner"]):
    return next(part for part in parts_of(facts, classes) if part.key == key)


def notice(facts: PartsFacts, key: str, classes=READERS["owner"]) -> str | None:
    return row(facts, key, classes).notice


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("kind", ["external", "internal"])
@pytest.mark.parametrize("status", ROWS_BY_STATUS)
def test_rows_follow_phase_kind_and_classes_in_a_fixed_order(status, kind, reader):
    classes = READERS[reader]
    keys = tuple(part.key for part in parts_of(full_facts(status, kind), classes))
    expected = tuple(
        key
        for key in ORDER
        if key in ROWS_BY_STATUS[status]
        and CLASSES_OF_ROW[key] & classes
        and not (key == "quote" and kind == "internal")
    )
    assert keys == expected


def test_no_basic_class_no_rows():
    assert parts_of(full_facts(), frozenset({B, C, ROSTER, SIGNAL})) == ()


@pytest.mark.parametrize("status", ROWS_BY_STATUS)
@pytest.mark.parametrize("kind", ["external", "internal"])
def test_a_member_reads_the_owner_and_nothing_else(status, kind):
    said = {
        part.key: part.notice
        for part in parts_of(full_facts(status, kind), READERS["member"])
    }
    assert said == {
        "team": None,
        "details": "Eigenaar Priya Product",
        "history": None,
    }


@pytest.mark.parametrize("status", ROWS_BY_STATUS)
@pytest.mark.parametrize("kind", ["external", "internal"])
def test_a_planner_reads_no_billing_and_no_budget(status, kind):
    parts = parts_of(full_facts(status, kind), READERS["planner"])
    said = " ".join(part.notice or "" for part in parts)
    for word in ("aan te leveren", "vast te leggen", "kwartaal", "regel", "offerte"):
        assert word not in said.lower()
    assert not {"budget", "quote", "report"} & {part.key for part in parts}


@pytest.mark.parametrize("status", ROWS_BY_STATUS)
@pytest.mark.parametrize("kind", ["external", "internal"])
def test_a_lezer_reads_nothing_about_the_team(status, kind):
    parts = parts_of(full_facts(status, kind), READERS["lezer"])
    said = " ".join(part.notice or "" for part in parts)
    assert "team" not in {part.key for part in parts}
    assert "rol open" not in said
    assert "schaal" not in said


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("status", ROWS_BY_STATUS)
def test_nobody_reads_an_amount_a_category_or_a_rate(status, reader):
    said = " ".join(
        part.notice or "" for part in parts_of(full_facts(status), READERS[reader])
    )
    for word in ("€", "categorie", "tarief"):
        assert word not in said


def test_history_never_has_a_notice():
    for status in ROWS_BY_STATUS:
        assert notice(full_facts(status), "history") is None


# -- close --------------------------------------------------------------------


def test_close_says_factureren_only_with_money_on_an_external_assignment():
    external, internal = full_facts(), full_facts(kind="internal")
    assert row(external, "close", READERS["owner"]).label == "Afsluiten en factureren"
    assert row(external, "close", READERS["lezer"]).label == "Afsluiten en factureren"
    assert row(external, "close", READERS["planner"]).label == "Afsluiten"
    assert row(internal, "close", READERS["owner"]).label == "Afsluiten"
    assert row(internal, "close", READERS["planner"]).label == "Afsluiten"


@pytest.mark.parametrize(
    ("overdue", "expected"),
    [(0, None), (1, "1 maand af te sluiten"), (8, "8 maanden af te sluiten")],
)
def test_months_to_close_are_for_money_and_staffing(overdue, expected):
    facts = full_facts(months=MonthFacts(overdue=overdue), billing=None)
    assert notice(facts, "close", READERS["owner"]) == expected
    assert notice(facts, "close", READERS["lezer"]) == expected
    assert notice(facts, "close", READERS["planner"]) == expected


@pytest.mark.parametrize(
    ("billing", "expected"),
    [
        (BillingFacts("deliver", "juli 2026"), "Juli 2026 aan te leveren"),
        (
            BillingFacts("record_invoice", "derde kwartaal 2026"),
            "Factuur over derde kwartaal 2026 vast te leggen",
        ),
        (BillingFacts("correction"), "Naverrekening aan te leveren"),
    ],
)
def test_billing_is_for_money_only(billing, expected):
    facts = full_facts(months=MonthFacts(), billing=billing)
    assert notice(facts, "close", READERS["owner"]) == expected
    assert notice(facts, "close", READERS["lezer"]) == expected
    assert notice(facts, "close", READERS["planner"]) is None


def test_months_and_billing_are_one_sentence():
    assert (
        notice(full_facts(), "close")
        == "8 maanden af te sluiten, derde kwartaal 2026 aan te leveren"
    )
    assert notice(full_facts(), "close", READERS["planner"]) == (
        "8 maanden af te sluiten"
    )


def test_an_internal_assignment_says_nothing_about_billing():
    facts = full_facts(kind="internal", billing=BillingFacts("correction"))
    assert notice(facts, "close") == "8 maanden af te sluiten"


def test_no_months_to_close_once_it_is_accounted():
    facts = full_facts("accounted", months=MonthFacts(8, True), billing=None)
    assert notice(facts, "close") is None


@pytest.mark.parametrize("status", ["accounted", "cancelled"])
def test_a_closed_month_keeps_the_row_after_the_work(status):
    facts = full_facts(status, months=MonthFacts(any_closed=True), billing=None)
    assert "close" in {part.key for part in parts_of(facts, READERS["owner"])}


@pytest.mark.parametrize("status", ["draft", "requested", "quoted", "rejected"])
def test_no_row_while_months_cannot_be_closed_and_none_was(status):
    assert "close" not in {
        part.key for part in parts_of(full_facts(status), READERS["owner"])
    }


# -- budget -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("budget", "expected"),
    [
        (BudgetFacts(lines=3), None),
        (BudgetFacts(lines=3, over_budget=1), "1 regel over de begroting"),
        (BudgetFacts(lines=3, over_budget=2), "2 regels over de begroting"),
        (BudgetFacts(lines=3, not_priced=1), "1 regel kan niet worden berekend"),
        (BudgetFacts(lines=3, not_priced=2), "2 regels kunnen niet worden berekend"),
        (
            BudgetFacts(lines=3, over_budget=1, not_priced=1),
            "1 regel over de begroting, 1 regel kan niet worden berekend",
        ),
    ],
)
def test_budget_after_the_agreement_only_reports_what_is_wrong(budget, expected):
    assert notice(full_facts(budget=budget), "budget") == expected


@pytest.mark.parametrize(
    ("budget", "expected"),
    [
        (BudgetFacts(), None),
        (BudgetFacts(lines=1), "1 regel"),
        (BudgetFacts(lines=4, over_budget=1), "4 regels"),
        (BudgetFacts(lines=4, not_priced=1), "4 regels, 1 kan niet worden berekend"),
    ],
)
@pytest.mark.parametrize(
    "status", ["draft", "requested", "quoted", "verbally_agreed", "rejected"]
)
def test_budget_while_potential_is_the_number_of_lines(status, budget, expected):
    assert notice(full_facts(status, budget=budget), "budget") == expected


def test_a_cancelled_budget_says_nothing():
    assert notice(full_facts("cancelled"), "budget") is None


# -- quote --------------------------------------------------------------------

_DAY = date(2025, 12, 18)


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        (QuoteFacts(QuoteStand.NONE), "Nog geen offerte"),
        (QuoteFacts(QuoteStand.MADE), "Gemaakt, nog niet aangeboden"),
        (QuoteFacts(QuoteStand.AWAITING_APPROVAL), "Wacht op interne goedkeuring"),
        (QuoteFacts(QuoteStand.SENT_BACK), "Teruggestuurd bij de interne goedkeuring"),
        (
            QuoteFacts(QuoteStand.OFFERED, _DAY),
            "Bij de opdrachtgever sinds 18 dec 2025",
        ),
        (QuoteFacts(QuoteStand.VERBAL, _DAY), "Mondeling akkoord op 18 dec 2025"),
        (QuoteFacts(QuoteStand.SIGNED, _DAY), "Getekend op 18 dec 2025"),
        (QuoteFacts(QuoteStand.REJECTED, _DAY), "Afgewezen op 18 dec 2025"),
    ],
)
def test_quote_says_where_it_stands(quote, expected):
    assert notice(full_facts(quote=quote), "quote") == expected


@pytest.mark.parametrize(
    ("stand", "expected"),
    [
        (QuoteStand.OFFERED, "Bij de opdrachtgever"),
        (QuoteStand.VERBAL, "Mondeling akkoord"),
        (QuoteStand.SIGNED, "Getekend"),
        (QuoteStand.REJECTED, "Afgewezen"),
    ],
)
def test_a_stand_without_a_date_still_says_where_it_stands(stand, expected):
    assert notice(full_facts(quote=QuoteFacts(stand)), "quote") == expected


@pytest.mark.parametrize("status", ["completed", "accounted", "cancelled"])
def test_no_quote_is_no_news_once_it_is_over(status):
    facts = full_facts(status, quote=QuoteFacts(QuoteStand.NONE))
    assert notice(facts, "quote") is None


# -- team ---------------------------------------------------------------------


def test_team_is_there_only_with_a_personnel_line():
    facts = full_facts(has_personnel_line=False)
    assert "team" not in {part.key for part in parts_of(facts, READERS["owner"])}
    assert "team" not in {part.key for part in parts_of(facts, READERS["member"])}


@pytest.mark.parametrize(
    ("open_roles", "other_scale", "expected"),
    [
        (0, 0, None),
        (1, 0, "1 rol open"),
        (2, 0, "2 rollen open"),
        (0, 1, "1 persoon in een andere schaal"),
        (0, 2, "2 mensen in een andere schaal"),
        (1, 1, "1 rol open, 1 persoon in een andere schaal"),
    ],
)
def test_team_with_staffing_and_the_signal(open_roles, other_scale, expected):
    facts = full_facts(open_roles=open_roles, other_scale=other_scale)
    assert notice(facts, "team", READERS["owner"]) == expected
    assert notice(facts, "team", READERS["planner"]) == expected


def test_team_with_staffing_without_the_signal():
    assert notice(full_facts(), "team", frozenset({A, C})) == "1 rol open"


def test_team_with_only_the_roster_says_nothing():
    assert notice(full_facts(), "team", frozenset({A, ROSTER})) is None
    assert notice(full_facts(), "team", frozenset({A, ROSTER, SIGNAL})) == (
        "1 persoon in een andere schaal"
    )


@pytest.mark.parametrize("status", ["completed", "accounted", "cancelled"])
def test_team_says_nothing_once_it_is_over(status):
    assert notice(full_facts(status), "team") is None


# -- report -------------------------------------------------------------------


def test_report_says_it_still_has_to_come():
    assert notice(full_facts("completed"), "report") == "Nog niet opgeleverd"


def test_report_says_nothing_once_it_is_there():
    assert notice(full_facts("completed", report_issued=True), "report") is None


def test_report_is_not_expected_of_an_internal_assignment():
    assert notice(full_facts("completed", "internal"), "report") is None


def test_report_is_still_expected_once_it_is_accounted():
    # The task holds for both statuses: its fact "completed" covers accounted.
    assert notice(full_facts("accounted"), "report") == "Nog niet opgeleverd"


def test_a_quote_on_an_assignment_that_became_internal_keeps_its_row():
    facts = full_facts(
        "rejected", "internal", quote=QuoteFacts(QuoteStand.REJECTED, _DAY)
    )
    assert notice(facts, "quote") == "Afgewezen op 18 dec 2025"


def test_a_cancelled_assignment_keeps_a_report_that_was_issued():
    keys = [
        part.key
        for part in parts_of(
            full_facts("cancelled", report_issued=True), READERS["owner"]
        )
    ]
    assert "report" in keys


# -- details ------------------------------------------------------------------


def test_details_name_the_owner():
    assert notice(full_facts(), "details") == "Eigenaar Priya Product"
    assert notice(full_facts(owner_name=None), "details") is None


# -- own line -----------------------------------------------------------------

_TODAY = date(2026, 11, 4)


def _inzet(role="Developer", pct="100.000", start=(2026, 1, 1), end=(2026, 12, 31)):
    return OwnInzet(role, Decimal(pct), date(*start), date(*end))


def test_own_line():
    assert own_line_of([_inzet()], _TODAY) == "Developer, 100%, tot 31 dec 2026"


def test_own_line_with_a_part_percentage():
    assert own_line_of([_inzet(pct="62.500")], _TODAY) == (
        "Developer, 62,5%, tot 31 dec 2026"
    )


def test_own_line_that_has_not_started():
    line = own_line_of([_inzet(start=(2027, 1, 1), end=(2027, 6, 30))], _TODAY)
    assert line == "Developer, 100%, van 1 jan 2027 tot 30 jun 2027"


def test_own_line_leaves_out_what_has_ended():
    assert own_line_of([_inzet(end=(2026, 11, 3))], _TODAY) is None
    assert own_line_of([], _TODAY) is None


def test_own_line_ending_today_still_counts():
    assert own_line_of([_inzet(end=(2026, 11, 4))], _TODAY) == (
        "Developer, 100%, tot 4 nov 2026"
    )


def test_own_line_names_every_role_from_the_earliest():
    later = _inzet("Ontwerper", "20", (2027, 1, 1), (2027, 3, 31))
    now = _inzet("Developer", "50")
    assert own_line_of([later, now], _TODAY) == (
        "Developer, 50%, tot 31 dec 2026; "
        "Ontwerper, 20%, van 1 jan 2027 tot 31 mrt 2027"
    )


# -- the client side ----------------------------------------------------------


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("status", ROWS_BY_STATUS)
def test_the_client_has_only_the_quote_and_what_is_around_it(status, reader):
    facts = full_facts(status, is_client=True)
    keys = [part.key for part in parts_of(facts, READERS[reader])]
    expected = ["quote", "details", "history"]
    assert keys == (expected if B in READERS[reader] else expected[1:])


def test_the_client_received_the_quote():
    facts = full_facts(
        "quoted", is_client=True, quote=QuoteFacts(QuoteStand.RECEIVED, _DAY)
    )
    assert notice(facts, "quote") == "Ontvangen op 18 dec 2025"


# -- every task leads to a row ------------------------------------------------

_ELSEWHERE = {"assignment.overview", "quote.approval", "received.quote"}
# A subject of one of these says that a month was closed.
_SUBJECTS_WITH_A_CLOSED_MONTH = {
    "billing_period",
    "closed_month",
    "correction_month",
    "period_correction",
}
_SUBJECTS_WITH_A_QUOTE = {"quote_round", "rejected_quote", "sent_back_quote"}


def _case_facts(status: str, kind: str, client: bool) -> dict[str, bool]:
    """The facts of ``grip.tasks.cases`` that follow from status, kind and party.

    Any other fact of a condition depends on more and is taken to hold.
    """
    of_phase = phase.phase_of(status)
    return {
        "external": kind == "external",
        "client": client,
        "contractor": not client,
        "potential": of_phase is phase.Phase.POTENTIAL,
        "agreed": status in ("accepted", "in_progress", "completed", "accounted"),
        "started": status in ("in_progress", "completed", "accounted"),
        "completed": status in ("completed", "accounted"),
        "closed": of_phase is phase.Phase.CLOSED,
        "may_close_months": phase.allows_month_close(status),
        "may_bill": phase.allows_billing(status),
        "verbally_agreed": status == phase.VERBALLY_AGREED,
        "accounted": status == "accounted",
        "rejected": status == "rejected",
        "cancelled": status == "cancelled",
    }


def _holds(condition: str, facts: dict[str, bool]) -> bool:
    if condition.startswith("not "):
        return not facts.get(condition[4:], False)
    return facts.get(condition, True)


def _assignment_tasks():
    for version, plan in known_plans().items():
        for template in plan.templates["assignment"]:
            yield version, template


def test_every_destination_of_an_assignment_task_is_known():
    for _, template in _assignment_tasks():
        destination = guidance().templates[template.key].destination
        assert destination in PART_OF_DESTINATION or destination in _ELSEWHERE


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("client", [False, True])
@pytest.mark.parametrize("kind", ["external", "internal"])
@pytest.mark.parametrize("status", ROWS_BY_STATUS)
def test_a_task_never_leads_to_a_part_without_a_row(status, kind, client, reader):
    facts = _case_facts(status, kind, client)
    for version, template in _assignment_tasks():
        destination = guidance().templates[template.key].destination
        wanted = PART_OF_DESTINATION.get(destination)
        if wanted is None or not all(_holds(c, facts) for c in template.when):
            continue
        # A reader who may not open the destination is sent to the landing.
        if not CLASSES_OF_ROW[wanted] & READERS[reader]:
            continue
        # Only what the task itself proves: no closed month, quote or personnel
        # line unless its subject says there is one.
        parts = parts_of(
            PartsFacts(
                kind=kind,
                status=status,
                is_client=client,
                months=MonthFacts(
                    any_closed=template.subject in _SUBJECTS_WITH_A_CLOSED_MONTH
                ),
                quote=QuoteFacts(QuoteStand.MADE)
                if template.subject in _SUBJECTS_WITH_A_QUOTE
                else QuoteFacts(QuoteStand.NONE),
                has_personnel_line=template.subject == "open_role",
            ),
            READERS[reader],
        )
        assert wanted in {part.key for part in parts}, (version, template.key)
