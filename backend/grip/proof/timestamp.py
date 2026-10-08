"""A trusted time for a statement, from a time-stamping authority (RFC 3161).

Without it, the time in a statement is the clock of the instance that made
it: the party that keeps the record also says when it was made. A
time-stamping authority signs a hash together with its own time, so a third
party vouches that the statement existed at that moment.

Asking for a timestamp sends only the SHA-256 of the statement to the
authority, never the statement.

This module needs ``rfc3161-client``. It is imported where it is used, so
the rest of the package works without it and says so.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any

TIMESTAMP_QUERY = "application/timestamp-query"
TIMESTAMP_REPLY = "application/timestamp-reply"


class TimestampError(Exception):
    """No timestamp could be obtained, or one does not verify."""


def available() -> bool:
    try:
        import rfc3161_client  # noqa: F401
    except ImportError:
        return False
    return True


def build_request(message: bytes) -> bytes:
    """The DER of a timestamp request over ``message`` (hashed with SHA-512)."""
    from rfc3161_client import TimestampRequestBuilder

    return TimestampRequestBuilder().data(message).build().as_bytes()


async def request_timestamp(
    message: bytes, authority_url: str, *, http_client: Any, timeout: float = 15.0
) -> bytes:
    """Ask the authority for a timestamp over ``message``; returns the reply (DER).

    The reply is checked to be a granted timestamp over this message before
    it is returned: a reply that does not fit is not stored as evidence.
    """
    if not authority_url.lower().startswith(("https://", "http://")):
        raise TimestampError("Het adres van de tijdstempelautoriteit is geen URL.")
    try:
        response = await http_client.post(
            authority_url,
            content=build_request(message),
            headers={"Content-Type": TIMESTAMP_QUERY},
            timeout=timeout,
        )
    except Exception as exc:  # network errors of any client
        raise TimestampError(
            f"De tijdstempelautoriteit is niet bereikbaar: {exc}"
        ) from exc
    if response.status_code != 200:
        raise TimestampError(
            f"De tijdstempelautoriteit antwoordde met status {response.status_code}."
        )
    reply = bytes(response.content)
    read_timestamp(reply, message)
    return reply


@dataclass(frozen=True)
class TimestampFacts:
    time: datetime
    # Names in the certificates the authority sent along, for the reader.
    signer: str | None
    policy: str | None
    # True when the signature was verified up to a given root certificate.
    chain_verified: bool


def _digest(name: str, message: bytes) -> bytes:
    import hashlib

    return hashlib.new(name, message).digest()


def read_timestamp(
    reply: bytes, message: bytes, *, roots: list[bytes] | None = None
) -> TimestampFacts:
    """What a timestamp reply states about ``message``.

    Always checked: the reply is a granted timestamp and its hash is the
    hash of ``message``. With ``roots`` (PEM or DER certificates) the
    signature of the authority is verified up to one of them. Without, the
    time is read but nobody is vouched for: the result says which.
    """
    try:
        from cryptography import x509
        from rfc3161_client import VerifierBuilder, decode_timestamp_response
    except ImportError as exc:
        raise TimestampError(
            "De tijdstempel kan hier niet worden gelezen: rfc3161-client ontbreekt."
        ) from exc

    try:
        response = decode_timestamp_response(reply)
    except Exception as exc:
        raise TimestampError(
            "Dit is geen antwoord van een tijdstempelautoriteit."
        ) from exc
    info = getattr(response, "tst_info", None)
    if info is None:
        raise TimestampError("De autoriteit heeft geen tijdstempel afgegeven.")

    imprint = info.message_imprint
    algorithm = getattr(imprint.hash_algorithm, "name", "").lower()
    names = [algorithm] if algorithm in ("sha256", "sha384", "sha512") else []
    names += [n for n in ("sha512", "sha256", "sha384") if n not in names]
    if not any(_digest(name, message) == bytes(imprint.message) for name in names):
        raise TimestampError("De tijdstempel is over een ander document gezet.")

    signer = None
    certificates = []
    try:
        certificates = list(response.signed_data.certificates)
    except Exception:
        certificates = []
    for raw in certificates:
        try:
            cert = x509.load_der_x509_certificate(bytes(raw))
        except Exception:
            continue
        # The authority's own certificate, not the root it may send along.
        if cert.subject != cert.issuer or signer is None:
            signer = cert.subject.rfc4514_string()

    chain_verified = False
    if roots:
        builder = VerifierBuilder()
        loaded = 0
        for root in roots:
            try:
                cert = (
                    x509.load_pem_x509_certificate(root)
                    if b"-----BEGIN" in root
                    else x509.load_der_x509_certificate(root)
                )
            except Exception as exc:
                raise TimestampError(
                    "Een opgegeven rootcertificaat is niet te lezen."
                ) from exc
            builder = builder.add_root_certificate(cert)
            loaded += 1
        if loaded:
            try:
                builder.build().verify_message(response, message)
            except Exception as exc:
                raise TimestampError(
                    f"De handtekening van de tijdstempelautoriteit klopt niet: {exc}"
                ) from exc
            chain_verified = True

    policy = getattr(info, "policy", None)
    return TimestampFacts(
        time=info.gen_time,
        signer=signer,
        policy=str(getattr(policy, "dotted_string", policy)) if policy else None,
        chain_verified=chain_verified,
    )


def encode(reply: bytes) -> str:
    return base64.b64encode(reply).decode("ascii")


def decode(text: str) -> bytes:
    return base64.b64decode(text)
