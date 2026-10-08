"""The catalogue a plan may draw from: subjects, facts, roles and anchors.

A plan arranges tasks around what is listed here and cannot invent anything.
A fact is a named statement about a case or about one subject of a case,
derived from domain data by ``grip.tasks.cases``; nobody sets a fact by hand
and ticking a task never changes one. See docs/taken.md for the meaning of
each name in Dutch.
"""

from __future__ import annotations

CASE_KINDS = ("assignment", "vacancy")

# The subjects a template can be "for", per kind of case. "case" is the case
# as a whole; the others repeat a task per month, role or quote.
SUBJECTS: dict[str, frozenset[str]] = {
    "assignment": frozenset(
        {
            "case",
            "quote_round",
            "rejected_quote",
            "received_quote",
            "open_role",
            "month_to_close",
            "closed_month",
        }
    ),
    "vacancy": frozenset({"case"}),
}

# Facts about the case as a whole.
CASE_FACTS: dict[str, frozenset[str]] = {
    "assignment": frozenset(
        {
            "external",
            "contractor",
            "client",
            "potential",
            "agreed",
            "started",
            "completed",
            "closed",
            "budget_has_line",
            "budget_has_personnel_line",
            "staffing_in_view",
            "may_close_months",
            "may_bill",
            "final_report_issued",
        }
    ),
    "vacancy": frozenset(
        {
            "draft",
            "requested",
            "in_procedure",
            "hr_advice_given",
            "control_advice_given",
            "advices_given",
            "approval_given",
            "approved",
            "needs_opening",
            "opened",
            "ready_to_fill",
            "hire_recorded",
            "colleague_known_in_wies",
            "colleague_has_email",
        }
    ),
}

# Facts about one subject, per subject kind.
SUBJECT_FACTS: dict[str, frozenset[str]] = {
    "case": frozenset(),
    "quote_round": frozenset({"quote_issued", "quote_offered", "quote_accepted"}),
    "rejected_quote": frozenset({"quote_superseded"}),
    "received_quote": frozenset({"quote_decided"}),
    "open_role": frozenset({"role_staffed"}),
    "month_to_close": frozenset({"month_closed"}),
    "closed_month": frozenset({"billing_delivered", "invoice_recorded"}),
}

# Dates a deadline can count from, per subject kind.
ANCHORS: dict[str, frozenset[str]] = {
    "case": frozenset({"requested_on"}),
    "quote_round": frozenset(),
    "rejected_quote": frozenset(),
    "received_quote": frozenset(),
    "open_role": frozenset({"needed_from"}),
    "month_to_close": frozenset({"month_end"}),
    "closed_month": frozenset({"closed_on", "delivered_on"}),
}

# Who a task can be for. A role is resolved when the task is read, except
# "requester" and "decision:<kind>", which name a person on a vacancy.
ASSIGNMENT_ROLES = frozenset({"owner", "manager"})
FUNCTION_ROLES = frozenset({"planner", "beheerder", "tekenbevoegde", "aanvrager"})
VACANCY_PERSON_ROLES = frozenset(
    {
        "requester",
        "decision:hr_advice",
        "decision:control_advice",
        "decision:approval",
    }
)
ASSIGNEES: dict[str, frozenset[str]] = {
    "assignment": ASSIGNMENT_ROLES | FUNCTION_ROLES,
    "vacancy": ASSIGNMENT_ROLES | FUNCTION_ROLES | VACANCY_PERSON_ROLES,
}

ROLE_LABELS: dict[str, str] = {
    "owner": "Eigenaar van de opdracht",
    "manager": "Eigenaar of manager van de opdracht",
    "planner": "Planner",
    "beheerder": "Beheerder",
    "tekenbevoegde": "Tekenbevoegde",
    "aanvrager": "Aanvrager",
}

STATUS_LABELS: dict[str, str] = {
    "todo": "Te doen",
    "doing": "Bezig",
    "waiting": "Wacht op een ander",
    "done": "Klaar",
    "obsolete": "Vervallen",
}

FACT_LABELS: dict[str, str] = {
    "budget_has_line": "de begroting heeft een regel",
    "quote_issued": "de offerte is uitgegeven",
    "quote_offered": "de offerte is aangeboden",
    "quote_accepted": "de opdrachtgever heeft akkoord gegeven",
    "quote_superseded": "er is een nieuwe offerte uitgegeven",
    "quote_decided": "er is akkoord gegeven of afgewezen",
    "role_staffed": "de rol is ingevuld",
    "started": "de opdracht is in uitvoering",
    "month_closed": "de maand is afgesloten",
    "final_report_issued": "het eindrapport is uitgegeven",
    "billing_delivered": "de factuurgegevens zijn aangeleverd",
    "invoice_recorded": "de factuur is vastgelegd",
    "requested": "de aanvraag is ingediend",
    "hr_advice_given": "het advies van HR is vastgelegd",
    "control_advice_given": "het advies van concern control is vastgelegd",
    "approval_given": "het akkoord is vastgelegd",
    "opened": "de vacature is opengesteld",
    "hire_recorded": "de aanname is vastgelegd",
    "colleague_known_in_wies": "de collega is bekend in Wies",
    "colleague_has_email": "de collega heeft een e-mailadres",
}


def facts_for(case_kind: str, subject: str) -> frozenset[str]:
    """Every fact a template for this subject may name."""
    return CASE_FACTS[case_kind] | SUBJECT_FACTS[subject]
