"""Billing details between the flat form of the domain and the message.

The domain keeps the details as one flat set of texts
(``grip.services.billing_deliveries.DETAIL_FIELDS``). In a message the
contact person is an object of its own. Both are in code names; the
translation to contract terms happens at the boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Domain key to the key inside the contact of a message.
_CONTACT = {"contact_name": "name", "contact_phone": "phone", "contact_email": "email"}


def to_message(details: Mapping[str, Any]) -> dict[str, Any]:
    message: dict[str, Any] = {}
    contact: dict[str, str] = {}
    for key, value in details.items():
        if not value:
            continue
        if key in _CONTACT:
            contact[_CONTACT[key]] = value
        else:
            message[key] = value
    if contact:
        message["contact"] = contact
    return message


def from_message(message: Mapping[str, Any]) -> dict[str, str]:
    details = {key: value for key, value in message.items() if key != "contact"}
    contact = message.get("contact") or {}
    for key, inner in _CONTACT.items():
        if contact.get(inner):
            details[key] = contact[inner]
    return details
