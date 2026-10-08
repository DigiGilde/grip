"""A passkey authenticator in software, for tests.

Makes the same structures a platform authenticator hands to the browser: an
attestation object with a new P-256 key (attestation format "none") on
registration, and a signed assertion on use. Nothing here is specific to
grip; the server's own checks run on what it produces.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from grip.proof.jose import b64url

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40


class SoftwareAuthenticator:
    def __init__(self, *, rp_id: str, origin: str, user_verification: bool = True):
        self.rp_id = rp_id
        self.origin = origin
        self.user_verification = user_verification
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0
        self.user_handle: bytes | None = None

    def _flags(self, extra: int = 0) -> int:
        return FLAG_UP | (FLAG_UV if self.user_verification else 0) | extra

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": challenge,
                "origin": self.origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode()

    def _cose_key(self) -> bytes:
        numbers = self.private_key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def register(self, options_json: str) -> str:
        """Answer ``navigator.credentials.create`` for these options."""
        options = json.loads(options_json)
        self.user_handle = _decode(options["user"]["id"])
        client_data = self._client_data("webauthn.create", options["challenge"])
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([self._flags(FLAG_AT)])
            + struct.pack(">I", self.sign_count)
            + bytes(16)  # aaguid
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return json.dumps(
            {
                "id": b64url(self.credential_id),
                "rawId": b64url(self.credential_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": b64url(client_data),
                    "attestationObject": b64url(attestation),
                    "transports": ["internal"],
                },
                "clientExtensionResults": {},
                "authenticatorAttachment": "platform",
            }
        )

    def assert_(self, options_json: str) -> str:
        """Answer ``navigator.credentials.get`` for these options."""
        options = json.loads(options_json)
        return json.dumps(self.assertion(options["challenge"]))

    def assertion(self, challenge: str) -> dict[str, Any]:
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", challenge)
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([self._flags()])
            + struct.pack(">I", self.sign_count)
        )
        signature = self.private_key.sign(
            auth_data + hashlib.sha256(client_data).digest(),
            ec.ECDSA(hashes.SHA256()),
        )
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(self.user_handle) if self.user_handle else None,
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }


def _decode(text: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
