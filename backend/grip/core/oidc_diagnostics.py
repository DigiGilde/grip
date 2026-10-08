"""What the identity provider sent at a login, made safe to show and share.

For the first login against a provider nobody has logged in through yet.
Everything that identifies a person is masked: the report shows which claims
arrived, their shape, and what grip did with them, so it can be pasted into
an issue or a chat. Tokens are never shown.

Only reachable with ``OIDC_DIAGNOSTICS`` on, which Settings refuses in a
deployed environment.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from authlib.jose import jwt as authlib_jwt
from authlib.jose.errors import JoseError

SESSION_KEY = "oidc_diagnostics"

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Claims whose values are shown as they are: they describe the login or the
# organisation, not the person.
_PLAIN = (
    "iss",
    "azp",
    "aud",
    "acr",
    "amr",
    "typ",
    "scope",
    "identity_provider",
    "locale",
)
_TIMES = ("auth_time", "iat", "exp")


def shape_of_identifier(value: Any) -> str:
    """Describe an identifier without giving it away."""
    if not isinstance(value, str) or not value:
        return "ontbreekt"
    text = value.strip()
    if _UUID.match(text.lower()):
        return "uuid"
    if ":" in text:
        head, _, tail = text.rpartition(":")
        return f"{head}:<{len(tail)} tekens>"
    if "@" in text:
        return f"e-mailadres, {mask_email(text)}"
    return f"<{len(text)} tekens>"


def mask_email(value: Any) -> str:
    """Keep the domain and the length of the local part."""
    if not isinstance(value, str) or "@" not in value:
        return "ontbreekt"
    local, _, domain = value.strip().rpartition("@")
    return f"<{len(local)} tekens>@{domain}"


def _when(value: Any) -> str | None:
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds")


def claims_of_id_token(id_token: Any, jwks: Any) -> dict[str, Any]:
    """The claims of an ID token whose signature checks out, else empty."""
    if not isinstance(id_token, str) or jwks is None:
        return {}
    try:
        return dict(authlib_jwt.decode(id_token, jwks))
    except (JoseError, ValueError):
        return {}


def _organisation(claims: Mapping[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    nested = claims.get("organization")
    if isinstance(nested, Mapping):
        found["organization (genest)"] = {k: nested[k] for k in sorted(nested)}
    for key in sorted(claims):
        lowered = key.lower()
        if key == "organization":
            continue
        if any(part in lowered for part in ("organi", "department", "afdeling")):
            found[key] = claims[key]
    return found


def snapshot(
    *,
    id_claims: Mapping[str, Any],
    userinfo: Mapping[str, Any],
    token: Mapping[str, Any],
    outcome: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One login as plain data that is safe to keep in the session and show."""
    claims: dict[str, Any] = {**userinfo, **id_claims}
    email = claims.get("email")
    result: dict[str, Any] = {
        "claims_in_id_token": sorted(id_claims),
        "claims_in_userinfo": sorted(userinfo),
        "plain": {name: claims[name] for name in _PLAIN if name in claims},
        "times": {name: _when(claims.get(name)) for name in _TIMES},
        "auth_time": claims.get("auth_time"),
        "sub": shape_of_identifier(claims.get("sub")),
        "preferred_username": shape_of_identifier(claims.get("preferred_username")),
        "sso_rijk_userid": shape_of_identifier(claims.get("sso-rijk-userid")),
        "email": mask_email(email),
        "email_has_capitals": isinstance(email, str) and email != email.lower(),
        "email_verified_present": "email_verified" in claims,
        "email_verified": claims.get("email_verified"),
        "name_present": bool(str(claims.get("name") or "").strip()),
        "given_and_family_name_present": bool(
            claims.get("given_name") and claims.get("family_name")
        ),
        "session_id_present": "sid" in claims,
        "organisation": _organisation(claims),
        "tokens": {
            "id_token": bool(token.get("id_token")),
            "access_token": bool(token.get("access_token")),
            "refresh_token": bool(token.get("refresh_token")),
            "expires_in": token.get("expires_in"),
            "refresh_expires_in": token.get("refresh_expires_in"),
            "scope": token.get("scope"),
        },
    }
    if outcome is not None:
        result["outcome"] = dict(outcome)
    return result


def compare_auth_time(first: Any, second: Any) -> str:
    """Whether the second login was a new authentication."""
    if not isinstance(first, int | float) or not isinstance(second, int | float):
        return (
            "ONBEKEND: de provider stuurt geen auth_time, dus een nieuwe "
            "aanmelding is niet vast te stellen."
        )
    if second > first:
        return (
            f"JA: auth_time is {int(second - first)} seconden nieuwer. De provider "
            "heeft de aanmelding opnieuw uitgevoerd."
        )
    return (
        "NEE: auth_time is gelijk gebleven. De provider gaf de bestaande "
        "aanmelding terug, ondanks prompt=login en max_age=0."
    )


