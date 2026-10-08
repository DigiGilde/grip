"""The hash chain over the stream.

Every event carries the hash of the event before it. The hash is SHA-256
over a canonical form (RFC 8785) of the event's fixed facts and of digests
of its values. Changing, removing or inserting an event breaks the chain at
that place, which ``verify`` reports.

A value (old, new, payload, note) is not hashed itself but through a salted
digest. That lets a value be erased later (retention, a request for
erasure) while the chain stays whole: the digest stays, the value and the
salt go.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import rfc8785

# Changes when the canonical form changes. Part of every hash.
CHAIN_VERSION = 1
# What the first event points back to.
GENESIS = "0" * 64

_VALUES = ("old_value", "new_value", "payload", "note")
_DIGESTS = ("old_digest", "new_digest", "payload_digest", "note_digest")


def plain(value: Any) -> Any:
    """The value as JSON stores it, so a digest survives a round trip."""
    return json.loads(json.dumps(value, default=str))


def _canonical(value: Any) -> bytes:
    try:
        return rfc8785.dumps(value)
    except Exception:
        # A number outside the range RFC 8785 allows: sorted JSON still
        # gives one form for one value.
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()


def digest(salt: str, value: Any) -> str | None:
    """The salted digest of a value; None for no value."""
    if value is None:
        return None
    return hashlib.sha256(salt.encode() + b"\x00" + _canonical(value)).hexdigest()


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def canonical_form(event: Mapping[str, Any]) -> bytes:
    """The bytes an event's hash is taken over. ``event`` maps column names."""
    return _canonical(
        {
            "v": CHAIN_VERSION,
            "seq": str(event["seq"]),
            "id": str(event["id"]),
            "occurred_at": timestamp(event["occurred_at"]),
            "type": event["type"],
            "action": event.get("action"),
            "subject": [event["subject_kind"], event["subject_id"]],
            "case": [event.get("case_kind"), _text(event.get("case_id"))],
            "person": _text(event.get("person_id")),
            "actor": [
                event["actor_kind"],
                _text(event.get("actor_person_id")),
                event.get("actor_ref"),
            ],
            "origin": [event["origin"], event.get("origin_peer")],
            "correlation": event["correlation_id"],
            "purpose": event.get("purpose"),
            "classes": [event.get("existence_class"), event.get("field_classes") or {}],
            "refs": event.get("refs"),
            "digests": [event.get(name) for name in _DIGESTS],
            "prev": event["prev_hash"],
        }
    )


def hash_of(event: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_form(event)).hexdigest()


@dataclass(frozen=True)
class Break:
    seq: int
    reason: str


@dataclass(frozen=True)
class Verdict:
    checked: int
    head_seq: int | None
    head_hash: str | None
    breaks: tuple[Break, ...]

    @property
    def intact(self) -> bool:
        return not self.breaks


def verify(
    events: Iterable[Mapping[str, Any]],
    *,
    expected_prev: str = GENESIS,
    stop_at_first: bool = False,
) -> Verdict:
    """Walk events in order of ``seq`` and say where the chain breaks.

    Reasons: ``prev_hash`` (an event was removed, inserted or reordered
    before this one), ``hash`` (a fixed fact or a digest of this event was
    changed) and ``value`` (a stored value no longer matches its digest).
    """
    breaks: list[Break] = []
    prev = expected_prev
    checked = 0
    last_seq: int | None = None
    for event in events:
        checked += 1
        seq = event["seq"]
        if last_seq is not None and seq != last_seq + 1:
            breaks.append(Break(seq, "gap"))
        last_seq = seq
        if event["prev_hash"] != prev:
            breaks.append(Break(seq, "prev_hash"))
        if hash_of(event) != event["hash"]:
            breaks.append(Break(seq, "hash"))
        elif event.get("salt") is not None:
            for value, name in zip(_VALUES, _DIGESTS, strict=True):
                if digest(event["salt"], event.get(value)) != event.get(name):
                    breaks.append(Break(seq, "value"))
                    break
        prev = event["hash"]
        if breaks and stop_at_first:
            break
    return Verdict(checked, last_seq, prev if checked else None, tuple(breaks))
