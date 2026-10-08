"""The canonical form of a quote, and its hash.

One quote has one canonical form and one hash, everywhere (ADR 0020).

The canonical form is the content of the quote in the terms of the contract
(the Dutch snapshot that grip-opdrachtverkeer describes), serialised as
canonical JSON according to RFC 8785. It is built once, when the quote is
issued, and those exact bytes are stored. The hash of the quote is the
SHA-256 over those bytes, in lowercase hex. It is the hash on the printed
document, on the signing pages, in an acceptance of every form and in the
messages between instances.

After issue nothing serialises a quote again to obtain its hash: the stored
bytes are what was issued. A quote that comes in from another instance is
stored as it was received, and its hash is checked against those bytes.

What a screen, a document or a report shows of an issued quote is read from
the stored bytes through the term mapping (``read``), so a reader sees what
was hashed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import rfc8785

from grip.services import terms


def canonical_json(value: Any) -> bytes:
    """Canonical JSON according to RFC 8785."""
    return rfc8785.dumps(value)


def hash_of(canonical: bytes) -> str:
    """The hash of a quote: SHA-256 over its canonical form."""
    return hashlib.sha256(canonical).hexdigest()


def canonical_form(snapshot: dict[str, Any]) -> bytes:
    """The canonical form of a quote, from its content in code names.

    Called when a quote is issued, and for a preview of what would be
    issued now. Never for a quote that already exists: that one has its
    bytes.
    """
    return canonical_json(terms.to_contract(snapshot))


def canonical_of_received(contract_snapshot: dict[str, Any]) -> bytes:
    """The canonical form of a quote that arrived in contract terms.

    The content is serialised as it came in, without translating it first,
    so the bytes equal those of the instance that issued it.
    """
    return canonical_json(contract_snapshot)


def contract_form(canonical: bytes) -> dict[str, Any]:
    """The stored canonical form as JSON, in contract terms."""
    parsed: dict[str, Any] = json.loads(canonical)
    return parsed


def read(canonical: bytes) -> dict[str, Any]:
    """The content of a quote in code names, read from its canonical form."""
    content: dict[str, Any] = terms.from_contract(contract_form(canonical))
    return content


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """The hash a quote with this content (in code names) gets when issued."""
    return hash_of(canonical_form(snapshot))
