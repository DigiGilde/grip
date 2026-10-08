from decimal import Decimal
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

    # The organisation as it signs its documents. A quote is sent by the
    # organisation, not by the software instance: this name stands on the
    # quote as the sender. Empty falls back to INSTANCE_NAME.
    ORGANISATION_NAME: str = ""
    # What the organisation is part of, as further lines of the letterhead
    # under its name, separated by "|". For example
    # "Rijksorganisatie X|Ministerie van Y".
    LETTERHEAD_LINES: str = ""
    # Path of an SVG with the Rijkslint and the coat of arms. Only an
    # organisation that may carry the Rijkslogo sets this; without it a
    # document gets a plain, sober head. The design system package ships the
    # mark as favicon.svg; point to that file, do not copy it.
    LETTERHEAD_LOGO_PATH: str = ""
    # Directory with the Rijkshuisstijl typeface (RijksSansWeb-Regular.woff2
    # and -Italic.woff2), for an organisation that may use it. Without it a
    # document is set in the fallback the huisstijl names, Verdana, or the
    # nearest sans-serif the system has.
    DOCUMENT_FONT_DIR: str = ""
    # Prefix of the reference a quote gets when issued, as in "DG-2026-0007".
    # Empty derives it from INSTANCE_KEY.
    QUOTE_REFERENCE_PREFIX: str = ""
    # Conditions proposed when a quote is issued; the issuer can change them.
    QUOTE_DEFAULT_CONDITIONS: str = ""

    # Percentage the monthly rates go up by when a new rate card is started
    # as a copy of an earlier year. Only the default the beheerder is shown;
    # the percentage used is chosen per card and kept in its audit row.
    RATE_INDEXATION_DEFAULT_PCT: Decimal = Decimal("5")

    # Federation (FSC). Only grip.federation reads these settings.
    # Serve the routes that other organisations call. Off by default: the
    # listener must only be reachable from the FSC inway.
    FEDERATION_INBOUND_ENABLED: bool = False
    # Send outbox messages. Off by default; needs OUTWAY_URL.
    FEDERATION_OUTBOUND_ENABLED: bool = False
    # Header in which the inway passes on the peer id of the caller. Taken
    # from the 2023 reference implementation; verify against the deployed
    # FSC version before relying on it.
    FSC_PEER_ID_HEADER: str = "Fsc-Request-Peer-Id"
    # Address of the own FSC outway, without a path.
    OUTWAY_URL: str = ""
    # ES256 private key (PEM, PKCS8) this instance signs acceptances with.
    # Without it a local run gets a throwaway key; a deployed instance
    # cannot sign.
    FEDERATION_SIGNING_KEY: str = ""
    # Key id in the JWS header. Default: the RFC 7638 thumbprint of the key.
    FEDERATION_SIGNING_KID: str = ""
    # JWKS (JSON) with public keys that are no longer used for signing but
    # that earlier acceptances were signed with.
    FEDERATION_RETIRED_JWKS: str = ""
    FEDERATION_OUTBOX_INTERVAL_SECONDS: int = 15
    FEDERATION_MAX_ATTEMPTS: int = 12
    FEDERATION_HTTP_TIMEOUT_SECONDS: float = 20.0
    FEDERATION_JWKS_TTL_SECONDS: int = 3600
    CORPUS_CACHE_TTL_SECONDS: int = 300

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
    # Accept an identity provider over plain http. Local development only (a
    # Keycloak in a container); refused in a deployed environment.
    OIDC_ALLOW_INSECURE_HTTP: bool = False

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

    # VLAM, the language model the government operates itself (drafting of
    # vacancy texts). VLAM_API_URL is injected by the hosting platform's vlam
    # service as a base address without a path and wins over the manual
    # VLAM_BASE_URL. The key and the model are the instance's own settings;
    # the model must be one that the endpoint lists under /v1/models.
    # Without these, everything works except drafting.
    VLAM_API_URL: str = ""
    VLAM_BASE_URL: str = ""
    VLAM_API_KEY: str = ""
    VLAM_MODEL_ID: str = ""
    # Outgoing mail through an SMTP relay. On the hosting platform the
    # send-email service injects SMTP_HOST, SMTP_PORT, SMTP_USERNAME,
    # SMTP_PASSWORD and SMTP_FROM after an administrator approved its use;
    # the relay writes the From address itself. Without SMTP_HOST and
    # SMTP_FROM nothing is mailed and everything else works.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    # starttls (the submission port), tls (implicit, usually 465) or none
    # (a local mail catcher only).
    SMTP_TLS: str = "starttls"
    # The platform relay has a certificate of the cluster itself; verifying
    # it then needs SMTP_TLS_CA_FILE, or this switched off inside the
    # cluster network.
    SMTP_TLS_VERIFY: bool = True
    SMTP_TLS_CA_FILE: str = ""
    MAIL_OUTBOX_INTERVAL_SECONDS: int = 15
    MAIL_MAX_ATTEMPTS: int = 8

    # A few sentences about the organisation, given to the model as context
    # when it drafts a vacancy text. Must not contain names of people.
    VACANCY_ORGANISATION_DESCRIPTION: str = ""

    # Comma-separated IP addresses or CIDR ranges of the proxies in front of
    # the backend. Only from these are X-Forwarded-Proto, -Host and -For
    # believed. Empty: no forwarded header is trusted.
    TRUSTED_PROXIES: str = ""

    # Link with Wies (docs/wies.md). Each direction is off while unset.
    # WIES_BASE_URL + WIES_API_KEY: grip reads colleagues from Wies.
    # GRIP_EXPORT_KEY: the key Wies presents to pull the export from grip.
    # WIES_SUBORGANIZATIONS: comma-separated merken of Wies this instance
    # takes its people from; empty means all.
    WIES_BASE_URL: str = ""
    WIES_API_KEY: str = ""
    GRIP_EXPORT_KEY: str = ""
    WIES_SUBORGANIZATIONS: str = ""
    # The merk grip proposes a new colleague under when none is given.
    WIES_DEFAULT_SUBORGANIZATION: str = ""
    # Days a person record is kept after a hire fell through. Four weeks is a
    # common term; have the privacy officer confirm it for the organisation.
    PROSPECTIVE_RETENTION_DAYS: int = 28

    # Tasks: how often the worker brings the tasks of every open case in
    # line with the facts (a month that ended, a deadline that passed).
    # Zero switches the loop off; reading tasks still evaluates them.
    TASKS_EVALUATE_INTERVAL_SECONDS: int = 300

    # The event stream as other systems read it (docs/gebeurtenissen.md).
    # EVENTS_FEED_KEY: the key a system presents to read the feed. Empty
    # keeps the feed closed: nothing leaves the instance by default.
    # INSTANCE_OIN: the organisation identification number, for the source
    # of a CloudEvent (urn:nld:oin:<OIN>:systeem:grip-<INSTANCE_KEY>).
    # LOGBOEK_PROCESSING_ACTIVITY_URI: the entry of this processing in the
    # register of processing activities, for Logboek Dataverwerkingen.
    EVENTS_FEED_KEY: str = ""
    INSTANCE_OIN: str = ""
    LOGBOEK_PROCESSING_ACTIVITY_URI: str = ""

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
    def _validate_oidc_transport(self) -> "Settings":
        """Refuse an identity provider over plain http at startup.

        Tokens and the session checks travel to the provider. Over http the
        login itself would appear to succeed, after which no session is ever
        valid: the token checks refuse to send credentials over http. Failing
        here says so at once. The discovery document's own endpoints are
        checked when the application starts (grip.core.auth.check_oidc_transport).
        """
        if self.OIDC_ALLOW_INSECURE_HTTP and self.PUBLIC_HOST:
            raise ValueError(
                "OIDC_ALLOW_INSECURE_HTTP mag niet aan staan in een gedeployde "
                "omgeving (PUBLIC_HOST is gezet). De identiteitsprovider moet "
                "via https bereikbaar zijn."
            )
        if self.OIDC_ALLOW_INSECURE_HTTP:
            return self
        for name in ("OIDC_ISSUER", "OIDC_DISCOVERY_URL"):
            value = getattr(self, name)
            if value and not value.lower().startswith("https://"):
                raise ValueError(
                    f"{name} gebruikt geen https ({value}). Inloggen lijkt dan "
                    "te lukken, maar geen enkele sessie is daarna geldig. "
                    "Gebruik een https-adres, of zet voor lokale ontwikkeling "
                    "met een eigen identiteitsprovider OIDC_ALLOW_INSECURE_HTTP=1."
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