_OUTCOME = {
    "subject": "Herkend aan de vaste identiteit (sub) van een eerdere aanmelding.",
    "emailadres_eerste_aanmelding": (
        "Eerste aanmelding: gekoppeld op het bevestigde e-mailadres. De vaste "
        "identiteit (sub) is nu vastgelegd bij de persoon."
    ),
    "gast": "Geen persoon in grip, wel een openstaande uitnodiging om te tekenen.",
    "geen_subject": "Geweigerd: de provider stuurde geen sub.",
    "geen_emailadres": "Geweigerd: de provider stuurde geen e-mailadres.",
    "emailadres_niet_bevestigd": (
        "Geweigerd: de provider staat niet in voor het e-mailadres "
        "(email_verified ontbreekt of is false)."
    ),
    "onbekend": (
        "Geweigerd: er is in grip geen persoon met dit e-mailadres. Zet het "
        "adres zoals het hierboven staat in BOOTSTRAP_BEHEERDER_EMAILS of laat "
        "een beheerder de persoon aanmaken."
    ),
    "inactief": "Geweigerd: de persoon is in grip niet actief.",
    "andere_aanmelding": (
        "Geweigerd: de persoon is eerder aan een andere identiteit gekoppeld. "
        "Een beheerder ontkoppelt de login bij Team."
    ),
}


def _lines_for(title: str, shot: Mapping[str, Any]) -> list[str]:
    lines = [title, "-" * len(title)]
    for name, value in shot.get("plain", {}).items():
        lines.append(f"{name}: {value}")
    for name, value in shot.get("times", {}).items():
        lines.append(f"{name}: {value or 'ontbreekt'}")
    lines += [
        f"sub: {shot.get('sub')}",
        f"preferred_username: {shot.get('preferred_username')}",
        f"sso-rijk-userid: {shot.get('sso_rijk_userid')}",
        f"email: {shot.get('email')}"
        + (" (bevat hoofdletters)" if shot.get("email_has_capitals") else ""),
        "email_verified: "
        + (
            str(shot.get("email_verified")).lower()
            if shot.get("email_verified_present")
            else "ONTBREEKT"
        ),
        f"name aanwezig: {'ja' if shot.get('name_present') else 'nee'}",
        "given_name en family_name aanwezig: "
        + ("ja" if shot.get("given_and_family_name_present") else "nee"),
        f"sid aanwezig: {'ja' if shot.get('session_id_present') else 'nee'}",
    ]
    organisation = shot.get("organisation") or {}
    if organisation:
        for name, value in organisation.items():
            lines.append(f"organisatie, {name}: {value}")
    else:
        lines.append("organisatie: geen claim over de organisatie ontvangen")
    tokens = shot.get("tokens", {})
    lines.append(
        "tokens: "
        + ", ".join(
            f"{name}={'ja' if tokens.get(name) else 'nee'}"
            for name in ("id_token", "access_token", "refresh_token")
        )
    )
    lines.append(
        f"geldigheid: access {tokens.get('expires_in')} s, "
        f"refresh {tokens.get('refresh_expires_in')} s; scope: {tokens.get('scope')}"
    )
    lines.append("claims in ID-token: " + ", ".join(shot.get("claims_in_id_token", [])))
    lines.append("claims in userinfo: " + ", ".join(shot.get("claims_in_userinfo", [])))
    return lines


def render(data: Mapping[str, Any] | None) -> str:
    """The report as plain text."""
    head = [
        "Aanmelding bij grip: wat de identiteitsprovider stuurde",
        "========================================================",
        "Namen, adressen en identiteiten zijn gemaskeerd; tokens staan er niet in.",
        "",
    ]
    first = (data or {}).get("first")
    if not first:
        return "\n".join(
            [
                *head,
                "Nog geen aanmelding gezien in deze browser.",
                "1. Open /api/auth/login en log in.",
                "2. Open daarna deze pagina opnieuw.",
                "",
            ]
        )
    lines = [*head, *_lines_for("Eerste aanmelding", first), ""]
    outcome = first.get("outcome") or {}
    code = outcome.get("code")
    lines += [
        "Wat grip ermee deed",
        "-------------------",
        _OUTCOME.get(str(code), f"Onbekende uitkomst: {code}"),
        "",
    ]
    second = (data or {}).get("second")
    lines += ["Opnieuw aanmelden afdwingen", "---------------------------"]
    if not second:
        failure = (data or {}).get("reauth_failed")
        if failure:
            lines.append(f"De tweede aanmelding mislukte bij de provider: {failure}")
        lines += [
            "Nog niet getest. Open /api/auth/diagnose/reauth: grip stuurt je dan",
            "opnieuw naar de provider met prompt=login en max_age=0. Let op of je",
            "echt opnieuw moet inloggen, en open daarna deze pagina weer.",
            "",
        ]
    else:
        lines += [
            compare_auth_time(first.get("auth_time"), second.get("auth_time")),
            f"auth_time eerste aanmelding: {first.get('times', {}).get('auth_time')}",
            f"auth_time tweede aanmelding: {second.get('times', {}).get('auth_time')}",
            f"acr en amr tweede aanmelding: {second.get('plain', {}).get('acr')}, "
            f"{second.get('plain', {}).get('amr')}",
            f"tijd tussen vertrek en terugkomst: {data.get('reauth_seconds')} s"
            if data and data.get("reauth_seconds") is not None
            else "",
            "Noteer er zelf bij: moest je bij SSO Rijk opnieuw je gegevens invoeren?",
            "",
        ]
    return "\n".join(line for line in lines if line is not None)
