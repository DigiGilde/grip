"""A passkey assertion as part of the proof of a decision.

A passkey is a key pair that lives on a person's own device. When a person
with a passkey decides on a quote, the device signs a challenge that grip
computes from the decision itself: the same inputs as the nonce of the
identity provider (the fingerprint of the quote, the hash of its file, what
is decided, the reference, a random value). The signature is checked with
the public key that was registered earlier, and the device says in what it
signs that it verified its user (fingerprint, face or PIN).

That is evidence of another kind than a login: it does not come from the
identity provider and needs nothing from it afterwards. It is an addition.
A decision without it is recorded exactly as before.

What it proves: a device holding the private key of this registered passkey
signed for exactly this decision, after verifying its user. What it does
not prove: which human that was, or that the registration was right; the
registration is this instance's own record, and is stated as such.

This module is pure: no database and no settings. The server uses it when
the assertion comes in, and the offline verifier uses it on a bundle.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from grip.proof.jose import b64url

PASSKEY_VERSION = 1
# Keeps this challenge apart from every other use of the same inputs.
CHALLENGE_DOMAIN = b"grip-passkey-besluit-v1\n"


class PasskeyError(ValueError):
    """The assertion does not prove what it should."""


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")


def compute_challenge(inputs: dict[str, Any]) -> bytes:
    """The challenge a passkey signs for a decision: 32 bytes.

    SHA-256 over a fixed prefix and the canonical JSON of the inputs of the
    nonce (``grip.proof.nonce.nonce_inputs``). The random value among them
    makes it different for every decision someone starts.
    """
    members = {
        "versie": int(inputs["versie"]),
        "vingerafdruk": str(inputs["vingerafdruk"]),
        "bestand_sha256": str(inputs.get("bestand_sha256") or ""),
        "besluit": str(inputs["besluit"]),
        "kenmerk": str(inputs.get("kenmerk") or ""),
        "zout": str(inputs["zout"]),
    }
    return hashlib.sha256(CHALLENGE_DOMAIN + _canonical(members)).digest()


def assertion_hash(assertion: dict[str, Any]) -> str:
    """The hash by which a statement names an assertion."""
    return hashlib.sha256(_canonical(assertion)).hexdigest()


@dataclass(frozen=True)
class AssertionFacts:
    user_verified: bool
    sign_count: int
    device_type: str | None
    backed_up: bool | None


def check_assertion(
    assertion: dict[str, Any],
    *,
    public_key_cose: bytes,
    challenge: bytes,
    rp_id: str,
    origin: str,
    current_sign_count: int = 0,
) -> AssertionFacts:
    """Verify an assertion against a public key and a challenge.

    Checks the signature, that the signed client data names this challenge,
    this origin and the kind "webauthn.get", that the authenticator data is
    for this relying party, and that the user was present and verified.
    Raises ``PasskeyError`` otherwise.
    """
    from webauthn import verify_authentication_response
    from webauthn.helpers.exceptions import WebAuthnException

    try:
        verified = verify_authentication_response(
            credential=assertion,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=public_key_cose,
            credential_current_sign_count=current_sign_count,
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        raise PasskeyError(str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise PasskeyError(f"de bevestiging is niet te lezen: {exc}") from exc
    device_type = getattr(verified.credential_device_type, "value", None)
    return AssertionFacts(
        user_verified=bool(verified.user_verified),
        sign_count=int(verified.new_sign_count),
        device_type=device_type,
        backed_up=bool(verified.credential_backed_up),
    )


def statement_element(
    *,
    credential_id: bytes,
    public_key_cose: bytes,
    rp_id: str,
    origin: str,
    challenge_inputs: dict[str, Any],
    assertion: dict[str, Any],
    registered_at: datetime,
    registration: dict[str, Any],
    confirmed_at: datetime,
) -> dict[str, Any]:
    """What a statement says about the passkey that confirmed the decision.

    Everything needed to check the assertion later is in here, signed by
    the instance with the rest of the statement: the public key, the
    relying party, the inputs of the challenge and the hash of the
    assertion. The registration is this instance's record of how the key
    came to belong to the person.
    """
    return {
        "versie": PASSKEY_VERSION,
        "credential_id": b64url(credential_id),
        "publieke_sleutel_cose": b64url(public_key_cose),
        "rp_id": rp_id,
        "origin": origin,
        "uitdaging": dict(challenge_inputs),
        "assertion_sha256": assertion_hash(assertion),
        "gebruiker_geverifieerd": True,
        "bevestigd_op": confirmed_at.isoformat(),
        "registratie": {
            "geregistreerd_op": registered_at.isoformat(),
            **registration,
        },
    }
