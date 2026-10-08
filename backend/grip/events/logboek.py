"""Logboek Dataverwerkingen: reads of sensitive data, and the mapping.

Two things live here.

The first is logging who read data of the classes D, E and F (billing
scale and rate, cost rate and margin, billability). Every response is built
by ``grip.access.build_response``; when it puts a field of one of those
classes in a response, that is noted for the running request, and the
request writes one ``data.read`` event per person whose data was read.

The second is the shape of an event as a log record of the standard
(``to_log_record``): an OpenTelemetry span with the ``dpl.core``
attributes. Sending those records to a Logboek is not built.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import fields as access_fields
from grip.access.types import DataClass
from grip.core.config import Settings
from grip.core.database import get_db
from grip.events import stream
from grip.events.classification import DEFAULT, SENSITIVE
from grip.events.retention import READ_TYPE
from grip.models.stream_event import StreamEvent

# The most sensitive first: the class a read event is filed under.
_ORDER = (DataClass.PERSON_COST, DataClass.PERSON_KPI, DataClass.PERSON_RATE)

# person id (or None when the response does not say whose) -> classes read.
_ledger: ContextVar[dict[UUID | None, set[DataClass]] | None] = ContextVar(
    "grip_read_ledger", default=None
)


def _person_of(value: BaseModel) -> UUID | None:
    for name in ("person_id", "id"):
        found = getattr(value, name, None)
        if name == "id" and "person" not in type(value).__name__.lower():
            continue
        if isinstance(found, UUID):
            return found
        if isinstance(found, str):
            try:
                return UUID(found)
            except ValueError:
                continue
    return None


def _observe(value: BaseModel, data_class: DataClass) -> None:
    ledger = _ledger.get()
    if ledger is not None:
        ledger.setdefault(_person_of(value), set()).add(data_class)


access_fields.set_read_observer(_observe, SENSITIVE)


def start() -> dict[UUID | None, set[DataClass]]:
    """Start noting sensitive reads for the running request."""
    ledger: dict[UUID | None, set[DataClass]] = {}
    _ledger.set(ledger)
    return ledger


def write_reads(
    db: AsyncSession,
    ledger: dict[UUID | None, set[DataClass]],
    *,
    purpose: str | None,
    path_person_id: UUID | None = None,
) -> list[StreamEvent]:
    """One event for what the request returned of the sensitive classes.

    A page about one person gives an event about that person, which the
    person can see. A list gives one event with the classes and the number
    of persons; who they were is in the payload, because the standard for
    logging data processing wants a log record per person whose data was
    processed, and those records are made from it (``to_log_records``).
    """
    if not ledger:
        return []
    persons = sorted(
        {person_id or path_person_id for person_id in ledger} - {None}, key=str
    )
    classes = set().union(*ledger.values())
    filed = next(c for c in _ORDER if c in classes)
    names = sorted(c.value for c in classes)
    ledger.clear()
    if len(persons) <= 1:
        about = persons[0] if persons else None
        return [
            stream.append(
                db,
                READ_TYPE,
                subject=("person", about) if about else ("data", "unknown"),
                person_id=about,
                new={"classes": names},
                purpose=purpose,
                existence_class=filed.value,
                field_classes={DEFAULT: filed.value},
            )
        ]
    return [
        stream.append(
            db,
            READ_TYPE,
            subject=("data", "list"),
            new={"classes": names, "persons": len(persons)},
            payload={"person_ids": [str(person_id) for person_id in persons]},
            purpose=purpose,
            # Whose data was in a list is for the beheerder to see.
            existence_class=None,
            field_classes={DEFAULT: None},
        )
    ]


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except ValueError:
        return None


async def log_sensitive_reads(
    request: Request, db: AsyncSession = Depends(get_db)
) -> AsyncGenerator[None, None]:
    """Router dependency: write what the request read, in its transaction."""
    ledger = start()
    yield
    if not ledger:
        return
    route = request.scope.get("route")
    purpose = f"{request.method} {getattr(route, 'path', request.url.path)}"
    write_reads(
        db,
        ledger,
        purpose=purpose[:200],
        path_person_id=_uuid(request.path_params.get("person_id")),
    )
    await db.flush()


# -- the mapping to a log record of the standard -----------------------------


def pseudonym(person_id: UUID, settings: Settings) -> str:
    """A person as the logboek names them: not reversible without the key."""
    return hmac.new(
        settings.SESSION_SECRET_KEY.encode(), person_id.bytes, hashlib.sha256
    ).hexdigest()


def is_processing(event: StreamEvent) -> bool:
    """Whether the event is a processing of personal data in the sense of
    the standard: it is about the data of a person."""
    return event.person_id is not None or bool((event.payload or {}).get("person_ids"))


def to_log_records(event: StreamEvent, settings: Settings) -> list[dict[str, Any]]:
    """The log records of an event: one per person whose data it is about.

    The standard wants a record per person (``dpl.core.data_subject_id`` is
    required), so a read of a list gives as many records as it had persons,
    all with the trace id of the one request.
    """
    listed = (event.payload or {}).get("person_ids") or []
    if event.person_id is not None or not listed:
        return [to_log_record(event, settings)]
    records = []
    for index, person_id in enumerate(listed):
        record = to_log_record(event, settings)
        record["attributes"]["dpl.core.data_subject_id"] = pseudonym(
            UUID(person_id), settings
        )
        # One span per person, under the one trace.
        record["span_id"] = hashlib.sha256(f"{event.id}:{index}".encode()).hexdigest()[
            :16
        ]
        records.append(record)
    return records


def to_log_record(event: StreamEvent, settings: Settings) -> dict[str, Any]:
    """The event as a log record of Logboek Dataverwerkingen 1.0."""
    moment = int(event.occurred_at.timestamp() * 1000)
    attributes: dict[str, Any] = {
        "dpl.core.processing_activity_id": settings.LOGBOEK_PROCESSING_ACTIVITY_URI
        or f"{settings.INSTANCE_BASE_URI.rstrip('/')}/verwerkingen/onbekend",
        "dpl.core.data_subject_id": pseudonym(event.person_id, settings)
        if event.person_id
        else "",
        "dpl.core.data_subject_id_type": "grip-persoon-pseudoniem",
    }
    if event.origin_peer:
        attributes["dpl.core.foreign_operation.processor"] = event.origin_peer
    return {
        "trace_id": event.correlation_id,
        "span_id": event.id.hex[:16],
        "status": "Unset",
        "name": event.type,
        "start_time": moment,
        "end_time": moment,
        "resource": {"service.name": f"grip-{settings.INSTANCE_KEY}"},
        "attributes": attributes,
    }
