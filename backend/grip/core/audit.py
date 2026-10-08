"""Writing to the audit log."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.audit_log import AuditLog
from grip.models.person import Person

CREATE = "create"
UPDATE = "update"
DELETE = "delete"


def record_audit(
    db: AsyncSession,
    *,
    actor: Person | None,
    action: str,
    entity: str,
    entity_id: UUID | str,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit row to the current transaction.

    The row commits or rolls back together with the change it describes.
    ``actor=None`` records the system as the actor.
    """
    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        old_value=old_value,
        new_value=new_value,
    )
    db.add(entry)
    return entry
