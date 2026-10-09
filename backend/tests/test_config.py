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
        "OIDC_DISCOVERY_URL",
        "OIDC_ALLOW_INSECURE_HTTP",
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


def _deployed(public_host: str) -> Settings:
    return _settings(
        OIDC_ISSUER="https://kc.example/realms/x",
        SESSION_SECRET_KEY="a-real-secret-of-sufficient-length",
        PUBLIC_HOST=public_host,
    )


def test_one_address_for_all_components() -> None:
    """The platform sends / to the frontend and /api to the backend."""
    s = _deployed("https://grip.example")
    assert s.FRONTEND_URL == "https://grip.example"
    assert s.BACKEND_URL == "https://grip.example"
    assert s.SESSION_COOKIE_DOMAIN == ""
    assert s.SESSION_COOKIE_SECURE is True
    assert s.CORS_ORIGINS == ["https://grip.example"]
    assert s.PASSKEY_RP_ID == "grip.example"


def test_an_address_per_component_with_a_dot() -> None:
    s = _deployed("https://component-2.grip.example")
    assert s.FRONTEND_URL == "https://grip.example"
    # The browser only ever uses the frontend's address.
    assert s.BACKEND_URL == "https://grip.example"
    assert s.SESSION_COOKIE_DOMAIN == ""


def test_an_address_per_component_with_a_dash_never_shares_cookies() -> None:
    """On a domain shared with other projects a parent-domain cookie would
    hand the session to every one of them."""
    s = _deployed("https://component-2-main-grip.rijksapp.example")
    assert s.FRONTEND_URL == "https://component-1-main-grip.rijksapp.example"
    assert s.BACKEND_URL == "https://component-1-main-grip.rijksapp.example"
    assert s.SESSION_COOKIE_DOMAIN == ""


def test_explicit_addresses_win() -> None:
    s = _settings(
        OIDC_ISSUER="https://kc.example/realms/x",
        SESSION_SECRET_KEY="a-real-secret-of-sufficient-length",
        PUBLIC_HOST="https://component-2.grip.example",
        FRONTEND_URL="https://grip.organisatie.example",
        BACKEND_URL="https://grip.organisatie.example",
    )
    assert s.FRONTEND_URL == "https://grip.organisatie.example"
    assert s.PASSKEY_ORIGIN == "https://grip.organisatie.example"


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


# --- the identity provider must be reached over https -------------------------

_SECRET = "s" * 40


@pytest.mark.parametrize("name", ["OIDC_ISSUER", "OIDC_DISCOVERY_URL"])
def test_http_identity_provider_is_refused_at_startup(name):
    values = {
        "OIDC_ISSUER": "https://idp.example/realms/x",
        "SESSION_SECRET_KEY": _SECRET,
        name: "http://idp.example/realms/x",
    }
    with pytest.raises(ValidationError) as excinfo:
        _settings(**values)
    message = str(excinfo.value)
    assert name in message and "https" in message
    assert "OIDC_ALLOW_INSECURE_HTTP" in message


def test_http_identity_provider_is_allowed_with_the_local_opt_out():
    settings = _settings(
        OIDC_ISSUER="http://localhost:9080/realms/grip",
        SESSION_SECRET_KEY=_SECRET,
        OIDC_ALLOW_INSECURE_HTTP=True,
    )
    assert settings.OIDC_ISSUER.startswith("http://")


def test_the_opt_out_is_refused_when_deployed():
    with pytest.raises(ValidationError) as excinfo:
        _settings(
            OIDC_ISSUER="https://idp.example/realms/x",
            SESSION_SECRET_KEY=_SECRET,
            OIDC_ALLOW_INSECURE_HTTP=True,
            PUBLIC_HOST="https://component-2.grip.example",
        )
    assert "OIDC_ALLOW_INSECURE_HTTP" in str(excinfo.value)


def test_https_identity_provider_needs_no_opt_out():
    settings = _settings(
        OIDC_ISSUER="https://idp.example/realms/x", SESSION_SECRET_KEY=_SECRET
    )
    assert settings.OIDC_ALLOW_INSECURE_HTTP is False
