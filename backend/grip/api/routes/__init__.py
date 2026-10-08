from fastapi import APIRouter

from grip.api.routes.allocations import router as allocations_router
from grip.api.routes.assignment_finance import router as assignment_finance_router
from grip.api.routes.assignments import router as assignments_router
from grip.api.routes.auth import router as auth_router
from grip.api.routes.billing import router as billing_router
from grip.api.routes.budget_lines import router as budget_lines_router
from grip.api.routes.catalogue_roles import router as catalogue_roles_router
from grip.api.routes.client_requests import router as client_requests_router
from grip.api.routes.costs import router as costs_router
from grip.api.routes.form_templates import router as form_templates_router
from grip.api.routes.function_framework import router as function_framework_router
from grip.api.routes.health import router as health_router
from grip.api.routes.inspection import router as inspection_router
from grip.api.routes.instance import router as instance_router
from grip.api.routes.integrations_wies import router as integrations_wies_router
from grip.api.routes.kpi import router as kpi_router
from grip.api.routes.month_close import router as month_close_router
from grip.api.routes.node_picker import router as node_picker_router
from grip.api.routes.organisations import router as organisations_router
from grip.api.routes.overview import router as overview_router
from grip.api.routes.peers import router as peers_router
from grip.api.routes.people import router as people_router
from grip.api.routes.person_roles import router as person_roles_router
from grip.api.routes.quotes import router as quotes_router
from grip.api.routes.rates import router as rates_router
from grip.api.routes.received_quotes import router as received_quotes_router
from grip.api.routes.received_quotes_list import router as received_quotes_list_router
from grip.api.routes.reports import router as reports_router
from grip.api.routes.signing import router as signing_router
from grip.api.routes.vacancies import router as vacancies_router
from grip.api.routes.vacancy_hire import router as vacancy_hire_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
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
api_router.include_router(vacancies_router)
api_router.include_router(vacancy_hire_router)
api_router.include_router(form_templates_router)
api_router.include_router(quotes_router)
api_router.include_router(signing_router)
api_router.include_router(month_close_router)
api_router.include_router(billing_router)
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
