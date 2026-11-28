"""For the test suite: nothing writes a read model around the chronicle.

``install`` hooks the session. Inside a request a write to one of the read
models that did not come through ``establish`` is a finding: product code that
records no fact. A test may arrange its world by hand outside a request; that
taints the session, and its chronicles are no longer compared with the rows.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import event as sa_event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from grip.chronicle.writer import BLESSED, MODELS, SUBJECT_KIND
from grip.models.stream_event import StreamEvent

_IN_REQUEST = "grip_chronicle_in_request"
_FINDINGS = "grip_chronicle_findings"
_TAINTED = "grip_chronicle_tainted"
_CASES = "grip_chronicle_cases"
_COUNTERS = frozenset({"version", "updated_at"})
_READ_MODELS = tuple(MODELS.values())
_WRITTEN_IN_SQL = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?)\s+\"?(\w+)",
    re.IGNORECASE,
)
_installed = False


def _sync(session: AsyncSession | Session) -> Session:
    return session.sync_session if isinstance(session, AsyncSession) else session


def _only_counted(obj: Any) -> bool:
    changed = {attr.key for attr in sa_inspect(obj).attrs if attr.history.has_changes()}
    return bool(changed) and changed <= _COUNTERS


def _report(session: Session, what: str) -> None:
    if session.info.get(_IN_REQUEST):
        session.info.setdefault(_FINDINGS, []).append(what)
    else:
        session.info[_TAINTED] = True


def _on_flush(session: Session, flush_context: Any, instances: Any) -> None:
    blessed = session.info.get(BLESSED, ())
    for obj in session.new:
        if isinstance(obj, StreamEvent):
            if obj.subject_kind == SUBJECT_KIND and obj.case_id is not None:
                session.info.setdefault(_CASES, set()).add(obj.case_id)
        elif isinstance(obj, _READ_MODELS) and id(obj) not in blessed:
            _report(session, f"new {obj.__tablename__}")
    for obj in session.deleted:
        if isinstance(obj, _READ_MODELS) and id(obj) not in blessed:
            _report(session, f"deleted {obj.__tablename__}")
    for obj in session.dirty:
        if (
            isinstance(obj, _READ_MODELS)
            and id(obj) not in blessed
            and session.is_modified(obj)
            and not _only_counted(obj)
        ):
            _report(session, f"changed {obj.__tablename__}")


def _on_execute(state: Any) -> None:
    if isinstance(state.statement, TextClause):
        for table in _WRITTEN_IN_SQL.findall(state.statement.text):
            if table.lower() in MODELS:
                _report(state.session, f"statement on {table.lower()}")
    elif state.is_insert or state.is_update or state.is_delete:
        table = getattr(getattr(state.statement, "table", None), "name", None)
        if table in MODELS:
            _report(state.session, f"statement on {table}")


def install() -> None:
    global _installed
    if not _installed:
        sa_event.listen(Session, "before_flush", _on_flush)
        sa_event.listen(Session, "do_orm_execute", _on_execute)
        _installed = True


@dataclass
class Unit:
    # What this request wrote around the chronicle.
    findings: list[str] = field(default_factory=list)
    # The cases that got a fact in this request.
    cases: set[UUID] = field(default_factory=set)


@contextmanager
def in_request(session: AsyncSession | Session) -> Iterator[Unit]:
    """Follow one request. Flush the test's own edits before entering."""
    sync = _sync(session)
    unit = Unit()
    sync.info[_IN_REQUEST] = True
    sync.info[_FINDINGS] = []
    sync.info[_CASES] = set()
    try:
        yield unit
    finally:
        sync.info[_IN_REQUEST] = False
        unit.findings = list(sync.info.get(_FINDINGS, []))
        unit.cases = set(sync.info.get(_CASES, set()))


def tainted(session: AsyncSession | Session) -> bool:
    return bool(_sync(session).info.get(_TAINTED))
