"""Every response field of the vacancy routes has exactly one data class."""

import pytest

from grip.access import unclassified_fields
from grip.schema import form_templates, vacancies

SCHEMAS = [
    vacancies.VacancyOut,
    vacancies.VacancySummaryOut,
    vacancies.OpenRoleOut,
    vacancies.UnfilledRoleOut,
    vacancies.VacancyOptionsOut,
    vacancies.RequestFormStatusOut,
    vacancies.LanguageModelOut,
    vacancies.PublishedTextOut,
    vacancies.ProcedureStepOut,
    vacancies.DecisionOut,
    vacancies.TextOut,
    vacancies.VacancyPermissionsOut,
    form_templates.FormTemplateOut,
    form_templates.FormInspectionOut,
    form_templates.FormFieldOut,
    form_templates.BundledMappingOut,
]


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda s: s.__name__)
def test_no_unclassified_fields(schema) -> None:
    assert unclassified_fields(schema) == []
