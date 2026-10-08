"""Shared steps for the transform, load and command-line tests."""

from __future__ import annotations

from grip.importers.grist.confirmation import (
    CONFIRMED,
    KIND_PERSON,
    ConfirmationList,
)
from grip.importers.grist.document import GristDocument
from grip.importers.grist.mapping import Mapping, check_mapping
from grip.importers.grist.transform import ImportPlan, build_plan

EMAIL_DOMAIN = "voorbeeld.example"


def confirm_all(confirmations: ConfirmationList) -> ConfirmationList:
    """Stand in for the person who reviews the list and approves it all."""
    for item in confirmations.items:
        item.status = CONFIRMED
        if item.kind == KIND_PERSON and item.values.get("action") == "laden":
            first = item.label.split()[0].lower()
            item.values["email"] = f"{first}@{EMAIL_DOMAIN}"
    return confirmations


def confirmed_plan(document: GristDocument, mapping: Mapping) -> ImportPlan:
    check = check_mapping(document, mapping)
    proposals = build_plan(document, mapping, check).confirmations
    return build_plan(document, mapping, check, confirmations=confirm_all(proposals))
