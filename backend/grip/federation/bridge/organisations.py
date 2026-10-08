"""Organisations at the boundary: references in messages, rows in the domain.

A reference names an organisation by TOOI URI, with a unit key for a part
that is not registered itself and the instance URI of its grip instance.
All dicts here are in code names.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings, get_settings
from grip.federation.peers import normalize_uri
from grip.models.organisation import Organisation
from grip.services.assignments import upsert_organisation


def own_reference(settings: Settings | None = None) -> dict[str, Any]:
    """This instance as an organisation reference."""
    settings = settings or get_settings()
    reference: dict[str, Any] = {
        "tooi_uri": settings.INSTANCE_TOOI_URI,
        "name": settings.INSTANCE_NAME,
        "instance_uri": normalize_uri(settings.INSTANCE_BASE_URI),
    }
    if settings.INSTANCE_KEY:
        reference["unit_key"] = settings.INSTANCE_KEY
    return reference


def reference(organisation: Organisation | None) -> dict[str, Any] | None:
    """A domain organisation as a reference, or None when it cannot be named.

    An organisation without a TOOI URI cannot appear in a message.
    """
    if organisation is None or not organisation.tooi_uri:
        return None
    result: dict[str, Any] = {
        "tooi_uri": organisation.tooi_uri,
        "name": organisation.name,
    }
    if organisation.unit_key:
        result["unit_key"] = organisation.unit_key
    if organisation.instance_uri:
        result["instance_uri"] = normalize_uri(organisation.instance_uri)
    return result


async def _by_instance(db: AsyncSession, instance_uri: str) -> Organisation | None:
    wanted = normalize_uri(instance_uri)
    rows = (
        (
            await db.execute(
                select(Organisation).where(Organisation.instance_uri.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    return next(
        (row for row in rows if normalize_uri(row.instance_uri or "") == wanted), None
    )


async def from_reference(db: AsyncSession, ref: dict[str, Any]) -> Organisation:
    """The domain organisation for a reference; created when it is new.

    Matched on the instance URI first: units of one registered organisation
    share a TOOI URI and are told apart by their instance.
    """
    instance_uri = ref.get("instance_uri")
    if instance_uri:
        found = await _by_instance(db, instance_uri)
        if found is not None:
            return found
    return await upsert_organisation(
        db,
        name=ref["name"],
        tooi_uri=ref.get("tooi_uri") or None,
        unit_key=ref.get("unit_key"),
        instance_uri=normalize_uri(instance_uri) if instance_uri else None,
    )


async def own_organisation(
    db: AsyncSession, settings: Settings | None = None
) -> Organisation:
    """This instance as a party in the domain; created on first use.

    An assignment that this instance requests names it as the client, and one
    that it receives names it as the contractor. The access rules recognise
    "this instance is the client" by the instance URI of that organisation.
    """
    return await from_reference(db, own_reference(settings))


async def organisation_by_id(
    db: AsyncSession, organisation_id: Any
) -> Organisation | None:
    if organisation_id is None:
        return None
    return await db.get(Organisation, organisation_id)
