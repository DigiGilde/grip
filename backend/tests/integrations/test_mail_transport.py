"""The SMTP transport and the message it sends, without a network."""

from __future__ import annotations

import smtplib
import uuid
from datetime import UTC, datetime

import pytest

from grip.core.config import get_settings
from grip.integrations.mail import transport
from grip.integrations.mail.config import (
    MailConfig,
    display_name,
    is_configured,
    mail_config,
)
from grip.integrations.mail.outbox import build_message
from grip.models.mail_outbox import MailOutbox

CONFIG = MailConfig(
    host="relay.example",
    port=587,
    username="project",
    password="secret",
    from_address="noreply+project@voorbeeld.example",
    tls="starttls",
    tls_verify=True,
    tls_ca_file="",
)


def _row(**changes) -> MailOutbox:
    values = {
        "id": uuid.uuid4(),
        "kind": "signing_link",
        "dedupe_key": "k",
        "subject_kind": "quote_invitation",
        "subject_id": uuid.uuid4(),
        "recipient": "tekenaar@opdrachtgever.example",
        "reply_to": "manager@example.org",
        "sender_name": "Voorbeeldgilde",
        "subject": "Offerte VG-2026-0001 staat klaar",
        "text_body": "Tekst",
        "html_body": "<p>Tekst</p>",
        "status": "queued",
        "attempts": 0,
        "next_attempt_at": datetime.now(UTC),
    }
    return MailOutbox(**{**values, **changes})


class FakeSMTP:
    """Stands in for smtplib.SMTP and remembers what was asked of it."""

    calls: list[str]
    fail_at: str | None = None
    error: Exception | None = None
    refused: dict = {}

    def __init__(self, host, port, timeout=None, **kwargs):
        type(self).calls = [f"connect {host}:{port}"]
        self._step("connect")

    def _step(self, name):
        if type(self).fail_at == name and type(self).error is not None:
            raise type(self).error

    def ehlo(self):
        type(self).calls.append("ehlo")

    def starttls(self, context=None):
        type(self).calls.append("starttls")
        self._step("starttls")

    def login(self, user, password):
        type(self).calls.append(f"login {user}")
        self._step("login")

    def send_message(self, message, from_addr=None, to_addrs=None):
        type(self).calls.append(f"send {from_addr} -> {to_addrs}")
        self._step("send")
        return type(self).refused

    def quit(self):
        type(self).calls.append("quit")

    def close(self):
        pass


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.fail_at, FakeSMTP.error, FakeSMTP.refused = None, None, {}
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_mail_is_off_without_host_and_sender(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "SMTP_FROM", "")
    assert mail_config(settings) is None and not is_configured(settings)
    monkeypatch.setattr(settings, "SMTP_HOST", "relay.example")
    assert not is_configured(settings), "a sender address is needed too"
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply@voorbeeld.example")
    config = mail_config(settings)
    assert config is not None and config.port == 587 and config.tls == "starttls"
    monkeypatch.setattr(settings, "SMTP_TLS", "anders")
    with pytest.raises(ValueError):
        mail_config(settings)


def test_a_name_cannot_break_out_of_its_header():
    assert display_name('Dienst "X" <a@b.example>\r\nBcc: c@d.example') == (
        "Dienst X a b.example Bcc: c d.example"
    )
    assert len(display_name("n" * 200)) == 64


def test_the_message_has_text_and_plain_html_and_says_who_to_answer():
    message = build_message(_row(), CONFIG)
    assert message["From"] == "Voorbeeldgilde <noreply+project@voorbeeld.example>"
    assert message["To"] == "tekenaar@opdrachtgever.example"
    assert message["Reply-To"] == "manager@example.org"
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Message-ID"].endswith("@voorbeeld.example>")
    kinds = [part.get_content_type() for part in message.iter_parts()]
    assert kinds == ["text/plain", "text/html"]
    assert "Reply-To" not in build_message(_row(reply_to=None), CONFIG)


def test_sends_over_starttls_after_logging_in(smtp):
    transport.send(
        CONFIG, build_message(_row(), CONFIG), "tekenaar@opdrachtgever.example"
    )
    assert smtp.calls == [
        "connect relay.example:587",
        "ehlo",
        "starttls",
        "ehlo",
        "login project",
        "send noreply+project@voorbeeld.example -> ['tekenaar@opdrachtgever.example']",
        "quit",
    ]


def test_a_mail_catcher_needs_no_tls_and_no_login(smtp):
    plain = MailConfig(**{**CONFIG.__dict__, "tls": "none", "username": ""})
    transport.send(plain, build_message(_row(), plain), "a@b.example")
    assert "starttls" not in smtp.calls
    assert not any(call.startswith("login") for call in smtp.calls)


@pytest.mark.parametrize(
    ("fail_at", "error", "kind", "code"),
    [
        (
            "send",
            smtplib.SMTPRecipientsRefused({"a@b.example": (550, b"no such user")}),
            transport.PermanentMailError,
            transport.RECIPIENT_REFUSED,
        ),
        (
            "send",
            smtplib.SMTPDataError(554, b"message refused"),
            transport.PermanentMailError,
            transport.MESSAGE_REFUSED,
        ),
        (
            "send",
            smtplib.SMTPSenderRefused(452, b"4.4.5 Rate limit exceeded", "x"),
            transport.TemporaryMailError,
            transport.LIMIT_REACHED,
        ),
        (
            "send",
            smtplib.SMTPDataError(451, b"try again later"),
            transport.TemporaryMailError,
            transport.RELAY_BUSY,
        ),
        (
            "login",
            smtplib.SMTPAuthenticationError(535, b"bad credentials"),
            transport.TemporaryMailError,
            transport.LOGIN_REFUSED,
        ),
        (
            "connect",
            ConnectionRefusedError("refused"),
            transport.TemporaryMailError,
            transport.RELAY_UNREACHABLE,
        ),
        (
            "starttls",
            smtplib.SMTPNotSupportedError("STARTTLS not offered"),
            transport.TemporaryMailError,
            transport.RELAY_UNREACHABLE,
        ),
    ],
)
def test_an_answer_of_the_relay_is_permanent_or_worth_another_try(
    smtp, fail_at, error, kind, code
):
    smtp.fail_at, smtp.error = fail_at, error
    with pytest.raises(kind) as caught:
        transport.send(CONFIG, build_message(_row(), CONFIG), "a@b.example")
    assert caught.value.code == code


def test_a_recipient_refused_without_an_exception_is_still_a_refusal(smtp):
    smtp.refused = {"a@b.example": (550, b"mailbox unavailable")}
    with pytest.raises(transport.PermanentMailError) as caught:
        transport.send(CONFIG, build_message(_row(), CONFIG), "a@b.example")
    assert caught.value.code == transport.RECIPIENT_REFUSED
