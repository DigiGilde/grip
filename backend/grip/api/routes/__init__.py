from fastapi import APIRouter, Depends

from grip.api.routes.allocations import router as allocations_router
from grip.api.routes.assignment_finance import router as assignment_finance_router
from grip.api.routes.assignments import router as assignments_router
from grip.api.routes.auth import router as auth_router
from grip.api.routes.billing import router as billing_router
from grip.api.routes.billing_periods import router as billing_periods_router
from grip.api.routes.budget_lines import router as budget_lines_router
from grip.api.routes.catalogue_roles import router as catalogue_roles_router
from grip.api.routes.client_requests import router as client_requests_router
from grip.api.routes.costs import router as costs_router
from grip.api.routes.events import feed_router as event_feed_router
from grip.api.routes.events import router as events_router
from grip.api.routes.form_templates import router as form_templates_router
from grip.api.routes.function_framework import router as function_framework_router
from grip.api.routes.health import router as health_router
from grip.api.routes.inspection import router as inspection_router
from grip.api.routes.instance import router as instance_router
from grip.api.routes.integrations_wies import router as integrations_wies_router
from grip.api.routes.kpi import router as kpi_router
from grip.api.routes.month_close import router as month_close_router
from grip.api.routes.node_picker import router as node_picker_router
from grip.api.routes.notifications import router as notifications_router
from grip.api.routes.organisations import router as organisations_router
from grip.api.routes.overview import router as overview_router
from grip.api.routes.passkeys import login_router as passkey_login_router
from grip.api.routes.passkeys import people_router as passkey_people_router
from grip.api.routes.passkeys import router as passkeys_router
from grip.api.routes.peers import router as peers_router
from grip.api.routes.people import router as people_router
from grip.api.routes.person_roles import router as person_roles_router
from grip.api.routes.quote_approvals import router as quote_approvals_router
from grip.api.routes.quote_drafts import router as quote_drafts_router
from grip.api.routes.quotes import router as quotes_router
from grip.api.routes.rates import router as rates_router
from grip.api.routes.received_quotes import router as received_quotes_router
from grip.api.routes.received_quotes_list import router as received_quotes_list_router
from grip.api.routes.reports import router as reports_router
from grip.api.routes.signing import router as signing_router
from grip.api.routes.tasks import router as tasks_router
from grip.api.routes.updates import router as updates_router
from grip.api.routes.vacancies import router as vacancies_router
from grip.api.routes.vacancy_hire import router as vacancy_hire_router
from grip.api.routes.vacancy_request_forms import (
    router as vacancy_request_forms_router,
)
from grip.api.routes.vacancy_texts import router as vacancy_texts_router
from grip.events.logboek import log_sensitive_reads

# Every route notes which sensitive data it returned (grip.events.logboek).

api_router = APIRouter(dependencies=[Depends(log_sensitive_reads)])
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(passkey_login_router)
api_router.include_router(passkeys_router)
api_router.include_router(passkey_people_router)
api_router.include_router(notifications_router)
api_router.include_router(instance_router)
api_router.include_router(organisations_router)
api_router.include_router(assignments_router)
api_router.include_router(assignment_finance_router)
api_router.include_router(budget_lines_router)
api_router.include_router(overview_router)
api_router.include_router(allocations_router)
api_router.include_router(rates_router)
api_router.include_router(people_router)
api_router.include_router(kpi_router)
api_router.include_router(costs_router)
api_router.include_router(vacancy_request_forms_router)
api_router.include_router(vacancies_router)
api_router.include_router(vacancy_hire_router)
api_router.include_router(vacancy_texts_router)
api_router.include_router(form_templates_router)
api_router.include_router(quotes_router)
api_router.include_router(signing_router)
api_router.include_router(month_close_router)
api_router.include_router(billing_router)
api_router.include_router(billing_periods_router)
api_router.include_router(integrations_wies_router)
api_router.include_router(peers_router)
api_router.include_router(received_quotes_router)
api_router.include_router(client_requests_router)
api_router.include_router(received_quotes_list_router)
api_router.include_router(node_picker_router)
api_router.include_router(inspection_router)
api_router.include_router(reports_router)
api_router.include_router(function_framework_router)
api_router.include_router(catalogue_roles_router)
api_router.include_router(person_roles_router)
api_router.include_router(tasks_router)
api_router.include_router(quote_approvals_router)
api_router.include_router(quote_drafts_router)

# Deciding with proof (grip.proof): intents, the evidence and checking a bundle.
from grip.api.routes.proof import router as proof_router  # noqa: E402
from grip.api.routes.proof import signing_router as proof_signing_router  # noqa: E402

api_router.include_router(proof_signing_router)
api_router.include_router(proof_router)
api_router.include_router(events_router)
api_router.include_router(event_feed_router)
api_router.include_router(updates_router)
