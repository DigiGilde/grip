"""The data class of every event and of every field in it.

An event has two questions for the access model: who may know that it
happened (the existence class), and who may see each value (the class of
the field). They differ on purpose: a planner may know that a billing scale
changed without seeing from what to what.

``None`` as a class means administration of the instance: only who may
manage the instance sees it. An entity that is not listed here gets that,
so something new is closed until someone classifies it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from grip.access.types import DataClass, ResourceKind

A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING
D = DataClass.PERSON_RATE
E = DataClass.PERSON_COST
F = DataClass.PERSON_KPI

# The classes of which a read is logged (Logboek Dataverwerkingen).
SENSITIVE: frozenset[DataClass] = frozenset({D, E, F})

# The key in ``field_classes`` for every field without its own entry, and
# for the payload and the note.
DEFAULT = "*"
ADMIN = None


@dataclass(frozen=True)
class Spec:
    """How the events about one kind of subject are classified."""

    existence: DataClass | None
    values: DataClass | None
    fields: Mapping[str, DataClass] = field(default_factory=dict)
    # The kind of resource the access model is asked about when the event
    # has no case and no person.
    resource: ResourceKind = ResourceKind.INSTANCE


def _spec(
    existence: DataClass | None,
    values: DataClass | None = None,
    resource: ResourceKind = ResourceKind.INSTANCE,
    **fields: DataClass,
) -> Spec:
    return Spec(
        existence, values if values is not None else existence, fields, resource
    )


_ASSIGNMENT = ResourceKind.ASSIGNMENT
_PERSON = ResourceKind.PERSON
_VACANCY = ResourceKind.VACANCY

# Rates and amounts that hang on one person, wherever they appear.
_PERSONAL_FIELDS: dict[str, DataClass] = {
    "billing_scale": D,
    "previous_billing_scale": D,
    "scale": D,
    "rate_category": D,
    "rate_cents": D,
    "hourly_rate_cents": D,
    "amount_cents": D,
    "cost_rate_cents": E,
    "cost_cents": E,
    "margin_cents": E,
    "target_percentage": F,
    "target": F,
}

SPECS: dict[str, Spec] = {
    # -- the assignment and what belongs to it --------------------------
    "assignment": _spec(A, A, _ASSIGNMENT),
    "assignment_request": _spec(A, A, _ASSIGNMENT),
    "assignment_role": _spec(A, A, _ASSIGNMENT),
    "task": _spec(A, A, _ASSIGNMENT),
    "budget_line": _spec(A, B, _ASSIGNMENT, intended_person_id=C),
    "budget_usage_requested": _spec(A, B, _ASSIGNMENT),
    "quote": _spec(A, B, _ASSIGNMENT),
    "quote_draft": _spec(A, B, _ASSIGNMENT),
    "quote_offer": _spec(A, B, _ASSIGNMENT),
    "quote_invitation": _spec(A, B, _ASSIGNMENT),
    "quote_acceptance": _spec(A, B, _ASSIGNMENT),
    "quote_rejection": _spec(A, B, _ASSIGNMENT),
    "quote_approval": _spec(A, B, _ASSIGNMENT),
    "decision_evidence": _spec(A, B, _ASSIGNMENT),
    # That a signing link was mailed is known with the assignment; to whom
    # is for who may read the quote.
    "mail_outbox": _spec(A, B, _ASSIGNMENT),
    "final_report": _spec(A, B, _ASSIGNMENT),
    "final_report_received": _spec(A, B, _ASSIGNMENT),
    "month_close": _spec(B, B, _ASSIGNMENT),
    "billing_export": _spec(B, B, _ASSIGNMENT),
    "billing_correction": _spec(B, B, _ASSIGNMENT),
    "outgoing_invoice": _spec(B, B, _ASSIGNMENT),
    "invoice_line": _spec(B, B, _ASSIGNMENT),
    "invoice_attachment": _spec(B, B, _ASSIGNMENT),
    "cost_item": _spec(B, B, ResourceKind.COST_ITEM),
    "cost_coverage": _spec(B, B, ResourceKind.COST_ITEM),
    # -- people ---------------------------------------------------------
    "allocation": _spec(C, C, _ASSIGNMENT, **_PERSONAL_FIELDS),
    "person": _spec(C, C, _PERSON),
    "person_standing": _spec(C, C, _PERSON),
    "person_role": _spec(C, C, _PERSON),
    "person_roles": _spec(C, C, _PERSON),
    "colleague_proposal": _spec(C, C, _PERSON),
    "person_scale": _spec(C, D, _PERSON),
    "hire": _spec(C, E, _PERSON),
    "billability_target": _spec(F, F, _PERSON),
    # -- vacancies ------------------------------------------------------
    "vacancy": _spec(DataClass.STAFFING_COUNTS, C, _VACANCY),
    "vacancy_text": _spec(DataClass.STAFFING_COUNTS, C, _VACANCY),
    "vacancy_step": _spec(DataClass.STAFFING_COUNTS, C, _VACANCY),
    "vacancy_decision": _spec(DataClass.STAFFING_COUNTS, C, _VACANCY),
    "vacancy_recruitment_ref": _spec(DataClass.STAFFING_COUNTS, C, _VACANCY),
    "vacancy_offer_received": _spec(DataClass.STAFFING_COUNTS, C, _VACANCY),
    "vacancy_hire": _spec(DataClass.STAFFING_COUNTS, C, _VACANCY),
    # -- administration of the instance ---------------------------------
    "rate_card": _spec(ADMIN),
    "rate_band": _spec(ADMIN),
    "scale_band": _spec(ADMIN),
    "organisation": _spec(ADMIN),
    "organisation_sync": _spec(ADMIN),
    "catalogue_role": _spec(ADMIN),
    "catalogue_role_sync": _spec(ADMIN),
    "function_framework": _spec(ADMIN),
    "function_family": _spec(ADMIN),
    "function_group": _spec(ADMIN),
    "form_template": _spec(ADMIN),
    "instance_setting": _spec(ADMIN),
    "peer": _spec(ADMIN),
    "stream": _spec(ADMIN),
}

# Domain events whose subject kind is not the first part of their name.
TYPE_SUBJECTS: dict[str, str] = {
    "invoice.recorded": "outgoing_invoice",
    "invoice.withdrawn": "outgoing_invoice",
}

_UNKNOWN = _spec(ADMIN)


def spec_for(subject_kind: str) -> Spec:
    return SPECS.get(subject_kind, _UNKNOWN)


def is_classified(subject_kind: str) -> bool:
    return subject_kind in SPECS


def _name(data_class: DataClass | None) -> str | None:
    return data_class.value if data_class is not None else None


def classify(
    subject_kind: str, *values: Mapping[str, Any] | None
) -> tuple[str | None, dict[str, str | None]]:
    """The existence class and the class per field, as stored on the event."""
    spec = spec_for(subject_kind)
    classes: dict[str, str | None] = {DEFAULT: _name(spec.values)}
    for value in values:
        for key in value or {}:
            if key in spec.fields:
                classes[key] = _name(spec.fields[key])
    return _name(spec.existence), classes


def class_of_field(field_classes: Mapping[str, Any], name: str) -> DataClass | None:
    value = field_classes.get(name, field_classes.get(DEFAULT))
    return DataClass(value) if value else None


def class_from(value: str | None) -> DataClass | None:
    return DataClass(value) if value else None
