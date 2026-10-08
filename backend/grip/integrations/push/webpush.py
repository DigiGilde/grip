"""Sending one message to one browser: the Web Push protocol.

Three standards, and nothing of any vendor:

- RFC 8030: an HTTP POST to the address the browser gave when it subscribed.
- RFC 8291: the body is encrypted for that one browser (ECDH on P-256, HKDF,
  AES-128-GCM, the ``aes128gcm`` content coding of RFC 8188). The push
  service that carries it cannot read it.
- RFC 8292 (VAPID): the request says who sends, with a short-lived token
  signed by the instance's key. The browser subscribed for that key only.

Written with ``cryptography`` and ``httpx``, which grip already has.
"""

from __future__ import annotations

import json
import os
import struct
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from grip.integrations.push.config import (
    PushConfig,
    b64url,
    b64url_decode,
    public_point,
)

RECORD_SIZE = 4096
# The longest plaintext that fits one record: the size minus the tag (16)
# and the delimiter (1).
MAX_PLAINTEXT = RECORD_SIZE - 17
TOKEN_LIFETIME_SECONDS = 12 * 60 * 60


class PushError(Exception):
    """The message was not accepted."""

    def __init__(self, message: str, *, gone: bool = False, retry: bool = True):
        super().__init__(message)
        # The subscription no longer exists at the push service.
        self.gone = gone
        self.retry = retry


@dataclass(frozen=True)
class Target:
    endpoint: str
    p256dh: str
    auth: str


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(
        ikm
    )


def encrypt(
    plaintext: bytes,
    target: Target,
    *,
    sender_key: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """The body of a push message for this browser (RFC 8291, one record)."""
    if len(plaintext) > MAX_PLAINTEXT:
        raise ValueError("the message does not fit one record")
    receiver_point = b64url_decode(target.p256dh)
    receiver = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), receiver_point
    )
    auth_secret = b64url_decode(target.auth)
    # A new key pair for every message.
    sender = sender_key or ec.generate_private_key(ec.SECP256R1())
    sender_point = public_point(sender)
    shared = sender.exchange(ec.ECDH(), receiver)
    ikm = _hkdf(
        auth_secret,
        shared,
        b"WebPush: info\x00" + receiver_point + sender_point,
        32,
    )
    salt = salt or os.urandom(16)
    key = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    # 0x02 marks the last record; no padding is added beyond it.
    ciphertext = AESGCM(key).encrypt(nonce, plaintext + b"\x02", None)
    header = (
        salt
        + struct.pack(">I", RECORD_SIZE)
        + bytes([len(sender_point)])
        + sender_point
    )
    return header + ciphertext


def vapid_token(config: PushConfig, endpoint: str, *, now: float | None = None) -> str:
    """A token that says this instance sends to this push service."""
    parts = urlsplit(endpoint)
    claims = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int((now or time.time()) + TOKEN_LIFETIME_SECONDS),
        "sub": config.subject,
    }
    header = b64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    body = b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    r, s = decode_dss_signature(
        config.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    )
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{header}.{body}.{b64url(signature)}"


def request_for(
    config: PushConfig,
    target: Target,
    payload: dict[str, Any],
    *,
    topic: str | None = None,
    urgency: str = "normal",
) -> tuple[dict[str, str], bytes]:
    """The headers and body of the POST to the push service."""
    body = encrypt(json.dumps(payload, separators=(",", ":")).encode(), target)
    headers = {
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(config.ttl_seconds),
        "Urgency": urgency,
        "Authorization": (
            f"vapid t={vapid_token(config, target.endpoint)}, k={config.public_key}"
        ),
    }
    if topic:
        # The push service keeps one undelivered message per topic: a newer
        # one replaces an older one that the device has not fetched yet.
        headers["Topic"] = topic
    return headers, body


async def send(
    client: Any,
    config: PushConfig,
    target: Target,
    payload: dict[str, Any],
    *,
    topic: str | None = None,
) -> None:
    """POST the message. Raises ``PushError`` when it was not accepted."""
    headers, body = request_for(config, target, payload, topic=topic)
    try:
        response = await client.post(
            target.endpoint, content=body, headers=headers, timeout=15
        )
    except Exception as exc:  # network, DNS, TLS: try again later
        raise PushError(f"{type(exc).__name__}") from exc
    status = response.status_code
    if status in (200, 201, 202, 204):
        return
    if status in (404, 410):
        raise PushError("subscription gone", gone=True, retry=False)
    if status in (400, 401, 403, 413):
        # Our request is wrong for this service; repeating it will not help.
        raise PushError(f"refused with {status}", retry=False)
    raise PushError(f"answered {status}")
