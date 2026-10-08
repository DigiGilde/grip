"""Completeness as a property: a change of domain data leaves an event.

``watch`` follows one unit of work on a session (in production: one
transaction) and tells afterwards which domain tables were changed without
an event that covers them. The test suite wraps every request in it, so a
new write path that forgets its event fails the build.

A table is covered when the unit wrote an event whose subject kind is the
table itself or one of the kinds named for it in ``COVERED_BY``. Tables
that hold no domain data are on ``NOT_DOMAIN``, each with the reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from grip.events.stream import KINDS_WRITTEN

# Tables whose changes need no event, and why.
NOT_DOMAIN: dict[str, str] = {
    "stream_event": "the stream itself",
    "http_session": "login sessions",
    "signing_intent": "a pending step of a signing session; the decision is the fact",
    "federation_inbox": "transport: a received message; what it causes is recorded",
    "federation_outbox": "transport: a message to send; its cause is recorded",
    "task": "derived from the facts by the engine; a manual change is recorded "
    "by the task service",
    "task_case": "what the engine remembers of a case",
    "task_engine_run": "when the engine last looked",
    "grist_import_ref": "bookkeeping of the one-time import",
    "quote_reference_counter": "a counter; the quote that takes a number is recorded",
    "organisation_sync_run": "a log of a sync run; the run is recorded as an event",
    "catalogue_role_sync_run": "a log of a sync run; the run is recorded as an event",
}

# A table that is changed as part of something else: the subject kinds
# whose event covers it.
COVERED_BY: dict[str, tuple[str, ...]] = {
    "month_close_line": ("month_close",),
    "billing_export_line": ("billing_export", "month_close"),
    "outgoing_invoice_delivery": ("outgoing_invoice", "invoice"),
    "outgoing_invoice": ("invoice",),
    "vacancy": ("vacancy_decision",),
    "vacancy_step": ("vacancy", "vacancy_decision"),
    # A role that is new to the catalogue enters it with the line that names it.
    "catalogue_role": ("catalogue_role_sync", "budget_line", "allocation"),
    # A client that is not known yet is added with the request that names it.
    "organisation": ("organisation_sync", "assignment_request"),
    # Lines follow when a role is merged or the period of the assignment moves.
    "budget_line": ("catalogue_role", "assignment"),
    "assignment_role": ("assignment", "assignment_request"),
    "person": ("colleague_proposal", "vacancy_hire", "person_standing"),
    "person_catalogue_role": ("person_roles", "person_role", "catalogue_role"),
    "person_role": ("person", "person_roles"),
    "role": ("person_role",),
    "rate_band": ("rate_card",),
    "scale_band": ("rate_card",),
    "quote_acceptance": ("quote",),
    "quote_rejection": ("quote",),
    "quote_offer": ("quote",),
    "decision_evidence": ("quote", "quote_acceptance", "quote_rejection"),
    "stored_document": (
        "invoice_attachment",
        "form_template",
        "quote",
        "quote_acceptance",
        "vacancy",
        "final_report",
    ),
    "function_family": ("function_framework",),
    "function_group": ("function_framework",),
    "task_note": ("task",),
    "person_standing": ("person", "colleague_proposal", "vacancy_hire"),
    "colleague_proposal": ("person_standing", "person", "vacancy_hire"),
    # The date and amount of the quote are kept at the assignment as well.
    "assignment": (
        "assignment_request",
        "final_report",
        "final_report_received",
        "quote",
        "quote_offer",
    ),
    # Inzet that follows a line or an assignment moves with it. The one
    # event at the line or the assignment names what moved along.
    "allocation": ("budget_line", "assignment"),
}

_CHANGED = "grip_completeness_changed"


def _note(session: Session, table: str | None) -> None:
    if table:
        session.info.setdefault(_CHANGED, []).append(table)


@sa_event.listens_for(Session, "after_flush")
def _after_flush(session: Session, flush_context: Any) -> None:
    for obj in session.new:
        _note(session, getattr(obj, "__tablename__", None))
    for obj in session.deleted:
        _note(session, getattr(obj, "__tablename__", None))
    for obj in session.dirty:
        if session.is_modified(obj):
            _note(session, getattr(obj, "__tablename__", None))


@sa_event.listens_for(Session, "do_orm_execute")
def _on_execute(state: Any) -> None:
    # Statements that change rows without loading them.
    if state.is_insert or state.is_update or state.is_delete:
        table = getattr(state.statement, "table", None)
        _note(state.session, getattr(table, "name", None))


@dataclass(frozen=True)
class Unrecorded:
    table: str
    # The subject kinds of the events the unit did write.
    recorded: tuple[str, ...]

    def __str__(self) -> str:
        wrote = ", ".join(self.recorded) or "no event"
        return f"{self.table} changed, covered by none of: {wrote}"


@dataclass
class Unit:
    session: Session
    _start: int = 0
    _first_kind: int = 0
    changed: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)

    def close(self) -> None:
        info = self.session.info
        self.changed = list(info.get(_CHANGED, [])[self._start :])
        self.kinds = list(info.get(KINDS_WRITTEN, [])[self._first_kind :])

    def unrecorded(self) -> list[Unrecorded]:
        kinds = set(self.kinds)
        missing = []
        for table in dict.fromkeys(self.changed):
            if table in NOT_DOMAIN:
                continue
            if table in kinds or kinds & set(COVERED_BY.get(table, ())):
                continue
            missing.append(Unrecorded(table, tuple(sorted(kinds))))
        return missing


@contextmanager
def watch(session: AsyncSession | Session) -> Iterator[Unit]:
    """Follow one unit of work. Flush before leaving the block."""
    sync = session.sync_session if isinstance(session, AsyncSession) else session
    unit = Unit(
        sync, len(sync.info.get(_CHANGED, [])), len(sync.info.get(KINDS_WRITTEN, []))
    )
    try:
        yield unit
    finally:
        unit.close()
