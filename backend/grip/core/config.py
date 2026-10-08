from functools import lru_cache
from urllib.parse import quote, urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_DATABASE_URL = "postgresql+asyncpg://grip:grip@localhost:5434/grip"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Grip"
    DEBUG: bool = False

    # Instance identity. Every organisation (or part of one) runs its own
    # instance; these values say which one this is.
    INSTANCE_NAME: str = "Grip (lokaal)"
    # Base of every URI this instance mints: {base}/id/opdracht/{uuid}.
    INSTANCE_BASE_URI: str = "http://localhost:8010"
    # TOOI URI of the nearest registered organisation.
    INSTANCE_TOOI_URI: str = ""
    # Own identifier, for instances smaller than a registered organisation.
    INSTANCE_KEY: str = "lokaal"
    PARENT_INSTANCE_URI: str = ""

    # Database: either provide DATABASE_URL directly, or the individual
    # components that the ZAD platform injects.
    DATABASE_URL: str = ""
    DATABASE_SERVER_HOST: str = ""
    DATABASE_SERVER_PORT: str = "5432"
    DATABASE_SERVER_USER: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_DB: str = ""
    DATABASE_SCHEMA: str = ""

    # OIDC: either provide OIDC_ISSUER directly, or OIDC_URL + OIDC_REALM
    # (ZAD platform).
    OIDC_ISSUER: str = ""
    OIDC_URL: str = ""
    OIDC_REALM: str = ""
    OIDC_CLIENT_ID: str = "grip"
    OIDC_CLIENT_SECRET: str = ""
    OIDC_DISCOVERY_URL: str = ""

    # Explicit opt-in to run without authentication. Without OIDC every
    # /api/ route would be open, so the app refuses to start in that state
    # unless this is set. Local development only.
    DEV_NO_AUTH: bool = False

    # Comma-separated email addresses that get the beheerder function at
    # startup. This is how the first beheerder of an instance comes to exist.
    BOOTSTRAP_BEHEERDER_EMAILS: str = ""

    # Public host injected by ZAD (e.g. https://component-2.grip.example).
    # Also the marker for "this is a deployed environment".
    PUBLIC_HOST: str = ""

    FRONTEND_URL: str = ""
    BACKEND_URL: str = ""
    SESSION_SECRET_KEY: str = "change-me-in-production"
    SESSION_COOKIE_DOMAIN: str = ""
    SESSION_COOKIE_SECURE: bool = False
    SESSION_TTL_SECONDS: int = 60 * 60 * 24 * 7

    CORS_ORIGINS: list[str] = Field(default_factory=list)

    @property
    def bootstrap_beheerder_emails(self) -> list[str]:
        return [
            e.strip().lower()
            for e in self.BOOTSTRAP_BEHEERDER_EMAILS.split(",")
            if e.strip()
        ]

    @model_validator(mode="after")
    def _build_database_url(self) -> "Settings":
        """Build DATABASE_URL from individual components if not set."""
        if not self.DATABASE_URL and self.DATABASE_SERVER_HOST:
            user = quote(self.DATABASE_SERVER_USER, safe="")
            password = quote(self.DATABASE_PASSWORD, safe="")
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{user}:{password}"
                f"@{self.DATABASE_SERVER_HOST}:{self.DATABASE_SERVER_PORT}"
                f"/{self.DATABASE_DB}"
            )
        if not self.DATABASE_URL:
            self.DATABASE_URL = _LOCAL_DATABASE_URL
        return self

    @model_validator(mode="after")
    def _derive_oidc_issuer(self) -> "Settings":
        """Build OIDC_ISSUER from the ZAD env vars if not set."""
        if not self.OIDC_ISSUER and self.OIDC_URL and self.OIDC_REALM:
            self.OIDC_ISSUER = f"{self.OIDC_URL.rstrip('/')}/realms/{self.OIDC_REALM}"
        return self

    _INSECURE_SECRET_DEFAULTS = frozenset(
        {"change-me-in-production", "local-dev-secret-key"}
    )

    @model_validator(mode="after")
    def _validate_session_secret(self) -> "Settings":
        """Reject the default SESSION_SECRET_KEY when OIDC is enabled."""
        if (
            self.OIDC_ISSUER
            and self.SESSION_SECRET_KEY in self._INSECURE_SECRET_DEFAULTS
        ):
            raise ValueError(
                "SESSION_SECRET_KEY must be set to a secure random value "
                "when OIDC is configured. Do not use the default."
            )
        return self

    @model_validator(mode="after")
    def _validate_auth_configured(self) -> "Settings":
        """Fail closed when authentication is not configured.

        DEV_NO_AUTH is honoured only outside a deployed environment.
        PUBLIC_HOST is injected by ZAD for every deployed component and is
        never set locally, so it is the production marker: one stray env var
        cannot open up a deployed instance.

        Runs after _derive_oidc_issuer so a ZAD-derived issuer counts.
        """
        if self.DEV_NO_AUTH and self.PUBLIC_HOST:
            raise ValueError(
                "DEV_NO_AUTH mag niet aan staan in een gedeployde omgeving "
                "(PUBLIC_HOST is gezet). Zet OIDC_ISSUER (of OIDC_URL + "
                "OIDC_REALM) zodat authenticatie actief is."
            )
        if self.DEV_NO_AUTH and self.OIDC_ISSUER:
            raise ValueError(
                "DEV_NO_AUTH en OIDC_ISSUER zijn allebei gezet. Kies een van "
                "de twee: met OIDC is er geen ontwikkelmodus zonder login."
            )
        if not self.OIDC_ISSUER and not self.DEV_NO_AUTH:
            raise ValueError(
                "Authenticatie is niet geconfigureerd: OIDC_ISSUER ontbreekt. "
                "Zet OIDC_ISSUER (of OIDC_URL + OIDC_REALM), of zet "
                "DEV_NO_AUTH=1 om bewust zonder authenticatie te draaien "
                "(alleen voor lokale ontwikkeling)."
            )
        return self

    @model_validator(mode="after")
    def _derive_urls_and_cookies(self) -> "Settings":
        """Derive URLs and cookie settings from PUBLIC_HOST when not set.

        On ZAD the frontend is component-1 and the backend component-2 of
        one project, on sibling hostnames. The session and CSRF cookies are
        therefore set on the shared parent domain.
        """
        if self.PUBLIC_HOST:
            parsed = urlparse(self.PUBLIC_HOST)
            hostname = parsed.hostname or ""

            if not self.BACKEND_URL:
                self.BACKEND_URL = self.PUBLIC_HOST.rstrip("/")
            if not self.FRONTEND_URL:
                for prefix in ("component-2.", "component-2-"):
                    if hostname.startswith(prefix):
                        self.FRONTEND_URL = f"https://{hostname[len(prefix) :]}"
                        break
            if not self.SESSION_COOKIE_DOMAIN and "." in hostname:
                self.SESSION_COOKIE_DOMAIN = f".{hostname.split('.', 1)[1]}"
            if parsed.scheme == "https":
                self.SESSION_COOKIE_SECURE = True

        if not self.BACKEND_URL:
            self.BACKEND_URL = "http://localhost:8010"
        if not self.FRONTEND_URL:
            self.FRONTEND_URL = "http://localhost:5183"
        if not self.CORS_ORIGINS:
            self.CORS_ORIGINS = [self.FRONTEND_URL]
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
