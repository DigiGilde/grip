"""What an ID token proves about an authentication.

An ID token is a statement signed by the identity provider: this subject
authenticated at this time, for this client, in answer to a request that
carried this nonce. Checking it needs the token and the provider's keys,
nothing else, so the same check runs when a decision is made and later when
someone verifies a bundle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from grip.proof.jose import JwsError, verify

# How long before the decision an authentication may lie and still count as
# done for this decision. The person logs in again and is sent straight
# back; a few minutes covers a slow second factor.
FRESH_SECONDS = 300
# Tolerated difference between the clock of the provider and ours.
CLOCK_SKEW_SECONDS = 60


class IdTokenError(Exception):
    """The ID token cannot be relied on: it does not prove what is claimed."""


@dataclass(frozen=True)
class IdTokenFacts:
    """The claims of a verified ID token that matter for a decision."""

    claims: dict[str, Any]
    issuer: str
    subject: str
    nonce: str
    # None when the provider did not say when the person authenticated.
    auth_time: datetime | None
    issued_at: datetime | None
    name: str | None
    email: str | None
    email_verified: bool
    # Assurance, when the provider states any.
    acr: str | None
    amr: tuple[str, ...]

    def age_at(self, moment: datetime) -> int | None:
        """Seconds between the authentication and ``moment``; None if unknown."""
        if self.auth_time is None:
            return None
        return int((moment - self.auth_time).total_seconds())

    def fresh_at(self, moment: datetime, limit: int = FRESH_SECONDS) -> bool:
        """Whether the person authenticated shortly before ``moment``.

        Unknown is not fresh: a provider that leaves ``auth_time`` out has
        not said that the person authenticated for this request.
        """
        age = self.age_at(moment)
        return age is not None and -CLOCK_SKEW_SECONDS <= age <= limit


def _time(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def _audiences(claims: dict[str, Any]) -> list[str]:
    aud = claims.get("aud")
    if isinstance(aud, str):
        return [aud]
    if isinstance(aud, list):
        return [a for a in aud if isinstance(a, str)]
    return []


def check_id_token(
    id_token: str,
    jwks: dict[str, Any] | None,
    *,
    issuer: str,
    client_id: str,
    nonce: str,
) -> IdTokenFacts:
    """Verify an ID token and return what it states.

    Checked: the signature against the given keys, the issuer, that the
    token was issued to ``client_id``, and that it carries ``nonce``. Not
    checked here: expiry and freshness. A token in a bundle is verified long
    after it expired; whether the authentication was fresh is a question
    about a moment, answered by ``IdTokenFacts.fresh_at``.
    """
    try:
        jws = verify(id_token, jwks)
    except JwsError as exc:
        raise IdTokenError(f"Het ID-token is niet geldig ondertekend: {exc}") from exc
    try:
        claims = json.loads(jws.payload)
    except ValueError as exc:
        raise IdTokenError("Het ID-token bevat geen JSON.") from exc
    if not isinstance(claims, dict):
        raise IdTokenError("Het ID-token bevat geen object met claims.")

    if claims.get("iss") != issuer:
        raise IdTokenError(
            "Het ID-token komt van een andere uitgever dan verwacht "
            f"({claims.get('iss')!r} in plaats van {issuer!r})."
        )
    audiences = _audiences(claims)
    if client_id not in audiences:
        raise IdTokenError("Het ID-token is niet voor deze toepassing uitgegeven.")
    # With more than one audience the provider must say who asked.
    if len(audiences) > 1 and claims.get("azp") != client_id:
        raise IdTokenError("Het ID-token is door een andere toepassing aangevraagd.")
    if claims.get("azp") not in (None, client_id):
        raise IdTokenError("Het ID-token is door een andere toepassing aangevraagd.")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise IdTokenError("Het ID-token noemt geen persoon (geen sub).")
    if claims.get("nonce") != nonce:
        raise IdTokenError(
            "Het ID-token hoort bij een ander verzoek: de nonce komt niet "
            "overeen met dit besluit over dit document."
        )

    amr = claims.get("amr")
    name = claims.get("name") or claims.get("preferred_username")
    email = claims.get("email")
    acr = claims.get("acr")
    return IdTokenFacts(
        claims=claims,
        issuer=issuer,
        subject=subject,
        nonce=nonce,
        auth_time=_time(claims.get("auth_time")),
        issued_at=_time(claims.get("iat")),
        name=name if isinstance(name, str) else None,
        email=email.strip().lower() if isinstance(email, str) else None,
        email_verified=claims.get("email_verified") is True,
        acr=acr if isinstance(acr, str) else None,
        amr=tuple(a for a in amr if isinstance(a, str))
        if isinstance(amr, list)
        else (),
    )
