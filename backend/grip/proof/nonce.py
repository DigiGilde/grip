"""The nonce that ties one authentication to one decision.

An OpenID Connect authorization request may carry a nonce, and the identity
provider puts it, unchanged, in the ID token it signs. Grip derives that
nonce from the decision: the fingerprint of the quote, what is decided, the
reference people know the quote by, and a random value. The provider's
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


def new_salt() -> str:
    """A fresh random value, 256 bits, as hex."""
    return secrets.token_hex(32)


def nonce_inputs(
    *, quote_fingerprint: str, action: str, reference: str | None, salt: str
) -> dict[str, Any]:
    """The inputs of a nonce, as they are stored and written into a statement."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    return {
        "version": NONCE_VERSION,
        "quote_fingerprint": quote_fingerprint,
        "action": action,
        "reference": reference or "",
        "salt": salt,
    }


def compute_nonce(inputs: dict[str, Any]) -> str:
    """The nonce for the given inputs: base64url of SHA-256 over their canonical JSON.

    The inputs are all strings and one small integer, so sorted keys and no
    whitespace give the same bytes as RFC 8785 would.
    """
    members = {
        "version": int(inputs["version"]),
        "quote_fingerprint": str(inputs["quote_fingerprint"]),
        "action": str(inputs["action"]),
        "reference": str(inputs.get("reference") or ""),
        "salt": str(inputs["salt"]),
    }
    canonical = json.dumps(
        members, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    )
    return b64url(hashlib.sha256(canonical.encode("utf-8")).digest())
