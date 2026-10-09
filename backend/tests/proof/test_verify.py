"""A bundle is checked with nothing but the bundle, and any change shows."""

from __future__ import annotations

import base64
import copy
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from grip.federation.signing import SigningKey
from grip.proof.bundle import build_bundle, render_page
from grip.proof.idtoken import IdTokenError, check_id_token
from grip.proof.jose import b64url, b64url_decode, sha256_hex
from grip.proof.nonce import compute_nonce, new_salt, nonce_inputs
from grip.proof.statement import (
    Authentication,
    Authority,
    build_statement,
    columns,
    parse_statement,
    sign_statement,
)
from grip.proof.verify import format_report, main, verify_bundle
from tests.proof.idp import CLIENT_ID, ISSUER, StandInProvider

QUOTE = b'{"kenmerk":"DG-2026-0007","regels":[],"totaal":{"bedrag_centen":17280000}}'
OTHER_QUOTE = b'{"kenmerk":"DG-2026-0008","regels":[],"totaal":{"bedrag_centen":1}}'
REFERENCE = "DG-2026-0007"
PDF = b"%PDF-1.7\n% de offerte zoals zij is opgemaakt\n%%EOF\n"
OTHER_PDF = b"%PDF-1.7\n% dezelfde inhoud, ander briefhoofd\n%%EOF\n"
FIXED = "document vastgelegd bij het maken van de offerte, op 08-10-2026"
NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def provider() -> StandInProvider:
    return StandInProvider()


@pytest.fixture(scope="module")
def instance_key() -> SigningKey:
    return SigningKey(
        private_key=ec.generate_private_key(ec.SECP256R1()), kid="instantie-1"
    )


def _bundle(
    provider: StandInProvider | None,
    key: SigningKey,
    *,
    action: str = "accept",
    auth_age: int | None = 5,
    claim_fresh: bool | None = None,
    quote: bytes = QUOTE,
    document: bytes | None = PDF,
    fixed: str = FIXED,
) -> dict:
    fingerprint = sha256_hex(quote)
    document_hash = sha256_hex(document) if document else None
    inputs = nonce_inputs(
        quote_fingerprint=fingerprint,
        document_sha256=document_hash,
        action=action,
        reference=REFERENCE,
        salt=new_salt(),
    )
    if provider is not None:
        token = provider.id_token(
            nonce=compute_nonce(inputs), auth_age=auth_age, now=NOW.timestamp()
        )
        fresh = auth_age is not None and auth_age <= 300
        authentication = Authentication(
            requested={"prompt": "login", "max_age": 0},
            client_id=provider.client_id,
            auth_time=NOW - timedelta(seconds=auth_age)
            if auth_age is not None
            else None,
            fresh=fresh if claim_fresh is None else claim_fresh,
            age_seconds=auth_age,
            id_token_sha256=sha256_hex(token.encode()),
            nonce_inputs=inputs,
        )
    else:
        token = None
        authentication = Authentication(
            requested=None,
            client_id=None,
            auth_time=None,
            fresh=None,
            age_seconds=None,
            absent_reason="deze instantie draait zonder identiteitsprovider",
        )
    statement = build_statement(
        statement_id=str(uuid.uuid4()),
        action=action,
        channel="signing_link",
        quote_fingerprint=fingerprint,
        quote_reference=REFERENCE,
        quote_uri="https://grip.voorbeeld.example/id/offerte/x",
        quote_total_cents=17280000,
        document_sha256=document_hash,
        document_fixed=fixed if document else None,
        subject="sub-tekenaar" if provider else None,
        issuer=provider.issuer if provider else None,
        name="Gast Tekenaar",
        email="gast@opdrachtgever.example",
        email_verified=True if provider else None,
        function="Directeur",
        organisation_claimed=None,
        on_behalf_of={"name": "Voorbeeldministerie"},
        received_at=NOW,
        authentication=authentication,
        authority=Authority(
            basis="uitnodiging", since="2026-10-01", declared_by_signer=True
        ),
        instance_name="Grip voorbeeld",
        instance_base_uri="https://grip.voorbeeld.example",
    )
    signed = sign_statement(statement, private_key=key.private_key, kid=key.kid)
    return build_bundle(
        quote_canonical=quote,
        quote_fingerprint=fingerprint,
        quote_reference=REFERENCE,
        quote_uri="https://grip.voorbeeld.example/id/offerte/x",
        document=document,
        document_sha256=document_hash,
        document_fixed=fixed if document else None,
        statement_jws=signed.jws,
        statement_hash=signed.hash,
        id_token=token,
        idp_jwks=provider.jwks if provider else None,
        idp_discovery=provider.discovery if provider else None,
        instance_name="Grip voorbeeld",
        instance_base_uri="https://grip.voorbeeld.example",
        instance_jwks={"keys": [key.public_jwk]},
    )


