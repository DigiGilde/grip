"""Check a bundle, with no access to grip.

    python -m grip.proof.verify bewijs.json
    python -m grip.proof.verify bewijs.json --online --tsa-root tsa-root.pem

The check needs the bundle and nothing else: no database, no settings, no
network unless ``--online`` is given. It prints what is proven and, as
plainly, what is not. It exits with 1 when something in the bundle does not
fit, and with 0 otherwise; a bundle can be sound and still leave things
unproven.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from grip.proof.bundle import BUNDLE_TYPE, BUNDLE_VERSION
from grip.proof.idtoken import FRESH_SECONDS, IdTokenError, check_id_token
from grip.proof.jose import find_key, sha256_hex
from grip.proof.nonce import compute_nonce
from grip.proof.statement import StatementError, read_statement

PROVEN = "bewezen"
NOT_PROVEN = "niet_bewezen"
WRONG = "fout"

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")
_LOCAL_SUFFIXES = (".localhost", ".local", ".test", ".example", ".invalid", ".internal")


@dataclass
class Report:
    findings: list[tuple[str, str]] = field(default_factory=list)
    statement: dict[str, Any] | None = None

    def proven(self, text: str) -> None:
        self.findings.append((PROVEN, text))

    def not_proven(self, text: str) -> None:
        self.findings.append((NOT_PROVEN, text))

    def wrong(self, text: str) -> None:
        self.findings.append((WRONG, text))

    @property
    def sound(self) -> bool:
        """Nothing in the bundle contradicts anything else in it."""
        return not any(status == WRONG for status, _ in self.findings)

    def of(self, status: str) -> list[str]:
        return [text for found, text in self.findings if found == status]


def is_local_issuer(issuer: str | None) -> bool:
    host = (urlsplit(issuer or "").hostname or "").lower()
    return host in _LOCAL_HOSTS or host.endswith(_LOCAL_SUFFIXES)


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        return _object(json.loads(response.read()))


def _check_document(
    bundle: dict[str, Any],
    statement: dict[str, Any],
    report: Report,
    *,
    held: bytes | None,
) -> None:
    """The quote as a file: the bytes in the bundle, and the hash that is cited.

    The fingerprint proves the content. Which document was shown and decided
    on is a question about a file, answered with its bytes.
    """
    quote = _object(bundle.get("offerte"))
    cited = _object(statement.get("offerte")).get("bestand_sha256")
    carried = quote.get("bestand_b64")
    if not cited:
        if carried:
            report.wrong(
                "De bundel bevat een document, maar de verklaring noemt er geen."
            )
            return
        report.not_proven(
            "De verklaring noemt geen document: bewezen is over welke inhoud is "
            "besloten, niet welk bestand de persoon voor zich had."
        )
        return
    if not carried:
        report.wrong(
            "De verklaring noemt een document, maar het zit niet in de bundel."
        )
        return
    try:
        document = base64.b64decode(carried, validate=True)
    except (binascii.Error, ValueError):
        report.wrong("Het document in de bundel is niet te lezen.")
        return
    actual = sha256_hex(document)
    if actual != quote.get("bestand_sha256") or actual != cited:
        report.wrong(
            "Het document in de bundel is een ander bestand dan waarover is "
            "besloten: de hash komt niet overeen met de verklaring."
        )
        return
    inputs = _object(_object(statement.get("hoe")).get("nonce"))
    if inputs and (inputs.get("bestand_sha256") or "") != cited:
        report.wrong("De nonce is berekend voor een ander document.")
        return
    fixed = _object(statement.get("offerte")).get("bestand_vastgelegd")
    report.proven(
        f"Het document in de bundel (pdf, {len(document)} bytes) heeft hash "
        f"{actual}, de hash die de verklaring noemt" + (f"; {fixed}." if fixed else ".")
    )
    if fixed and "bij het maken" not in fixed:
        report.not_proven(
            "Het document is niet bij het maken van de offerte vastgelegd "
            f"({fixed}). Dat het zo is opgemaakt als toen, volgt er niet uit."
        )
    if held is None:
        return
    if sha256_hex(held) == actual:
        report.proven(
            "Het bestand dat u opgaf is byte voor byte het document waarover "
            "is besloten."
        )
    else:
        report.wrong(
            "Het bestand dat u opgaf is een ander bestand dan het document "
            "waarover is besloten."
        )


def _check_quote(bundle: dict[str, Any], report: Report) -> str | None:
    quote = _object(bundle.get("offerte"))
    try:
        canonical = base64.b64decode(quote.get("canoniek_b64") or "", validate=True)
    except (binascii.Error, ValueError):
        report.wrong("De offerte in de bundel is niet te lezen.")
        return None
    if not canonical:
        report.wrong("De bundel bevat geen offerte.")
        return None
    fingerprint = sha256_hex(canonical)
    if fingerprint != quote.get("vingerafdruk"):
        report.wrong(
            "De offerte in de bundel past niet bij de vingerafdruk die erbij "
            "staat: de offerte of de vingerafdruk is gewijzigd."
        )
        return None
    report.proven(
        f"De offerte in de bundel heeft vingerafdruk {fingerprint} "
        f"(kenmerk {quote.get('kenmerk') or 'onbekend'})."
    )
    return fingerprint


def _check_statement(
    bundle: dict[str, Any], fingerprint: str | None, report: Report
) -> tuple[dict[str, Any] | None, bytes | None]:
    part = _object(bundle.get("verklaring"))
    instance = _object(bundle.get("instantie"))
    try:
        statement, jws = read_statement(part.get("jws") or "", instance.get("sleutels"))
    except StatementError as exc:
        report.wrong(str(exc))
        return None, None
    if sha256_hex(jws.payload) != part.get("hash"):
        report.wrong(
            "De hash van de verklaring in de bundel klopt niet met de verklaring."
        )
        return None, None
    stated = _object(statement.get("offerte")).get("vingerafdruk")
    if fingerprint is not None and stated != fingerprint:
        report.wrong("De verklaring gaat over een andere offerte dan die in de bundel.")
        return None, None
    who = _object(statement.get("wie"))
    report.proven(
        "De verklaring is ondertekend met de sleutel van de instantie "
        f"{_object(statement.get('instantie')).get('naam') or instance.get('naam')!r} "
        "en is daarna niet gewijzigd. Zij zegt: "
        f"{who.get('naam')} ({who.get('email')}) besloot {statement.get('besluit')!r} "
        f"over deze offerte, ontvangen op "
        f"{_object(statement.get('wanneer')).get('ontvangen_op')}."
    )
    report.not_proven(
        "De sleutel van de instantie is door de instantie zelf gemaakt en is niet "
        "aan een organisatie gebonden: dat deze sleutel van deze organisatie is, "
        "volgt niet uit de bundel."
    )
    return statement, jws.payload


def _check_identity(
    bundle: dict[str, Any],
    statement: dict[str, Any],
    fingerprint: str | None,
    report: Report,
    *,
    online: bool,
) -> None:
    who = _object(statement.get("wie"))
    how = _object(statement.get("hoe"))
    login = _object(how.get("aanmelding"))
    identity = bundle.get("aanmelding")

    if not how.get("id_token_sha256"):
        if identity:
            report.wrong(
                "De bundel bevat een ID-token, maar de verklaring noemt er geen."
            )
            return
        report.not_proven(
            "Er is geen verklaring van een identiteitsprovider over wie besloot: "
            f"{login.get('ontbreekt_omdat') or 'de reden is niet vastgelegd'}. "
            "Wie besloot staat alleen in de verklaring van de instantie zelf."
        )
        return
    identity = _object(identity)
    id_token = identity.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        report.wrong(
            "De verklaring noemt een ID-token, maar het zit niet in de bundel."
        )
        return
    if sha256_hex(id_token.encode("ascii", "replace")) != how.get("id_token_sha256"):
        report.wrong(
            "Het ID-token in de bundel is een ander dan dat waar de verklaring "
            "naar verwijst."
        )
        return

    inputs = _object(how.get("nonce"))
    try:
        nonce = compute_nonce(inputs)
    except (KeyError, TypeError, ValueError):
        report.wrong(
            "De gegevens waaruit de nonce is berekend ontbreken of kloppen niet."
        )
        return
    if fingerprint is not None and inputs.get("vingerafdruk") != fingerprint:
        report.wrong("De nonce is berekend voor een andere offerte.")
        return
    if inputs.get("besluit") != statement.get("besluit"):
        report.wrong(
            "De nonce is berekend voor een ander besluit dan in de verklaring staat."
        )
        return
    if (inputs.get("kenmerk") or "") != (
        _object(statement.get("offerte")).get("kenmerk") or ""
    ):
        report.wrong("De nonce is berekend voor een ander kenmerk.")
        return

    issuer = who.get("uitgever") or ""
    try:
        facts = check_id_token(
            id_token,
            identity.get("sleutels"),
            issuer=issuer,
            client_id=login.get("client_id") or "",
            nonce=nonce,
        )
    except IdTokenError as exc:
        report.wrong(str(exc))
        return
    if facts.subject != who.get("subject"):
        report.wrong("Het ID-token gaat over een andere persoon dan de verklaring.")
        return
    if facts.email and who.get("email") and facts.email != who.get("email"):
        report.wrong(
            "Het e-mailadres in het ID-token is een ander dan in de verklaring."
        )
        return
    discovery = _object(identity.get("ontdekking"))
    if discovery and discovery.get("issuer") not in (None, issuer):
        report.wrong(
            "De bewaarde gegevens van de identiteitsprovider horen bij een "
            "andere uitgever."
        )
        return

    report.proven(
        f"De identiteitsprovider {issuer} heeft een ID-token ondertekend voor "
        f"{facts.name or facts.subject}"
        + (f" ({facts.email})" if facts.email else "")
        + ". De handtekening klopt met de sleutels in de bundel."
    )
    report.proven(
        "Dat ID-token is afgegeven voor een aanmelding die aan precies dit "
        f"besluit ({statement.get('besluit')}) over precies deze offerte is "
        "gebonden: de nonce in het token is opnieuw berekend uit de vingerafdruk, "
        "de hash van het document, het besluit, het kenmerk en de willekeurige "
        "waarde in de verklaring, en komt overeen."
    )

    received = _object(statement.get("wanneer")).get("ontvangen_op")
    try:
        moment = datetime.fromisoformat(received)
    except (TypeError, ValueError):
        moment = None
    age = facts.age_at(moment) if moment is not None else None
    if facts.auth_time is None:
        report.not_proven(
            "De identiteitsprovider zegt niet wanneer de persoon zich aanmeldde "
            "(geen auth_time). Dat de persoon zich voor dit besluit opnieuw "
            "aanmeldde is daarmee niet bewezen."
        )
    elif moment is not None and facts.fresh_at(moment):
        report.proven(
            f"De persoon meldde zich {age} seconden voor het besluit aan bij de "
            f"identiteitsprovider (aangemeld op {facts.auth_time.isoformat()}), "
            f"binnen de grens van {FRESH_SECONDS} seconden."
        )
    else:
        report.not_proven(
            "De aanmelding bij de identiteitsprovider was niet vers: "
            f"{age if age is not None else 'onbekend aantal'} seconden voor het "
            "besluit. De provider heeft het opnieuw aanmelden niet uitgevoerd, of "
            "de persoon was al langer aangemeld. Bewezen is dat deze identiteit "
            "bij dit verzoek hoorde, niet dat de persoon op dat moment zelf "
            "opnieuw inlogde."
        )
    if login.get("vers") is True and not (moment and facts.fresh_at(moment)):
        report.wrong(
            "De verklaring noemt de aanmelding vers, maar het ID-token zegt "
            "iets anders."
        )
    if facts.acr or facts.amr:
        report.proven(
            "De provider vermeldt het niveau van de aanmelding: "
            f"acr={facts.acr or 'geen'}, amr={', '.join(facts.amr) or 'geen'}."
        )
    else:
        report.not_proven(
            "De provider vermeldt niet hoe de persoon zich aanmeldde (geen acr of "
            "amr): met welk middel, en of er een tweede factor was, is niet bekend."
        )
    report.not_proven(
        "Geeft deze identiteitsprovider het inloggen door aan een andere partij "
        "(bijvoorbeeld SSO Rijk), dan zegt het tijdstip van aanmelden iets over "
        "de sessie bij deze provider. Dat de persoon bij die andere partij "
        "opnieuw zijn wachtwoord of pas gebruikte, volgt er niet uit."
    )
    if is_local_issuer(issuer):
        report.not_proven(
            f"De identiteitsprovider ({issuer}) is een lokale testomgeving: "
            "iedereen met toegang tot die machine kan er een persoon in aanmaken."
        )

    key = find_key(identity.get("sleutels"), _kid_of(id_token))
    if not online:
        report.not_proven(
            "De sleutels van de identiteitsprovider komen uit de bundel. Dat het "
            "de sleutels van die provider zijn is niet nagegaan; controleer dat "
            "met --online zolang de provider ze publiceert."
        )
        return
    try:
        meta = _fetch_json(f"{issuer.rstrip('/')}/.well-known/openid-configuration")
        published = _fetch_json(str(meta.get("jwks_uri")))
    except Exception as exc:  # any network or parsing failure
        report.not_proven(
            "De sleutels van de identiteitsprovider konden niet worden "
            f"opgehaald ({exc})."
        )
        return
    current = find_key(published, _kid_of(id_token))
    if current is not None and key is not None and _same_key(current, key):
        report.proven(
            "De sleutel waarmee het ID-token is ondertekend staat op dit moment "
            "bij de identiteitsprovider gepubliceerd."
        )
    else:
        report.not_proven(
            "De sleutel waarmee het ID-token is ondertekend staat niet meer bij "
            "de identiteitsprovider gepubliceerd. Sleutels wisselen; dit zegt "
            "niet dat de sleutel onecht is."
        )


def _check_passkey(
    bundle: dict[str, Any], statement: dict[str, Any], report: Report
) -> None:
    """The passkey assertion, when the decision was confirmed with one.

    The statement (signed by the instance) holds the public key, the
    relying party and the inputs of the challenge; the bundle holds what
    the device signed. Nothing is said when no passkey was used.
    """
    from grip.proof.jose import b64url_decode
    from grip.proof.passkey import (
        PasskeyError,
        assertion_hash,
        check_assertion,
        compute_challenge,
    )

    stated = _object(statement.get("hoe")).get("passkey")
    carried = _object(bundle.get("passkey")).get("assertion")
    if stated is None and carried is None:
        return
    if not isinstance(stated, dict):
        report.wrong(
            "De bundel bevat een bevestiging met een passkey, maar de verklaring "
            "noemt er geen."
        )
        return
    if not isinstance(carried, dict):
        report.not_proven(
            "De verklaring noemt een bevestiging met een passkey, maar die zit "
            "niet in de bundel en is dus niet na te gaan."
        )
        return
    if assertion_hash(carried) != stated.get("assertion_sha256"):
        report.wrong(
            "De bevestiging met een passkey in de bundel is een andere dan die de "
            "verklaring noemt."
        )
        return
    inputs = _object(stated.get("uitdaging"))
    quote = _object(statement.get("offerte"))
    try:
        challenge = compute_challenge(inputs)
    except (KeyError, TypeError, ValueError):
        report.wrong("De uitdaging van de passkey is niet te berekenen.")
        return
    if inputs.get("vingerafdruk") != quote.get("vingerafdruk"):
        report.wrong("De passkey tekende voor een andere offerte.")
        return
    if (inputs.get("bestand_sha256") or "") != (quote.get("bestand_sha256") or ""):
        report.wrong("De passkey tekende voor een ander document.")
        return
    if inputs.get("besluit") != statement.get("besluit"):
        report.wrong("De passkey tekende voor een ander besluit.")
        return
    try:
        facts = check_assertion(
            carried,
            public_key_cose=b64url_decode(str(stated.get("publieke_sleutel_cose"))),
            challenge=challenge,
            rp_id=str(stated.get("rp_id") or ""),
            origin=str(stated.get("origin") or ""),
        )
    except (PasskeyError, ValueError) as exc:
        report.wrong(f"De bevestiging met een passkey klopt niet: {exc}")
        return
    report.proven(
        "Een passkey tekende voor precies dit besluit: de uitdaging is berekend "
        "uit de vingerafdruk van de offerte, de hash van het document, het "
        "besluit en het kenmerk, en de handtekening klopt met de publieke "
        f"sleutel in de verklaring (op {stated.get('origin')})."
    )
    if facts.user_verified:
        report.proven(
            "Het apparaat met de passkey meldde dat het zijn gebruiker heeft "
            "geverifieerd (vingerafdruk, gezicht of pincode) voor deze handeling."
        )
    registration = _object(stated.get("registratie"))
    when = registration.get("geregistreerd_op") or "onbekend"
    if registration.get("uitgever"):
        how = (
            f"in een sessie die was aangemeld bij {registration.get('uitgever')} "
            f"als {registration.get('subject')}"
        )
    else:
        how = str(registration.get("ontbreekt_omdat") or "zonder bekende aanmelding")
    report.not_proven(
        f"De passkey is op {when} in deze instantie vastgelegd, {how}. Dat de "
        "passkey bij deze persoon hoort berust op die registratie van de "
        "instantie. Welke mens het apparaat bediende is hiermee niet bewezen."
    )


def _kid_of(compact: str) -> str | None:
    try:
        header = json.loads(
            base64.urlsafe_b64decode(
                compact.split(".")[0] + "=" * (-len(compact.split(".")[0]) % 4)
            )
        )
    except (ValueError, IndexError):
        return None
    return header.get("kid") if isinstance(header, dict) else None


def _same_key(a: dict[str, Any], b: dict[str, Any]) -> bool:
    members = ("kty", "n", "e", "crv", "x", "y")
    return all(a.get(m) == b.get(m) for m in members)


def _check_timestamp(
    bundle: dict[str, Any],
    payload: bytes,
    report: Report,
    *,
    tsa_roots: list[bytes] | None,
) -> None:
    stamp = bundle.get("tijdstempel")
    if not stamp:
        report.not_proven(
            "Er is geen onafhankelijke tijdstempel: het tijdstip van het besluit "
            "is de klok van de instantie die het vastlegde."
        )
        return
    from grip.proof import timestamp

    try:
        reply = timestamp.decode(_object(stamp).get("antwoord_b64") or "")
        facts = timestamp.read_timestamp(reply, payload, roots=tsa_roots)
    except (timestamp.TimestampError, ValueError, binascii.Error) as exc:
        report.wrong(f"De tijdstempel klopt niet: {exc}")
        return
    who = facts.signer or _object(stamp).get("autoriteit") or "onbekend"
    if facts.chain_verified:
        report.proven(
            f"De tijdstempelautoriteit ({who}) verklaart dat deze verklaring "
            f"bestond op {facts.time.isoformat()}; de handtekening is "
            "gecontroleerd tot het opgegeven rootcertificaat."
        )
    else:
        report.proven(
            f"De tijdstempel is over precies deze verklaring gezet en noemt "
            f"{facts.time.isoformat()} als tijdstip."
        )
        report.not_proven(
            f"De handtekening van de tijdstempelautoriteit ({who}) is niet "
            "gecontroleerd: geef het rootcertificaat van de autoriteit mee met "
            "--tsa-root."
        )


def verify_bundle(
    bundle: dict[str, Any],
    *,
    online: bool = False,
    tsa_roots: list[bytes] | None = None,
    held_document: bytes | None = None,
) -> Report:
    """Check a bundle and report what it proves and what it does not."""
    report = Report()
    if not isinstance(bundle, dict) or bundle.get("soort") != BUNDLE_TYPE:
        report.wrong("Dit is geen bundel met bewijs van grip.")
        return report
    if bundle.get("versie") != BUNDLE_VERSION:
        report.wrong(f"Onbekende versie van de bundel: {bundle.get('versie')!r}.")
        return report

    fingerprint = _check_quote(bundle, report)
    statement, payload = _check_statement(bundle, fingerprint, report)
    if statement is None or payload is None:
        return report
    report.statement = statement
    _check_document(bundle, statement, report, held=held_document)
    _check_identity(bundle, statement, fingerprint, report, online=online)
    _check_passkey(bundle, statement, report)
    _check_timestamp(bundle, payload, report, tsa_roots=tsa_roots)

    authority = _object(statement.get("bevoegdheid"))
    basis = authority.get("grondslag") or "onbekend"
    if authority.get("recht"):
        basis += f" ({authority['recht']})"
    report.not_proven(
        f"Grip baseerde zich op: {basis}. Dat deze persoon namens de "
        "organisatie mocht beslissen (het mandaat) ligt buiten grip vast en is "
        "hiermee niet bewezen."
    )
    return report


def format_report(report: Report) -> str:
    lines: list[str] = []
    if report.sound:
        lines.append("De bundel is in zichzelf kloppend.")
    else:
        lines.append("DE BUNDEL KLOPT NIET.")
    for title, status in (
        ("Klopt niet", WRONG),
        ("Bewezen", PROVEN),
        ("Niet bewezen", NOT_PROVEN),
    ):
        items = report.of(status)
        if not items:
            continue
        lines.append("")
        lines.append(f"{title}:")
        lines.extend(f"  - {item}" for item in items)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m grip.proof.verify",
        description=(
            "Controleer een bundel met bewijs van een besluit, zonder toegang tot grip."
        ),
    )
    parser.add_argument("bundel", help="het bestand met de bundel (JSON)")
    parser.add_argument(
        "--online",
        action="store_true",
        help=(
            "vergelijk de sleutels van de identiteitsprovider met wat die nu publiceert"
        ),
    )
    parser.add_argument(
        "--tsa-root",
        action="append",
        default=[],
        metavar="BESTAND",
        help="rootcertificaat van de tijdstempelautoriteit (PEM of DER); mag vaker",
    )
    parser.add_argument(
        "--bestand",
        metavar="PDF",
        help="een offerte als bestand, om te vergelijken met het document in de bundel",
    )
    args = parser.parse_args(argv)
    try:
        bundle = json.loads(Path(args.bundel).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"De bundel is niet te lezen: {exc}", file=sys.stderr)
        return 2
    roots = [Path(path).read_bytes() for path in args.tsa_root]
    held = Path(args.bestand).read_bytes() if args.bestand else None
    report = verify_bundle(
        bundle, online=args.online, tsa_roots=roots or None, held_document=held
    )
    print(format_report(report))
    return 0 if report.sound else 1


if __name__ == "__main__":
    raise SystemExit(main())
