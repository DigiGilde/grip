"""Canonical JSON and the quote hash.

The hash of a quote is the SHA-256 over the RFC 8785 canonical JSON of its
snapshot, in lowercase hex. The contract repo uses the same definition, so a
hash computed here verifies at the other side.
"""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785


def canonical_json(value: Any) -> bytes:
    return rfc8785.dumps(value)


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(snapshot)).hexdigest()
