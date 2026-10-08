"""Signing an acceptance and verifying it. Needs no database."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from grip.core.config import get_settings
from grip.federation import signing

from .conftest import example


@pytest.fixture
def settings():
    return get_settings().model_copy(
        update={
            "FEDERATION_SIGNING_KEY": signing.generate_private_key_pem(),
            "FEDERATION_SIGNING_KID": "",
        }
    )


def _unsigned() -> dict:
    acceptance = example("acceptance")
    del acceptance["jws"]
    return acceptance


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_round_trip(settings):
    acceptance = _unsigned()
    acceptance["jws"] = signing.sign_acceptance(acceptance, settings)
    signing.verify_acceptance(acceptance, signing.own_jwks(settings))


def test_header_names_es256_and_the_published_key(settings):
    jws = signing.sign_acceptance(_unsigned(), settings)
    header = json.loads(base64.urlsafe_b64decode(jws.split(".")[0] + "=="))
    key = signing.own_jwks(settings)["keys"][0]
    assert header == {"alg": "ES256", "kid": key["kid"]}
    assert signing.jws_kid(jws) == key["kid"]
    assert key["kid"] == signing.jwk_thumbprint(key)
    assert "d" not in key


@pytest.mark.parametrize(
    "field,value",
    [
        ("quote_hash", "0" * 64),
        ("signed_at", "2026-06-11T14:30:00+02:00"),
        ("form", "signing_link"),
        ("signer", {"name": "Iemand Anders", "email": "ander@opdrachtgever.example"}),
    ],
)
def test_changed_field_is_detected(settings, field, value):
    acceptance = _unsigned()
    acceptance["jws"] = signing.sign_acceptance(acceptance, settings)
    acceptance[field] = value
    with pytest.raises(signing.SignatureInvalidError, match="other content"):
        signing.verify_acceptance(acceptance, signing.own_jwks(settings))


def test_changed_signature_is_detected(settings):
    acceptance = _unsigned()
    header, payload, signature = signing.sign_acceptance(acceptance, settings).split(
        "."
    )
    raw = bytearray(base64.urlsafe_b64decode(signature + "=="))
    raw[0] ^= 0x01
    acceptance["jws"] = f"{header}.{payload}.{_b64(bytes(raw))}"
    with pytest.raises(signing.SignatureInvalidError, match="does not verify"):
        signing.verify_acceptance(acceptance, signing.own_jwks(settings))


def test_another_key_does_not_verify(settings):
    acceptance = _unsigned()
    acceptance["jws"] = signing.sign_acceptance(acceptance, settings)
    other = settings.model_copy(
        update={"FEDERATION_SIGNING_KEY": signing.generate_private_key_pem()}
    )
    jwks = signing.own_jwks(other)
    # Same kid, other key: the lookup succeeds, the signature must not.
    jwks["keys"][0]["kid"] = signing.own_jwks(settings)["keys"][0]["kid"]
    with pytest.raises(signing.SignatureInvalidError, match="does not verify"):
        signing.verify_acceptance(acceptance, jwks)


def test_unknown_kid_is_refused(settings):
    acceptance = _unsigned()
    acceptance["jws"] = signing.sign_acceptance(acceptance, settings)
    with pytest.raises(signing.SignatureInvalidError, match="does not publish"):
        signing.verify_acceptance(acceptance, example("jwks"))


@pytest.mark.parametrize("algorithm", ["none", "HS256", "RS256"])
def test_other_algorithms_are_refused(settings, algorithm):
    acceptance = _unsigned()
    _, payload, signature = signing.sign_acceptance(acceptance, settings).split(".")
    kid = signing.own_jwks(settings)["keys"][0]["kid"]
    header = _b64(json.dumps({"alg": algorithm, "kid": kid}).encode())
    acceptance["jws"] = f"{header}.{payload}.{signature}"
    with pytest.raises(signing.SignatureInvalidError, match="ES256 or PS256"):
        signing.verify_acceptance(acceptance, signing.own_jwks(settings))


def test_ps256_from_a_peer_verifies():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "rsa-1",
        "alg": "PS256",
        "n": _b64(numbers.n.to_bytes(256, "big")),
        "e": _b64(numbers.e.to_bytes(3, "big")),
    }
    acceptance = _unsigned()
    header = _b64(json.dumps({"alg": "PS256", "kid": "rsa-1"}).encode())
    payload = _b64(signing.canonical_json(signing.signed_fields(acceptance)))
    signature = private_key.sign(
        f"{header}.{payload}".encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )
    acceptance["jws"] = f"{header}.{payload}.{_b64(signature)}"
    signing.verify_acceptance(acceptance, {"keys": [jwk]})

    acceptance["quote_hash"] = "1" * 64
    with pytest.raises(signing.SignatureInvalidError):
        signing.verify_acceptance(acceptance, {"keys": [jwk]})


def test_key_for_another_algorithm_is_refused(settings):
    acceptance = _unsigned()
    acceptance["jws"] = signing.sign_acceptance(acceptance, settings)
    jwks = signing.own_jwks(settings)
    jwks["keys"][0]["alg"] = "PS256"
    with pytest.raises(signing.SignatureInvalidError, match="not meant"):
        signing.verify_acceptance(acceptance, jwks)


def test_deployed_instance_without_key_cannot_sign():
    settings = get_settings().model_copy(
        update={"FEDERATION_SIGNING_KEY": "", "PUBLIC_HOST": "https://grip.example"}
    )
    assert signing.own_jwks(settings) == {"keys": []}
    with pytest.raises(signing.SigningError):
        signing.sign_acceptance(_unsigned(), settings)


def test_local_run_gets_a_throwaway_key():
    settings = get_settings().model_copy(
        update={"FEDERATION_SIGNING_KEY": "", "PUBLIC_HOST": ""}
    )
    acceptance = _unsigned()
    acceptance["jws"] = signing.sign_acceptance(acceptance, settings)
    signing.verify_acceptance(acceptance, signing.own_jwks(settings))


def test_retired_keys_stay_published(settings):
    retired = example("jwks")
    with_retired = settings.model_copy(
        update={"FEDERATION_RETIRED_JWKS": json.dumps(retired)}
    )
    kids = [key["kid"] for key in signing.own_jwks(with_retired)["keys"]]
    assert kids[1:] == ["voorbeeld-2026-01"] and len(kids) == 2
    # An acceptance signed with the retired key still verifies.
    signing.verify_acceptance(example("acceptance"), signing.own_jwks(with_retired))


def test_pem_with_escaped_newlines_is_accepted(settings):
    escaped = settings.model_copy(
        update={
            "FEDERATION_SIGNING_KEY": settings.FEDERATION_SIGNING_KEY.replace(
                "\n", "\\n"
            )
        }
    )
    assert signing.own_jwks(escaped) == signing.own_jwks(settings)