# --- the nonce binds a token to one decision ----------------------------------


def test_the_nonce_depends_on_every_input():
    base = {
        "quote_fingerprint": "a" * 64,
        "action": "accept",
        "reference": REFERENCE,
        "salt": "00" * 32,
    }
    nonce = compute_nonce(nonce_inputs(**base))
    assert compute_nonce(nonce_inputs(**base)) == nonce
    for change in (
        {"quote_fingerprint": "b" * 64},
        {"action": "reject"},
        {"document_sha256": "c" * 64},
        {"reference": "DG-2026-0008"},
        {"salt": "11" * 32},
    ):
        assert compute_nonce(nonce_inputs(**{**base, **change})) != nonce, change


def test_a_token_for_another_quote_or_action_is_refused(provider):
    wanted = nonce_inputs(
        quote_fingerprint=sha256_hex(QUOTE),
        action="accept",
        reference=REFERENCE,
        salt="00" * 32,
    )
    for other in (
        {**wanted, "vingerafdruk": sha256_hex(OTHER_QUOTE)},
        {**wanted, "besluit": "afwijzing"},
        {**wanted, "bestand_sha256": sha256_hex(OTHER_PDF)},
        {**wanted, "zout": "11" * 32},
    ):
        token = provider.id_token(nonce=compute_nonce(other))
        with pytest.raises(IdTokenError, match="nonce"):
            check_id_token(
                token,
                provider.jwks,
                issuer=ISSUER,
                client_id=CLIENT_ID,
                nonce=compute_nonce(wanted),
            )
    # The token for exactly this decision is accepted.
    facts = check_id_token(
        provider.id_token(nonce=compute_nonce(wanted)),
        provider.jwks,
        issuer=ISSUER,
        client_id=CLIENT_ID,
        nonce=compute_nonce(wanted),
    )
    assert facts.subject == "sub-tekenaar" and facts.email_verified


def test_a_token_of_another_issuer_client_or_key_is_refused(provider):
    nonce = "n-1"
    token = provider.id_token(nonce=nonce)
    ok = {"issuer": ISSUER, "client_id": CLIENT_ID, "nonce": nonce}
    with pytest.raises(IdTokenError, match="uitgever"):
        check_id_token(
            token, provider.jwks, **{**ok, "issuer": "https://elders.example"}
        )
    with pytest.raises(IdTokenError, match="toepassing"):
        check_id_token(token, provider.jwks, **{**ok, "client_id": "andere-client"})
    stranger = StandInProvider()
    with pytest.raises(IdTokenError, match="ondertekend"):
        check_id_token(token, stranger.jwks, **ok)
    with pytest.raises(IdTokenError, match="ondertekend"):
        check_id_token(token, {"keys": []}, **ok)


