"""Every route that changes a stored record says how a stale save is handled.

A PATCH or PUT on a record is either protected (the service checks the
version the form started from, ``grip.services.stale``) or on the list of
exceptions with the reason. A new route that is on neither list fails here,
so a form cannot be added that silently overwrites someone else's change.
"""

from __future__ import annotations

from tests.test_route_authorization_inventory import _api_routes

# Route -> where the check is made. Each kind has a test of two saves from
# the same version: tests/test_stale_save.py, tests/test_stale_save_kinds.py
# and the API tests next to the features.
PROTECTED = {
    "PATCH /api/assignments/{assignment_id}": "assignments.update_assignment",
    "PUT /api/assignments/{assignment_id}/roles/{person_id}": (
        "assignments.set_assignment_role"
    ),
    "PATCH /api/allocations/{allocation_id}": "assignments.update_allocation",
    "PATCH /api/budget-lines/{line_id}": "assignments.update_budget_line",
    "PATCH /api/outgoing-invoices/{invoice_id}": ("outgoing_invoices.correct_invoice"),
    "PUT /api/assignments/{assignment_id}/billing/terms": (
        "billing_deliveries.set_terms"
    ),
    "PATCH /api/catalogue-roles/{role_id}": "catalogue_roles.update_role",
    "PATCH /api/costs/{cost_item_id}": "costs.update_cost_item",
    "PATCH /api/costs/{cost_item_id}/invoice-lines/{invoice_line_id}": (
        "invoice_lines.update"
    ),
    "PUT /api/costs/{cost_item_id}/coverage/{budget_line_id}": "costs.set_coverage",
    "PUT /api/form-templates/{template_id}/fields/{name}": "form_setup.set_field",
    "PATCH /api/function-framework/families/{family_id}": (
        "function_framework.update_family"
    ),
    "PATCH /api/function-framework/groups/{group_id}": (
        "function_framework.update_group"
    ),
    "PUT /api/kpi/{person_id}/{year}": "rates.set_billability_target",
    "PATCH /api/organisations/{organisation_id}": ("organisations.update_organisation"),
    "PUT /api/people/{person_id}/roles": "person_roles.set_person_roles",
    "PATCH /api/peers/{peer_row_id}": "routes.peers.update_peer",
    "PUT /api/people/{person_id}/start-date": "standing.set_start_date",
    "PATCH /api/people/{person_id}": "team.update_person",
    "PATCH /api/instance-settings": "instance_settings.set_values",
    "PATCH /api/quote-sender": "instance_settings.set_values",
    "PUT /api/vacancy-texts/settings": "instance_settings.set_values",
    "PATCH /api/rates/cards/{card}": "rates.update_card",
    "PUT /api/rates/cards/{card}/status": "rates.set_rate_card_status",
    "PUT /api/rates/cards/{card}/bands/{category}": "rates.set_rate_band",
    "PUT /api/rates/cards/{card}/scales/{scale}": "rates.set_scale_band",
    "PATCH /api/tasks/{task_id}": "routes.tasks.update_task",
    "PUT /api/vacancies/{vacancy_id}/recruitment-ref": (
        "vacancy_hire.set_recruitment_ref"
    ),
    "PATCH /api/vacancies/{vacancy_id}": "vacancies.update_vacancy",
    "PUT /api/vacancies/{vacancy_id}/decisions/{kind}": "vacancies.record_decision",
    "PUT /api/vacancies/{vacancy_id}/steps/{kind}": "vacancies.set_step",
    "PUT /api/vacancies/{vacancy_id}/publications": "text_flow.set_publication",
    "PUT /api/vacancy-texts/templates/{template_id}": "library.save_template",
    "PUT /api/vacancy-texts/shared/{key}": "library.update_shared_section",
}

# Route -> why a stale save cannot overwrite someone's change there.
EXCEPTIONS = {
    "PATCH /api/assignments/{assignment_id}/quote-draft": (
        "the draft of a quote has its own version per part (head_version)"
    ),
    "PUT /api/assignments/{assignment_id}/quote-draft/sections/{key}": (
        "the draft of a quote has its own version per section"
    ),
    "PUT /api/assignments/{assignment_id}/quote-draft/outline": (
        "the draft of a quote has its own version of the outline"
    ),
    "PUT /api/notifications/preference": (
        "a person's own preference: nobody else edits it"
    ),
    "PUT /api/people/{person_id}/functions/{function}": (
        "granting one right is the same whoever does it and whenever"
    ),
}


def _changing_routes(app) -> set[str]:
    found = set()
    for route in _api_routes(app):
        for method in sorted(route.methods & {"PATCH", "PUT"}):
            found.add(f"{method} {route.path}")
    return found


def test_every_changing_route_is_protected_or_excused(_test_app) -> None:
    routes = _changing_routes(_test_app)
    assert routes, "no routes found: the guard would pass on nothing"
    unknown = sorted(routes - set(PROTECTED) - set(EXCEPTIONS))
    assert not unknown, (
        "These routes change a record and say nothing about a stale save. "
        "Add stale.check to the service and list the route under PROTECTED, "
        f"or list it under EXCEPTIONS with the reason: {unknown}"
    )


def test_the_lists_name_only_routes_that_exist(_test_app) -> None:
    routes = _changing_routes(_test_app)
    gone = sorted((set(PROTECTED) | set(EXCEPTIONS)) - routes)
    assert not gone, f"Listed, but no such route any more: {gone}"


def test_no_route_is_on_both_lists() -> None:
    assert not set(PROTECTED) & set(EXCEPTIONS)
