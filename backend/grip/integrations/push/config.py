"""The settings of web push, and whether it is on."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from grip.core.config import Settings


class PushConfigError(ValueError):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class PushConfig:
    private_key: ec.EllipticCurvePrivateKey
    # The public key as browsers want it: the uncompressed point, base64url.
    public_key: str
    # Who the push service can reach about this sender (mailto: or https:).
    subject: str
    timezone: ZoneInfo
    daily_cap: int
    batch_seconds: int
    ttl_seconds: int


@lru_cache(maxsize=4)
def _load(raw: str) -> ec.EllipticCurvePrivateKey:
    text = raw.strip().replace("\\n", "\n")
    try:
        if "BEGIN" in text:
            key = serialization.load_pem_private_key(text.encode(), password=None)
        else:
            # The 32 bytes of the private value, base64url: what most
            # tools that make VAPID keys print.
            key = ec.derive_private_key(
                int.from_bytes(b64url_decode(text), "big"), ec.SECP256R1()
            )
    except (ValueError, TypeError) as exc:
        raise PushConfigError(
            "PUSH_VAPID_PRIVATE_KEY is not a P-256 private key"
        ) from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise PushConfigError("PUSH_VAPID_PRIVATE_KEY must be an EC P-256 key")
    return key


def public_point(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> bytes:
    public = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return public.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def is_configured(settings: Settings) -> bool:
    return bool(settings.PUSH_VAPID_PRIVATE_KEY.strip())


def push_config(settings: Settings) -> PushConfig | None:
    """The configuration, or None when the instance has no key pair."""
    if not is_configured(settings):
        return None
    key = _load(settings.PUSH_VAPID_PRIVATE_KEY)
    return PushConfig(
        private_key=key,
        public_key=b64url(public_point(key)),
        subject=settings.PUSH_VAPID_SUBJECT.strip() or settings.FRONTEND_URL,
        timezone=ZoneInfo(settings.PUSH_TIMEZONE),
        daily_cap=settings.PUSH_DAILY_CAP,
        batch_seconds=settings.PUSH_BATCH_SECONDS,
        ttl_seconds=settings.PUSH_TTL_SECONDS,
    )