def test_an_unsigned_token_is_refused(provider):
    header = b64url(json.dumps({"alg": "none"}).encode())
    payload = provider.id_token(nonce="n-1").split(".")[1]
    with pytest.raises(IdTokenError):
        check_id_token(
            f"{header}.{payload}.",
            provider.jwks,
            issuer=ISSUER,
            client_id=CLIENT_ID,
            nonce="n-1",
        )


def test_freshness_is_a_question_about_a_moment(provider):
    def facts(age):
        return check_id_token(
            provider.id_token(nonce="n", auth_age=age, now=NOW.timestamp()),
            provider.jwks,
            issuer=ISSUER,
            client_id=CLIENT_ID,
            nonce="n",
        )

    assert facts(5).fresh_at(NOW) is True
    assert facts(5).age_at(NOW) == 5
    # Logged in this morning: a session, not an authentication for this act.
    assert facts(4 * 3600).fresh_at(NOW) is False
    # The provider does not say when: not fresh, rather than assumed fresh.
    assert facts(None).fresh_at(NOW) is False
    assert facts(None).auth_time is None


# --- the bundle verifies offline -----------------------------------------------


def test_a_sound_bundle_says_what_is_proven_and_what_is_not(provider, instance_key):
    report = verify_bundle(_bundle(provider, instance_key))
    assert report.sound, format_report(report)
    proven = " ".join(report.of("bewezen"))
    assert sha256_hex(QUOTE) in proven
    assert "nonce" in proven and "akkoord" in proven
    assert "5 seconden voor het besluit" in proven
    assert "Gast Tekenaar" in proven

    unproven = " ".join(report.of("niet_bewezen"))
    assert "niet aan een organisatie gebonden" in unproven
    assert "geen onafhankelijke tijdstempel" in unproven
    assert "mandaat" in unproven
    assert "lokale testomgeving" in unproven  # the issuer is an .example host
    assert "SSO Rijk" in unproven
    assert "acr of amr" in unproven


def test_without_a_provider_the_identity_is_plainly_not_proven(instance_key):
    report = verify_bundle(_bundle(None, instance_key))
    assert report.sound
    assert not any("identiteitsprovider" in text for text in report.of("bewezen"))
    assert any(
        "geen verklaring van een identiteitsprovider" in text
        for text in report.of("niet_bewezen")
    )


def test_a_stale_authentication_is_recorded_as_weaker_not_as_fresh(
    provider, instance_key
):
    report = verify_bundle(_bundle(provider, instance_key, auth_age=4 * 3600))
    assert report.sound
    assert any("niet vers" in text for text in report.of("niet_bewezen"))
    assert not any("seconden voor het besluit aan" in t for t in report.of("bewezen"))
    # The binding to the document still holds; that part is proven.
    assert any("nonce" in text for text in report.of("bewezen"))


def test_a_statement_that_calls_a_stale_authentication_fresh_is_caught(
    provider, instance_key
):
    report = verify_bundle(
        _bundle(provider, instance_key, auth_age=4 * 3600, claim_fresh=True)
    )
    assert not report.sound
    assert any("vers" in text for text in report.of("fout"))


def test_a_missing_auth_time_is_not_proof_of_reauthentication(provider, instance_key):
    report = verify_bundle(_bundle(provider, instance_key, auth_age=None))
    assert report.sound
    assert any("geen auth_time" in text for text in report.of("niet_bewezen"))


def _flip(text: str) -> str:
    """The same base64url text with one character changed."""
    middle = len(text) // 2
    swap = "A" if text[middle] != "A" else "B"
    return text[:middle] + swap + text[middle + 1 :]


def _alter_quote(bundle):
    bundle["offerte"]["canoniek_b64"] = base64.b64encode(OTHER_QUOTE).decode()


def _alter_quote_and_fingerprint(bundle):
    _alter_quote(bundle)
    bundle["offerte"]["vingerafdruk"] = sha256_hex(OTHER_QUOTE)


