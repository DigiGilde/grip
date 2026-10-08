"""Signing and verifying acceptances, and the hash of a quote.

An acceptance signed in the client's own instance carries a compact JWS. Its
payload is the canonical JSON (RFC 8785) of the fields the contract names.
The receiver verifies it with a key from the sender's JWKS and checks that
the payload equals the fields of the message.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

from grip.core.config import Settings
from grip.federation import terms

logger = logging.getLogger(__name__)

# The fields of an acceptance that the JWS covers, as the contract lists them.
SIGNED_FIELDS_CODE = (
    "id",
    "quote_id",
    "quote_hash",
    "signer",
    "organisation",
    "signed_at",
    "form",
)
# The JWS covers the message as it crosses the boundary, so in contract terms.
SIGNED_FIELDS = tuple(terms.term(name) for name in SIGNED_FIELDS_CODE)

_P256_SIZE = 32


class SigningError(Exception):
    """This instance cannot sign: no key is configured."""


class SignatureInvalidError(Exception):
    """A JWS did not verify, or does not cover the message it came with."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical_json(value: Any) -> bytes:
    """Canonical JSON according to RFC 8785."""
    return rfc8785.dumps(value)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_hash(snapshot: Any) -> str:
    """The hash of a quote: SHA-256 over the canonical JSON of its snapshot."""
    return sha256_hex(canonical_json(snapshot))


def payload_hash(payload: Any) -> str:
    """Hash that decides whether a repeated message has the same content."""
    return sha256_hex(canonical_json(payload))


def signed_fields(acceptance: dict[str, Any]) -> dict[str, Any]:
    """The signed part of an acceptance. ``acceptance`` is in contract terms."""
    return {field: acceptance[field] for field in SIGNED_FIELDS}


# --- keys ------------------------------------------------------------------


def _public_jwk(public_key: ec.EllipticCurvePublicKey) -> dict[str, str]:
    numbers = public_key.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(numbers.x.to_bytes(_P256_SIZE, "big")),
        "y": _b64url(numbers.y.to_bytes(_P256_SIZE, "big")),
    }


def jwk_thumbprint(jwk: dict[str, str]) -> str:
    """RFC 7638 thumbprint of an EC public key."""
    members = {key: jwk[key] for key in ("crv", "kty", "x", "y")}
    canonical = json.dumps(members, separators=(",", ":"), sort_keys=True)
    return _b64url(hashlib.sha256(canonical.encode()).digest())


@dataclass(frozen=True)
class SigningKey:
    private_key: ec.EllipticCurvePrivateKey
    kid: str

    @property
    def public_jwk(self) -> dict[str, str]:
        return {
            **_public_jwk(self.private_key.public_key()),
            "kid": self.kid,
            "use": "sig",
            "alg": "ES256",
        }


