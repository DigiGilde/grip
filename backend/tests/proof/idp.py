"""A stand-in identity provider for tests: a key, its JWKS and ID tokens.

The tokens are real RS256 JWS, verified by the same code that verifies a
token of a real provider.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from grip.proof.jose import b64url

ISSUER = "https://idp.voorbeeld.example/realms/test"
CLIENT_ID = "grip"


def _uint(value: int) -> str:
    return b64url(value.to_bytes((value.bit_length() + 7) // 8, "big"))


@dataclass
class StandInProvider:
    issuer: str = ISSUER
    client_id: str = CLIENT_ID
    kid: str = "test-key-1"
    key: rsa.RSAPrivateKey = field(
        default_factory=lambda: rsa.generate_private_key(65537, 2048)
    )

    @property
    def jwks(self) -> dict[str, Any]:
        numbers = self.key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": self.kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": _uint(numbers.n),
                    "e": _uint(numbers.e),
                }
            ]
        }

    @property
    def discovery(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "jwks_uri": f"{self.issuer}/protocol/openid-connect/certs",
            "authorization_endpoint": f"{self.issuer}/protocol/openid-connect/auth",
            "token_endpoint": f"{self.issuer}/protocol/openid-connect/token",
        }

    def id_token(
        self,
        *,
        nonce: str,
        sub: str = "sub-tekenaar",
        email: str = "gast@opdrachtgever.example",
        name: str = "Gast Tekenaar",
        email_verified: bool = True,
        auth_age: int | None = 5,
        now: float | None = None,
        **extra: Any,
    ) -> str:
        """An ID token as the provider would issue it after a login.

        ``auth_age`` is how many seconds ago the person authenticated;
        ``None`` leaves ``auth_time`` out.
        """
        moment = int(now if now is not None else time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.client_id,
            "azp": self.client_id,
            "sub": sub,
            "iat": moment,
            "exp": moment + 300,
            "nonce": nonce,
            "email": email,
            "email_verified": email_verified,
            "name": name,
            **extra,
        }
        if auth_age is not None:
            claims["auth_time"] = moment - auth_age
        header = b64url(
            json.dumps({"alg": "RS256", "kid": self.kid, "typ": "JWT"}).encode()
        )
        payload = b64url(json.dumps(claims).encode())
        signing_input = f"{header}.{payload}".encode("ascii")
        signature = self.key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{payload}.{b64url(signature)}"
