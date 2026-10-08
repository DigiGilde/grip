"""The bundle: everything needed to check a decision, in one file.

Both parties keep the same file: the signer downloads it, the instance
stores what it is made of. It holds the quote in its canonical form, the
signed statement, the ID token the identity provider issued for this
decision with the keys that verify it, the keys of the instance, and an
optional timestamp. Written in Dutch terms (ADR 0019).
"""

from __future__ import annotations

import base64
import html
from datetime import datetime
from typing import Any

BUNDLE_TYPE = "grip.bewijs"
BUNDLE_VERSION = 1
BUNDLE_MEDIA_TYPE = "application/vnd.grip.bewijs+json"


def build_bundle(
    *,
    quote_canonical: bytes,
    quote_fingerprint: str,
    quote_reference: str | None,
    quote_uri: str,
    document: bytes | None = None,
    document_sha256: str | None = None,
    document_fixed: str | None = None,
    statement_jws: str,
    statement_hash: str,
    id_token: str | None,
    idp_jwks: dict[str, Any] | None,
    idp_discovery: dict[str, Any] | None,
    instance_name: str,
    instance_base_uri: str,
    instance_jwks: dict[str, Any],
    timestamp_reply: bytes | None = None,
    timestamp_authority: str | None = None,
) -> dict[str, Any]:
    return {
        "soort": BUNDLE_TYPE,
        "versie": BUNDLE_VERSION,
        "offerte": {
            "canoniek_b64": base64.b64encode(quote_canonical).decode("ascii"),
            "vingerafdruk": quote_fingerprint,
            "kenmerk": quote_reference,
            "uri": quote_uri,
            # The quote as the file that was shown and decided on.
            "bestand_b64": (
                base64.b64encode(document).decode("ascii") if document else None
            ),
            "bestand_sha256": document_sha256,
            "bestand_vastgelegd": document_fixed,
        },
        "verklaring": {"jws": statement_jws, "hash": statement_hash},
        "aanmelding": (
            {"id_token": id_token, "sleutels": idp_jwks, "ontdekking": idp_discovery}
            if id_token
            else None
        ),
        "instantie": {
            "naam": instance_name,
            "basis_uri": instance_base_uri,
            "sleutels": instance_jwks,
        },
        "tijdstempel": (
            {
                "antwoord_b64": base64.b64encode(timestamp_reply).decode("ascii"),
                "autoriteit": timestamp_authority,
            }
            if timestamp_reply
            else None
        ),
    }


DECISION_SENTENCES = {
    "akkoord": "gaf akkoord op",
    "afwijzing": "wees af:",
    "goedkeuring": "keurde intern goed:",
    "teruggestuurd": "stuurde terug naar de maker:",
}
CHANNEL_SENTENCES = {
    "tekenlink": "via een tekenlink in de instantie van de opdrachtnemer",
    "eigen_instantie": "in de eigen instantie van de opdrachtgever",
    "intern": "binnen de eigen organisatie",
    "document": "met een getekend document",
}


def _when(iso: str | None) -> str:
    if not iso:
        return "onbekend"
    moment = datetime.fromisoformat(iso)
    return moment.strftime("%d-%m-%Y %H:%M:%S %Z").strip()


def _row(label: str, value: str) -> str:
    return (
        f'<tr><th scope="row">{html.escape(label)}</th>'
        f"<td>{html.escape(value)}</td></tr>"
    )


