"""Compact JWS: decode and verify, with nothing but ``cryptography``.

Deliberately small and self-contained: the offline check of a bundle must
not depend on the application, its settings or its database. Three
algorithms are known: ES256 (the key of a grip instance), and RS256 and
PS256 (what identity providers sign ID tokens with).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

_P256_SIZE = 32


class JwsError(Exception):
    """A JWS is malformed, uses an unknown key or algorithm, or does not verify."""


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Jws:
    header: dict[str, Any]
    payload: bytes
    signature: bytes
    signing_input: bytes

    @property
    def kid(self) -> str | None:
        kid = self.header.get("kid")
        return kid if isinstance(kid, str) else None

    @property
    def algorithm(self) -> str | None:
        alg = self.header.get("alg")
        return alg if isinstance(alg, str) else None


def decode(compact: str) -> Jws:
    """Split a compact JWS, without verifying anything."""
    if not isinstance(compact, str) or compact.count(".") != 2:
        raise JwsError("Dit is geen compacte JWS (drie delen, gescheiden door punten).")
    header_part, payload_part, signature_part = compact.split(".")
    try:
        header = json.loads(b64url_decode(header_part))
        payload = b64url_decode(payload_part)
        signature = b64url_decode(signature_part)
    except (ValueError, UnicodeDecodeError) as exc:
        raise JwsError("De JWS is geen geldige base64url-JSON.") from exc
    if not isinstance(header, dict):
        raise JwsError("De kop van de JWS is geen object.")
    return Jws(
        header=header,
        payload=payload,
        signature=signature,
        signing_input=f"{header_part}.{payload_part}".encode("ascii"),
    )


def _rsa_key(jwk: dict[str, Any]) -> rsa.RSAPublicKey:
    if jwk.get("kty") != "RSA":
        raise JwsError("De sleutel is geen RSA-sleutel.")
    return rsa.RSAPublicNumbers(
        int.from_bytes(b64url_decode(jwk["e"]), "big"),
        int.from_bytes(b64url_decode(jwk["n"]), "big"),
    ).public_key()


def _verify_rs256(jwk: dict[str, Any], signing_input: bytes, signature: bytes) -> None:
    _rsa_key(jwk).verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())


def _verify_ps256(jwk: dict[str, Any], signing_input: bytes, signature: bytes) -> None:
    _rsa_key(jwk).verify(
        signature,
        signing_input,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size
        ),
        hashes.SHA256(),
    )


def _verify_es256(jwk: dict[str, Any], signing_input: bytes, signature: bytes) -> None:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise JwsError("De sleutel is geen EC P-256-sleutel.")
    if len(signature) != 2 * _P256_SIZE:
        raise JwsError("De handtekening heeft niet de lengte van ES256.")
    public_key = ec.EllipticCurvePublicNumbers(
        int.from_bytes(b64url_decode(jwk["x"]), "big"),
        int.from_bytes(b64url_decode(jwk["y"]), "big"),
        ec.SECP256R1(),
    ).public_key()
    der = encode_dss_signature(
        int.from_bytes(signature[:_P256_SIZE], "big"),
        int.from_bytes(signature[_P256_SIZE:], "big"),
    )
    public_key.verify(der, signing_input, ec.ECDSA(hashes.SHA256()))


_VERIFIERS = {"RS256": _verify_rs256, "PS256": _verify_ps256, "ES256": _verify_es256}


def find_key(jwks: dict[str, Any] | None, kid: str | None) -> dict[str, Any] | None:
    keys = (jwks or {}).get("keys", [])
    if not isinstance(keys, list):
        return None
    return next(
        (key for key in keys if isinstance(key, dict) and key.get("kid") == kid), None
    )


def verify(compact: str, jwks: dict[str, Any] | None) -> Jws:
    """Verify a compact JWS against a key set and return its parts.

    Raises ``JwsError`` when the algorithm is not one of the three known
    ones, the key is not in the set, the key is meant for another
    algorithm, or the signature does not verify.
    """
    jws = decode(compact)
    verifier = _VERIFIERS.get(jws.algorithm or "")
    if verifier is None:
        raise JwsError(
            f"Het algoritme {jws.algorithm!r} wordt niet geaccepteerd "
            "(alleen RS256, PS256 en ES256)."
        )
    jwk = find_key(jwks, jws.kid)
    if jws.kid is None or jwk is None:
        raise JwsError("De sleutel waarmee is getekend zit niet in de sleutelset.")
    if jwk.get("alg") not in (None, jws.algorithm):
        raise JwsError("De sleutel is voor een ander algoritme bedoeld.")
    if jwk.get("use") not in (None, "sig"):
        raise JwsError("De sleutel is niet bedoeld om mee te tekenen.")
    try:
        verifier(jwk, jws.signing_input, jws.signature)
    except InvalidSignature as exc:
        raise JwsError("De handtekening klopt niet.") from exc
    except (KeyError, ValueError) as exc:
        raise JwsError("De sleutel is onvolledig of ongeldig.") from exc
    return jws