def _alter_statement(bundle):
    header, payload, signature = bundle["verklaring"]["jws"].split(".")
    statement = json.loads(b64url_decode(payload))
    statement["wie"]["naam"] = "Iemand Anders"
    from grip.proof.statement import canonical

    body = canonical(statement)
    bundle["verklaring"]["jws"] = f"{header}.{b64url(body)}.{signature}"
    bundle["verklaring"]["hash"] = sha256_hex(body)


def _alter_statement_signature(bundle):
    header, payload, signature = bundle["verklaring"]["jws"].split(".")
    bundle["verklaring"]["jws"] = f"{header}.{payload}.{_flip(signature)}"


def _alter_token(bundle):
    header, payload, signature = bundle["aanmelding"]["id_token"].split(".")
    claims = json.loads(b64url_decode(payload))
    claims["sub"] = "iemand-anders"
    bundle["aanmelding"]["id_token"] = (
        f"{header}.{b64url(json.dumps(claims).encode())}.{signature}"
    )


def _swap_token(bundle):
    """A real token of the same provider, issued for another decision."""
    bundle["aanmelding"]["id_token"] = _OTHER_TOKEN


def _alter_document(bundle):
    """Same content, another lay-out: not the file that was decided on."""
    bundle["offerte"]["bestand_b64"] = base64.b64encode(OTHER_PDF).decode()


def _alter_document_and_its_hash(bundle):
    _alter_document(bundle)
    bundle["offerte"]["bestand_sha256"] = sha256_hex(OTHER_PDF)


def _drop_document(bundle):
    bundle["offerte"]["bestand_b64"] = None


def _alter_idp_keys(bundle):
    bundle["aanmelding"]["sleutels"] = StandInProvider().jwks


def _alter_instance_keys(bundle):
    stranger = ec.generate_private_key(ec.SECP256R1())
    key = SigningKey(private_key=stranger, kid="instantie-1")
    bundle["instantie"]["sleutels"] = {"keys": [key.public_jwk]}


def _drop_token(bundle):
    bundle["aanmelding"] = None


def _alter_discovery(bundle):
    bundle["aanmelding"]["ontdekking"]["issuer"] = "https://elders.example"


_OTHER_TOKEN = ""


@pytest.mark.parametrize(
    "alter",
    [
        _alter_quote,
        _alter_quote_and_fingerprint,
        _alter_statement,
        _alter_statement_signature,
        _alter_document,
        _alter_document_and_its_hash,
        _drop_document,
        _alter_token,
        _swap_token,
        _alter_idp_keys,
        _alter_instance_keys,
        _drop_token,
        _alter_discovery,
    ],
)
def test_any_altered_part_makes_the_bundle_fail(provider, instance_key, alter):
    global _OTHER_TOKEN  # noqa: PLW0603
    _OTHER_TOKEN = provider.id_token(nonce="voor-een-ander-besluit")
    bundle = _bundle(provider, instance_key)
    assert verify_bundle(copy.deepcopy(bundle)).sound
    alter(bundle)
    report = verify_bundle(bundle)
    assert not report.sound, alter.__name__
    assert report.of("fout"), alter.__name__


def test_the_file_is_proven_next_to_the_content(provider, instance_key):
    report = verify_bundle(_bundle(provider, instance_key))
    proven = " ".join(report.of("bewezen"))
    assert sha256_hex(PDF) in proven and "bij het maken" in proven


def test_a_file_someone_holds_is_compared_byte_for_byte(provider, instance_key):
    bundle = _bundle(provider, instance_key)
    same = verify_bundle(bundle, held_document=PDF)
    assert same.sound
    assert any("byte voor byte" in text for text in same.of("bewezen"))
    other = verify_bundle(bundle, held_document=OTHER_PDF)
    assert not other.sound
    assert any("ander bestand" in text for text in other.of("fout"))


