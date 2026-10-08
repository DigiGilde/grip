"""Writing to the audit log.

The audit log is the event stream read by entity (ADR 0028). This helper
stays for the many places that record a plain change; it writes one event.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip.events import stream
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
    assignment_id: UUID | None = None,
    vacancy_id: UUID | None = None,
    person_id: UUID | None = None,
    note: str | None = None,
) -> AuditLog:
    """Add a change record to the current transaction.

    The event commits or rolls back together with the change it describes.
    ``actor=None`` leaves the actor to the context of the request (a guest,
    a peer, a job), and records the system when there is none. Name the
    assignment, vacancy or person the change belongs to when it is at hand;
    otherwise it is looked up from the values and the entity.
    """
    return stream.append(
        db,
        subject=(entity, entity_id),
        action=action,
        actor_person_id=actor.id if actor is not None else None,
        old=old_value,
        new=new_value,
        assignment_id=assignment_id,
        vacancy_id=vacancy_id,
        person_id=person_id,
        note=note,
    )
