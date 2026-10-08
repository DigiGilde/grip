"""The mail settings of an instance, read from the environment."""

from __future__ import annotations

import re
from dataclasses import dataclass

from grip.core.config import Settings, get_settings

TLS_STARTTLS = "starttls"
TLS_IMPLICIT = "tls"
TLS_NONE = "none"
TLS_MODES = (TLS_STARTTLS, TLS_IMPLICIT, TLS_NONE)

# What a display name may not hold: it goes into a header, and the platform
# relay refuses the same characters (line ends, "@", angle brackets, quotes,
# backslash, dollar sign).
_UNSAFE_IN_NAME = re.compile(r'[@<>"$\\\x00-\x1f\x7f]')
_MAX_NAME_LENGTH = 64


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    tls: str
    tls_verify: bool
    tls_ca_file: str


def mail_config(settings: Settings | None = None) -> MailConfig | None:
    """The relay to send through, or None when mail is not configured."""
    settings = settings or get_settings()
    host = settings.SMTP_HOST.strip()
    from_address = settings.SMTP_FROM.strip()
    if not host or not from_address:
        return None
    tls = settings.SMTP_TLS.strip().lower() or TLS_STARTTLS
    if tls not in TLS_MODES:
        raise ValueError(f"SMTP_TLS is one of {', '.join(TLS_MODES)}, not {tls!r}")
    return MailConfig(
        host=host,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        from_address=from_address,
        tls=tls,
        tls_verify=settings.SMTP_TLS_VERIFY,
        tls_ca_file=settings.SMTP_TLS_CA_FILE.strip(),
    )


def is_configured(settings: Settings | None = None) -> bool:
    return mail_config(settings) is not None


def display_name(name: str) -> str:
    """A name that is safe next to an address in a header."""
    cleaned = _UNSAFE_IN_NAME.sub(" ", name)
    return " ".join(cleaned.split())[:_MAX_NAME_LENGTH].strip()