def render_page(statement: dict[str, Any], findings: list[tuple[str, str]]) -> str:
    """The "Akkoordverklaring": the statement as a page a person can read.

    ``findings`` are the results of checking the bundle, as pairs of status
    ("bewezen", "niet_bewezen", "fout") and sentence. The page shows what is
    proven and, as plainly, what is not.
    """
    who = statement["wie"]
    quote = statement["offerte"]
    how = statement["hoe"]
    login = how["aanmelding"]
    authority = statement["bevoegdheid"]
    on_behalf = statement.get("namens") or {}
    decision = statement["besluit"]
    sentence = DECISION_SENTENCES.get(decision, decision)

    if how.get("id_token_sha256"):
        verified = (
            "Opnieuw aangemeld bij de identiteitsprovider voor dit besluit"
            if login.get("vers")
            else "Aangemeld bij de identiteitsprovider, maar niet opnieuw voor dit "
            "besluit"
        )
        age = login.get("leeftijd_seconden")
        if age is not None:
            verified += f" ({age} seconden voor het besluit)"
    else:
        verified = "Geen verklaring van een identiteitsprovider: " + str(
            login.get("ontbreekt_omdat") or "onbekend"
        )

    basis = authority.get("grondslag") or "onbekend"
    if authority.get("recht"):
        basis += f": {authority['recht']}"
    if authority.get("sinds"):
        basis += f", sinds {authority['sinds']}"
    if authority.get("toegekend_door"):
        basis += f", toegekend door {authority['toegekend_door']}"

    rows = [
        _row("Wie", f"{who.get('naam') or ''} ({who.get('email') or ''})"),
        _row("Functie", who.get("functie") or "niet opgegeven"),
        _row(
            "Namens",
            str(on_behalf.get("name") or on_behalf.get("naam") or "niet vastgelegd"),
        ),
        _row("Besluit", decision),
        _row("Offerte", f"{quote.get('kenmerk') or quote.get('uri')}"),
        _row("Vingerafdruk van de inhoud", quote.get("vingerafdruk") or ""),
        _row(
            "Hash van het document (pdf)",
            (quote.get("bestand_sha256") or "niet vastgelegd")
            + (
                f" ({quote['bestand_vastgelegd']})"
                if quote.get("bestand_vastgelegd")
                else ""
            ),
        ),
        _row("Ontvangen door grip op", _when(statement["wanneer"].get("ontvangen_op"))),
        _row("Aangemeld op", _when(statement["wanneer"].get("aangemeld_op"))),
        _row("Tijdbron", statement["wanneer"].get("tijdbron") or ""),
        _row("Hoe vastgesteld", verified),
        _row(
            "Kanaal", CHANNEL_SENTENCES.get(how.get("kanaal"), how.get("kanaal") or "")
        ),
        _row("Identiteitsprovider", who.get("uitgever") or "geen"),
        _row("Grondslag van de bevoegdheid", basis),
    ]
    if statement.get("toelichting"):
        rows.append(_row("Toelichting", statement["toelichting"]))

    marks = {"bewezen": "Bewezen", "niet_bewezen": "Niet bewezen", "fout": "Klopt niet"}
    listed = "\n".join(
        f'<li class="{html.escape(status)}">'
        f"<strong>{marks.get(status, status)}:</strong> "
        f"{html.escape(text)}</li>"
        for status, text in findings
    )
    title = f"Akkoordverklaring {quote.get('kenmerk') or ''}".strip()
    lead = (
        f"{html.escape(who.get('naam') or 'Onbekend')} {html.escape(sentence)} "
        f"offerte {html.escape(str(quote.get('kenmerk') or quote.get('uri') or ''))}."
    )
    return f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 46rem; margin: 2rem auto;
  padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }}
h1 {{ font-size: 1.6rem; }} h2 {{ font-size: 1.2rem; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; vertical-align: top; padding: .35rem .5rem;
  border-bottom: 1px solid #ddd; }}
th {{ width: 14rem; font-weight: 600; }}
td {{ overflow-wrap: anywhere; }}
li {{ margin-bottom: .4rem; }}
.fout {{ color: #a1260d; }}
@media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>{lead}</p>
<table>
{chr(10).join(rows)}
</table>
<h2>Wat hiermee is bewezen en wat niet</h2>
<ul>
{listed}
</ul>
<p>{html.escape(authority.get("toelichting") or "")}</p>
<p>Deze pagina is gemaakt uit de bundel met het bewijs. De bundel zelf is na te
rekenen zonder toegang tot grip, met het commando
<code>python -m grip.proof.verify</code>.</p>
</body>
</html>
"""