def test_a_statement_without_a_file_proves_the_content_only(provider, instance_key):
    report = verify_bundle(_bundle(provider, instance_key, document=None))
    assert report.sound
    assert any("welk bestand" in text for text in report.of("niet_bewezen"))


def test_a_file_fixed_afterwards_is_said_to_be_so(provider, instance_key):
    late = "document vastgelegd na het maken van de offerte, op 08-10-2026"
    report = verify_bundle(_bundle(provider, instance_key, fixed=late))
    assert report.sound
    assert any(
        "niet bij het maken van de offerte vastgelegd" in text
        for text in report.of("niet_bewezen")
    )


def test_something_that_is_no_bundle_is_refused():
    assert not verify_bundle({}).sound
    assert not verify_bundle({"soort": "grip.bewijs", "versie": 99}).sound
    assert not verify_bundle([]).sound  # type: ignore[arg-type]


def test_the_command_checks_a_file_and_exits_accordingly(
    provider, instance_key, tmp_path, capsys
):
    bundle = _bundle(provider, instance_key)
    good = tmp_path / "bewijs.json"
    good.write_text(json.dumps(bundle), encoding="utf-8")
    assert main([str(good)]) == 0
    out = capsys.readouterr().out
    assert "De bundel is in zichzelf kloppend." in out
    assert "Bewezen:" in out and "Niet bewezen:" in out

    _alter_quote(bundle)
    bad = tmp_path / "gewijzigd.json"
    bad.write_text(json.dumps(bundle), encoding="utf-8")
    assert main([str(bad)]) == 1
    assert "DE BUNDEL KLOPT NIET." in capsys.readouterr().out

    assert main([str(tmp_path / "bestaat-niet.json")]) == 2

    held = tmp_path / "offerte.pdf"
    held.write_bytes(PDF)
    assert main([str(good), "--bestand", str(held)]) == 0
    assert "byte voor byte" in capsys.readouterr().out
    held.write_bytes(OTHER_PDF)
    assert main([str(good), "--bestand", str(held)]) == 1


# --- the statement is the decision ---------------------------------------------


def test_the_columns_are_read_from_the_statement(provider, instance_key):
    bundle = _bundle(provider, instance_key, action="reject")
    payload = b64url_decode(bundle["verklaring"]["jws"].split(".")[1])
    values = columns(parse_statement(payload))
    assert values == {
        "action": "reject",
        "channel": "signing_link",
        "quote_hash": sha256_hex(QUOTE),
        "document_sha256": sha256_hex(PDF),
        "signer_name": "Gast Tekenaar",
        "signer_email": "gast@opdrachtgever.example",
        "signer_function": "Directeur",
        "organisation": {"name": "Voorbeeldministerie"},
        "decided_at": NOW,
        "note": None,
    }


def test_the_page_says_what_is_proven_and_what_is_not(provider, instance_key):
    bundle = _bundle(provider, instance_key)
    report = verify_bundle(bundle)
    page = render_page(report.statement, report.findings)
    assert "<h1>Akkoordverklaring DG-2026-0007</h1>" in page
    assert "Gast Tekenaar gaf akkoord op offerte DG-2026-0007." in page
    assert "Niet bewezen:" in page and "Bewezen:" in page
    assert "mandaat" in page
    # Nothing a visitor typed can become markup.
    risky = _bundle(provider, instance_key)
    statement = parse_statement(b64url_decode(risky["verklaring"]["jws"].split(".")[1]))
    statement["wie"]["naam"] = "<script>x</script>"
    assert "<script>" not in render_page(statement, [])


def test_a_statement_from_an_example_instance_says_so(provider, instance_key):
    plain = verify_bundle(_bundle(provider, instance_key)).statement
    assert "voorbeeld" not in plain["instantie"]
    assert "geen echt document" not in render_page(plain, [])
    marked = {**plain, "instantie": {**plain["instantie"], "voorbeeld": True}}
    assert "Voorbeeld, geen echt document" in render_page(marked, [])
