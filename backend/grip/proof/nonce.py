"""The nonce that ties one authentication to one decision.

An OpenID Connect authorization request may carry a nonce, and the identity
provider puts it, unchanged, in the ID token it signs. Grip derives that
nonce from the decision: the fingerprint of the quote's content, the hash
of the file the person was shown, what is decided, the reference people
know the quote by, and a random value. The provider's
signature then covers a value that only fits this quote and this decision.

The inputs are kept and written into the statement, so anyone can compute
the nonce again and compare it with the one in the token. The random value
keeps the nonce unpredictable, so a token cannot be prepared in advance for
a decision that has not been asked for.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from grip.proof.jose import b64url

NONCE_VERSION = 1
ACTIONS = ("accept", "reject", "approve", "send_back")

# A statement and its nonce are read outside this instance, by the other
# party and by whoever checks a bundle later. Like the contract between
# instances they are written in Dutch terms (ADR 0019); the code keeps its
# English names and translates here, in one place.
DECISION_TERMS = {
    "accept": "akkoord",
    "reject": "afwijzing",
    "approve": "goedkeuring",
    "send_back": "teruggestuurd",
}
DECISION_CODES = {term: code for code, term in DECISION_TERMS.items()}


def new_salt() -> str:
    """A fresh random value, 256 bits, as hex."""
    return secrets.token_hex(32)


def nonce_inputs(
    *,
    quote_fingerprint: str,
    action: str,
    reference: str | None,
    salt: str,
    document_sha256: str | None = None,
) -> dict[str, Any]:
    """The inputs of a nonce, as they are stored and written into a statement."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    return {
        "versie": NONCE_VERSION,
        "vingerafdruk": quote_fingerprint,
        "bestand_sha256": document_sha256 or "",
        "besluit": DECISION_TERMS[action],
        "kenmerk": reference or "",
        "zout": salt,
    }


def compute_nonce(inputs: dict[str, Any]) -> str:
    """The nonce for the given inputs: base64url of SHA-256 over their canonical JSON.

    The inputs are all strings and one small integer, so sorted keys and no
    whitespace give the same bytes as RFC 8785 would.
    """
    members = {
        "versie": int(inputs["versie"]),
        "vingerafdruk": str(inputs["vingerafdruk"]),
        "bestand_sha256": str(inputs.get("bestand_sha256") or ""),
        "besluit": str(inputs["besluit"]),
        "kenmerk": str(inputs.get("kenmerk") or ""),
        "zout": str(inputs["zout"]),
    }
    canonical = json.dumps(
        members, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    )
    return b64url(hashlib.sha256(canonical.encode("utf-8")).digest())
