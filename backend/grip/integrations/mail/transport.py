"""Hand one message to the relay over SMTP.

The standard library does this; it blocks, so the outbox calls it in a
thread. An answer of the relay is sorted into "will not change by trying
again" and "try again later", each with a short code the outbox stores.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from grip.integrations.mail.config import (
    TLS_IMPLICIT,
    TLS_STARTTLS,
    MailConfig,
)

_TIMEOUT_SECONDS = 20

RECIPIENT_REFUSED = "recipient_refused"
MESSAGE_REFUSED = "message_refused"
LIMIT_REACHED = "limit_reached"
LOGIN_REFUSED = "login_refused"
RELAY_UNREACHABLE = "relay_unreachable"
RELAY_BUSY = "relay_busy"


class MailError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class PermanentMailError(MailError):
    """The relay understood the message and refused it."""


class TemporaryMailError(MailError):
    """Not sent now; a later attempt may succeed."""


def _context(config: MailConfig) -> ssl.SSLContext:
    if not config.tls_verify:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    return ssl.create_default_context(cafile=config.tls_ca_file or None)


def _text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _from_response(code: int, message: bytes | str, *, recipient: bool) -> MailError:
    detail = f"{code} {_text(message)}"
    # 4.4.5 and 4.7.x are how a relay says that an account is over its limit.
    if code in (421, 450, 451, 452) and "limit" in detail.lower():
        return TemporaryMailError(LIMIT_REACHED, detail)
    if 400 <= code < 500:
        return TemporaryMailError(RELAY_BUSY, detail)
    return PermanentMailError(
        RECIPIENT_REFUSED if recipient else MESSAGE_REFUSED, detail
    )


def send(config: MailConfig, message: EmailMessage, recipient: str) -> None:
    """Send one message to one recipient. Raises a MailError when not sent."""
    try:
        if config.tls == TLS_IMPLICIT:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                config.host,
                config.port,
                timeout=_TIMEOUT_SECONDS,
                context=_context(config),
            )
        else:
            client = smtplib.SMTP(config.host, config.port, timeout=_TIMEOUT_SECONDS)
    except (OSError, smtplib.SMTPException) as exc:
        raise TemporaryMailError(RELAY_UNREACHABLE, repr(exc)) from exc
    try:
        try:
            client.ehlo()
            if config.tls == TLS_STARTTLS:
                client.starttls(context=_context(config))
                client.ehlo()
            if config.username:
                client.login(config.username, config.password)
            refused = client.send_message(
                message, from_addr=config.from_address, to_addrs=[recipient]
            )
        except smtplib.SMTPAuthenticationError as exc:
            # A setting of the instance, not a property of the message.
            raise TemporaryMailError(
                LOGIN_REFUSED, f"{exc.smtp_code} {_text(exc.smtp_error)}"
            ) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            code, text = next(iter(exc.recipients.values()), (550, b"refused"))
            raise _from_response(code, text, recipient=True) from exc
        except smtplib.SMTPResponseException as exc:
            raise _from_response(
                exc.smtp_code, exc.smtp_error, recipient=False
            ) from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise TemporaryMailError(RELAY_UNREACHABLE, repr(exc)) from exc
        if refused:
            code, text = next(iter(refused.values()))
            raise _from_response(code, text, recipient=True)
    finally:
        try:
            client.quit()
        except (OSError, smtplib.SMTPException):
            client.close()