def generate_private_key_pem() -> str:
    """A new ES256 private key as PEM, for the FEDERATION_SIGNING_KEY setting."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


@lru_cache(maxsize=4)
def _load_key(pem: str, kid: str) -> SigningKey:
    private_key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(
        private_key.curve, ec.SECP256R1
    ):
        raise SigningError("FEDERATION_SIGNING_KEY must be an EC P-256 private key")
    return SigningKey(
        private_key=private_key,
        kid=kid or jwk_thumbprint(_public_jwk(private_key.public_key())),
    )


@lru_cache(maxsize=1)
def _throwaway_key() -> SigningKey:
    logger.warning(
        "No FEDERATION_SIGNING_KEY configured: using a throwaway key that is "
        "lost when the process stops. Local development only."
    )
    return _load_key(generate_private_key_pem(), "")


def get_signing_key(settings: Settings) -> SigningKey | None:
    """The key this instance signs with, or None when it cannot sign.

    A local run without a configured key gets a throwaway key. A deployed
    instance (PUBLIC_HOST set) never does: signatures made with a key that
    disappears on restart could not be verified later.
    """
    if settings.FEDERATION_SIGNING_KEY:
        # Environment variables often carry the PEM with literal "\n".
        pem = settings.FEDERATION_SIGNING_KEY.replace("\\n", "\n")
        return _load_key(pem, settings.FEDERATION_SIGNING_KID)
    if settings.PUBLIC_HOST:
        return None
    return _throwaway_key()


def own_jwks(settings: Settings) -> dict[str, Any]:
    """The public keys of this instance: the current one and retired ones."""
    keys: list[dict[str, Any]] = []
    current = get_signing_key(settings)
    if current is not None:
        keys.append(current.public_jwk)
    if settings.FEDERATION_RETIRED_JWKS:
        retired = json.loads(settings.FEDERATION_RETIRED_JWKS).get("keys", [])
        known = {key.get("kid") for key in keys}
        keys.extend(key for key in retired if key.get("kid") not in known)
    return {"keys": keys}


# --- sign ------------------------------------------------------------------


def sign_acceptance(acceptance: dict[str, Any], settings: Settings) -> str:
    """Compact JWS (ES256) over the signed fields of an acceptance.

    ``acceptance`` is the message in contract terms, as it will be sent.
    """
    key = get_signing_key(settings)
    if key is None:
        raise SigningError(
            "This instance has no signing key (FEDERATION_SIGNING_KEY) and "
            "cannot sign an acceptance."
        )
    header = _b64url(
        json.dumps({"alg": "ES256", "kid": key.kid}, separators=(",", ":")).encode()
    )
    payload = _b64url(canonical_json(signed_fields(acceptance)))
    signing_input = f"{header}.{payload}".encode("ascii")
    der = key.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = r.to_bytes(_P256_SIZE, "big") + s.to_bytes(_P256_SIZE, "big")
    return f"{header}.{payload}.{_b64url(signature)}"


# --- verify ----------------------------------------------------------------


def _verify_es256(jwk: dict[str, Any], signing_input: bytes, signature: bytes) -> None:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise SignatureInvalidError("The key is not an EC P-256 key")
    if len(signature) != 2 * _P256_SIZE:
        raise SignatureInvalidError("The signature has the wrong length for ES256")
    public_key = ec.EllipticCurvePublicNumbers(
        int.from_bytes(_b64url_decode(jwk["x"]), "big"),
        int.from_bytes(_b64url_decode(jwk["y"]), "big"),
        ec.SECP256R1(),
    ).public_key()
    der = encode_dss_signature(
        int.from_bytes(signature[:_P256_SIZE], "big"),
        int.from_bytes(signature[_P256_SIZE:], "big"),
    )
    public_key.verify(der, signing_input, ec.ECDSA(hashes.SHA256()))


def _verify_ps256(jwk: dict[str, Any], signing_input: bytes, signature: bytes) -> None:
    if jwk.get("kty") != "RSA":
        raise SignatureInvalidError("The key is not an RSA key")
    public_key = rsa.RSAPublicNumbers(
        int.from_bytes(_b64url_decode(jwk["e"]), "big"),
        int.from_bytes(_b64url_decode(jwk["n"]), "big"),
    ).public_key()
    public_key.verify(
        signature,
        signing_input,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size
        ),
        hashes.SHA256(),
    )


_VERIFIERS = {"ES256": _verify_es256, "PS256": _verify_ps256}


def jws_kid(jws: str) -> str | None:
    """The key id in the header of a compact JWS, without verifying it."""
    try:
        header = json.loads(_b64url_decode(jws.split(".")[0]))
    except (ValueError, IndexError):
        return None
    kid = header.get("kid") if isinstance(header, dict) else None
    return kid if isinstance(kid, str) else None


def verify_acceptance(acceptance: dict[str, Any], jwks: dict[str, Any]) -> None:
    """Check the JWS of an acceptance against the sender's keys.

    Raises SignatureInvalidError when the JWS is malformed, uses another
    algorithm than the contract allows, refers to an unknown key, does not
    verify, or covers other content than the fields of the message.
    """
    jws = acceptance.get(terms.term("jws"))
    if not isinstance(jws, str) or jws.count(".") != 2:
        raise SignatureInvalidError("The acceptance carries no compact JWS")
    header_part, payload_part, signature_part = jws.split(".")
    try:
        header = json.loads(_b64url_decode(header_part))
        payload = _b64url_decode(payload_part)
        signature = _b64url_decode(signature_part)
    except ValueError as exc:
        raise SignatureInvalidError("The JWS is not valid base64url JSON") from exc

    algorithm = header.get("alg") if isinstance(header, dict) else None
    verifier = _VERIFIERS.get(algorithm)
    if verifier is None:
        raise SignatureInvalidError("The JWS must use ES256 or PS256")
    kid = header.get("kid")
    jwk = next((key for key in jwks.get("keys", []) if key.get("kid") == kid), None)
    if kid is None or jwk is None:
        raise SignatureInvalidError(
            "The JWS refers to a key the sender does not publish"
        )
    # A key published for another algorithm must not verify this one.
    if jwk.get("alg") not in (None, algorithm):
        raise SignatureInvalidError("The key is not meant for the algorithm of the JWS")

    try:
        verifier(jwk, f"{header_part}.{payload_part}".encode("ascii"), signature)
    except InvalidSignature as exc:
        raise SignatureInvalidError("The JWS signature does not verify") from exc
    except (KeyError, ValueError) as exc:
        raise SignatureInvalidError("The key of the sender is malformed") from exc

    if payload != canonical_json(signed_fields(acceptance)):
        raise SignatureInvalidError("The JWS covers other content than the acceptance")
