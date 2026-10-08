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
            "quote_approval",
            "sent_back_quote",
            "correction_month",
            "open_role",
            "month_to_close",
            "closed_month",
            "billing_period",
        }
    ),
    # text: a text the vacancy needs (the motivation, the vacancy text).
    # text_review: one person asked to judge the latest version of a text.
    "vacancy": frozenset({"case", "text", "text_review"}),
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
            "publication_recorded",
            "request_form_in_use",
            "request_form_current",
            "request_form_signed",
        }
    ),
}

# Facts about one subject, per subject kind.
SUBJECT_FACTS: dict[str, frozenset[str]] = {
    "case": frozenset(),
    "quote_round": frozenset({"quote_issued", "quote_offered", "quote_accepted"}),
    "rejected_quote": frozenset({"quote_superseded"}),
    "received_quote": frozenset({"quote_decided"}),
    "quote_approval": frozenset({"approval_decided"}),
    "sent_back_quote": frozenset({"quote_superseded"}),
    "correction_month": frozenset({"correction_delivered"}),
    "open_role": frozenset({"role_staffed"}),
    "month_to_close": frozenset({"month_closed"}),
    "closed_month": frozenset({"billing_delivered", "invoice_recorded"}),
    # A month or a calendar quarter, as the assignment is billed.
    "billing_period": frozenset(
        {"period_ready", "period_delivered", "period_invoiced"}
    ),
    "text": frozenset(
        {
            "text_due",
            "text_in_review",
            "text_returned",
            "text_settled",
            "text_moved_on",
        }
    ),
    "text_review": frozenset({"verdict_given"}),
}

# Dates a deadline can count from, per subject kind.
ANCHORS: dict[str, frozenset[str]] = {
    "case": frozenset({"requested_on"}),
    "quote_round": frozenset(),
    "rejected_quote": frozenset(),
    "received_quote": frozenset(),
    "quote_approval": frozenset({"approval_requested_on"}),
    "sent_back_quote": frozenset(),
    "correction_month": frozenset({"correction_arose_on"}),
    "open_role": frozenset({"needed_from"}),
    "month_to_close": frozenset({"month_end"}),
    "closed_month": frozenset({"closed_on", "delivered_on"}),
    "billing_period": frozenset({"ready_on", "delivered_on"}),
    "text": frozenset(),
    "text_review": frozenset({"offered_on"}),
}

# Who a task can be for. A role is resolved when the task is read, except
# "requester" and "decision:<kind>", which name a person on a vacancy.
ASSIGNMENT_ROLES = frozenset({"owner", "manager"})
FUNCTION_ROLES = frozenset(
    {"planner", "beheerder", "tekenbevoegde", "aanvrager", "offertegoedkeurder"}
)
# The person a subject names: who asked for approval of a quote. Without such
# a person the task is for the owner of the assignment.
# "writer": who wrote or offered a text of a vacancy; "reviewer": who was
# asked to judge it.
SUBJECT_PERSON_ROLES = frozenset({"maker", "writer", "reviewer"})
VACANCY_PERSON_ROLES = frozenset(
    {
        "requester",
        "decision:hr_advice",
        "decision:control_advice",
        "decision:approval",
    }
)
ASSIGNEES: dict[str, frozenset[str]] = {
    "assignment": ASSIGNMENT_ROLES | FUNCTION_ROLES | SUBJECT_PERSON_ROLES,
    "vacancy": ASSIGNMENT_ROLES
    | FUNCTION_ROLES
    | VACANCY_PERSON_ROLES
    | frozenset({"writer", "reviewer"}),
}

ROLE_LABELS: dict[str, str] = {
    "owner": "Eigenaar van de opdracht",
    "manager": "Eigenaar of manager van de opdracht",
    "planner": "Planner",
    "beheerder": "Beheerder",
    "tekenbevoegde": "Tekenbevoegde",
    "aanvrager": "Aanvrager",
    "offertegoedkeurder": "Offertegoedkeurder",
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
    "approval_decided": "de offerte is goedgekeurd of teruggestuurd",
    "correction_delivered": "de naverrekening is aangeleverd",
    "role_staffed": "de rol is ingevuld",
    "started": "de opdracht is in uitvoering",
    "month_closed": "de maand is afgesloten",
    "final_report_issued": "het eindrapport is uitgegeven",
    "billing_delivered": "de factuurgegevens zijn aangeleverd",
    "invoice_recorded": "de factuur is vastgelegd",
    "period_delivered": "de periode is aangeleverd",
    "period_invoiced": "de factuur over de periode is vastgelegd",
    "requested": "de aanvraag is ingediend",
    "hr_advice_given": "het advies van HR is vastgelegd",
    "control_advice_given": "het advies van concern control is vastgelegd",
    "approval_given": "het akkoord is vastgelegd",
    "opened": "de vacature is opengesteld",
    "hire_recorded": "de aanname is vastgelegd",
    "colleague_known_in_wies": "de collega is bekend in Wies",
    "colleague_has_email": "de collega heeft een e-mailadres",
    "text_settled": "de tekst is vastgesteld",
    "verdict_given": "het oordeel is gegeven",
    "text_moved_on": "er is een nieuwe versie of de tekst is vastgesteld",
    "publication_recorded": "de link naar de gepubliceerde vacature is vastgelegd",
    "request_form_current": "het aanvraagformulier is gemaakt en klopt met de vacature",
    "request_form_signed": "het getekende formulier is vastgelegd",
}


def facts_for(case_kind: str, subject: str) -> frozenset[str]:
    """Every fact a template for this subject may name."""
    return CASE_FACTS[case_kind] | SUBJECT_FACTS[subject]
