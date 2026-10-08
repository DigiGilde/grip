"""Settings must fail closed: no accidental unauthenticated instance."""

import pytest
from pydantic import ValidationError

from grip.core.config import Settings


def _settings(**overrides) -> Settings:
    # _env_file=None keeps a developer's local .env out of the test.
    return Settings(_env_file=None, **overrides)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "DEV_NO_AUTH",
        "OIDC_ISSUER",
        "OIDC_URL",
        "OIDC_REALM",
        "PUBLIC_HOST",
        "SESSION_SECRET_KEY",
        "FRONTEND_URL",
        "BACKEND_URL",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_refuses_to_start_without_auth():
    with pytest.raises(ValidationError, match="OIDC_ISSUER ontbreekt"):
        _settings()


def test_dev_no_auth_allowed_locally():
    assert _settings(DEV_NO_AUTH=True).OIDC_ISSUER == ""


def test_dev_no_auth_refused_when_deployed():
    with pytest.raises(ValidationError, match="gedeployde omgeving"):
        _settings(DEV_NO_AUTH=True, PUBLIC_HOST="https://component-2.grip.example")


def test_dev_no_auth_refused_together_with_oidc():
    with pytest.raises(ValidationError, match="allebei gezet"):
        _settings(
            DEV_NO_AUTH=True,
            OIDC_ISSUER="https://idp.example/realms/x",
            SESSION_SECRET_KEY="s" * 40,
        )


def test_default_session_secret_refused_with_oidc():
    with pytest.raises(ValidationError, match="SESSION_SECRET_KEY"):
        _settings(OIDC_ISSUER="https://idp.example/realms/x")


def test_issuer_derived_from_zad_variables():
    s = _settings(
        OIDC_URL="https://idp.example/",
        OIDC_REALM="grip",
        SESSION_SECRET_KEY="s" * 40,
    )
    assert s.OIDC_ISSUER == "https://idp.example/realms/grip"


def test_urls_and_cookies_derived_from_public_host():
    s = _settings(
        OIDC_ISSUER="https://idp.example/realms/x",
        SESSION_SECRET_KEY="s" * 40,
        PUBLIC_HOST="https://component-2.grip.example",
    )
    assert s.BACKEND_URL == "https://component-2.grip.example"
    assert s.FRONTEND_URL == "https://grip.example"
    assert s.SESSION_COOKIE_DOMAIN == ".grip.example"
    assert s.SESSION_COOKIE_SECURE is True
    assert s.CORS_ORIGINS == ["https://grip.example"]


def test_local_defaults_use_grip_ports():
    s = _settings(DEV_NO_AUTH=True)
    assert s.BACKEND_URL == "http://localhost:8010"
    assert s.FRONTEND_URL == "http://localhost:5183"
    assert ":5434/" in s.DATABASE_URL


def test_bootstrap_emails_are_normalised():
    s = _settings(
        DEV_NO_AUTH=True, BOOTSTRAP_BEHEERDER_EMAILS=" A@Example.org, ,b@x.nl"
    )
    assert s.bootstrap_beheerder_emails == ["a@example.org", "b@x.nl"]
