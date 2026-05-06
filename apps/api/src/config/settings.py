from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder value — the application refuses to start in non-dev
# environments if ``jwt_secret_key`` is left at this literal.
_JWT_PLACEHOLDER = "CHANGE-ME-in-production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "ConsentOS API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    allowed_origins: str = "http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse allowed_origins as a comma-separated string."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # Database
    database_url: str = "postgresql+asyncpg://consentos:consentos@localhost:5432/consentos"
    database_echo: bool = False
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = _JWT_PLACEHOLDER
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Pseudonymisation — HMAC key for IP / UA hashing on consent records.
    # Defaults to deriving from the JWT secret if not explicitly set.
    pseudonymisation_secret: str | None = None

    # Bootstrap token — required as ``X-Admin-Bootstrap-Token`` on
    # ``POST /api/v1/organisations/``. When unset (the default), the
    # endpoint is disabled. Rotate or unset after your first org is
    # provisioned to prevent further tenant creation.
    admin_bootstrap_token: str | None = None

    # Initial admin bootstrap — on first startup, if the ``users`` table
    # is empty and both credentials below are set, the API creates an
    # organisation and an owner user so the operator can log in to the
    # admin UI for the first time. Idempotent: once any user exists this
    # is a no-op, so the variables can safely remain set across restarts.
    # Rotate the password via the admin UI after first login.
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    initial_admin_full_name: str = "Administrator"
    initial_org_name: str = "Default Organisation"
    initial_org_slug: str = "default"

    # CDN — public URL where banner scripts (consent-loader.js,
    # consent-bundle.js) are hosted. In dev the admin UI dog-foods
    # the banner so localhost:5173 works for testing; in production
    # this should be a real CDN URL (CloudFlare Pages, S3+CloudFront,
    # Cloud CDN, etc.) — see docs for setup.
    cdn_base_url: str = "http://localhost:5173"

    # Scanner service
    scanner_service_url: str = "http://localhost:8001"
    scanner_timeout_seconds: int = 300

    # IAB Global Vendor List — fetched daily by ``src.tasks.iab_gvl``
    # and cached in the ``iab_*`` tables (CMP-68). The default points at
    # the canonical IAB-hosted v3 GVL; override only when running offline
    # or pointing at a mirror for development.
    iab_gvl_url: str = "https://vendor-list.consensu.org/v3/vendor-list.json"
    iab_gvl_timeout_seconds: int = 30

    # Extra GeoIP country header — checked *before* the built-in list
    # (``cf-ipcountry``, ``x-vercel-ip-country``, ``x-appengine-country``,
    # ``x-country-code``). Set this when running behind a CDN/load
    # balancer that uses a non-standard header, e.g. Google Cloud
    # Load Balancer's ``x-gclb-country`` or an internal edge proxy.
    # Header names are case-insensitive. Leave unset if one of the
    # built-in headers is fine.
    geoip_country_header: str | None = None

    # Subdivision/state code header — optional companion to
    # ``GEOIP_COUNTRY_HEADER``. When both are set the API pairs them to
    # produce region keys like ``US-CA`` or ``GB-SCT`` (ISO 3166-2
    # subdivision without the country prefix). Different CDNs expose
    # this under different names: Cloudflare Enterprise uses
    # ``cf-region-code``, Vercel uses ``x-vercel-ip-country-region``,
    # GCP Load Balancer uses ``x-gclb-region``, CloudFront functions
    # use ``cloudfront-viewer-country-region``. Leave unset if you
    # only need country-level granularity.
    geoip_region_header: str | None = None

    # Local MaxMind GeoLite2/GeoIP2 City database — used as a fallback
    # when no CDN header is present. Download GeoLite2-City.mmdb from
    # https://dev.maxmind.com/geoip/geolite2-free-geolocation-data and
    # mount it into the container (e.g. ``/data/GeoLite2-City.mmdb``).
    # When unset, lookups fall back to the free external ip-api.com
    # service, which is rate-limited and should not be relied on in
    # production.
    geoip_maxmind_db_path: str | None = None

    # Rate limiting — on by default. Public endpoints (banner config +
    # consent submission) are internet-exposed and must not be DoS-able.
    # Auth endpoints get a stricter bucket via ``RateLimitMiddleware``.
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120

    # Anonymous telemetry — daily heartbeat reporting deployment metadata
    # and bucketed scale (no PII, no consent records, no domains). Default
    # on for production; auto-disabled in dev/test environments. Operators
    # can opt out with ``TELEMETRY_ENABLED=false``. Full payload schema
    # and audit instructions in ``docs/telemetry.md``.
    telemetry_enabled: bool = True
    telemetry_endpoint: str = "https://telemetry.consentos.dev/v1/heartbeat"
    telemetry_timeout_seconds: int = 10

    @property
    def telemetry_active(self) -> bool:
        """``True`` when telemetry should actually send.

        Combines the explicit opt-out flag with an automatic disable in
        dev/test environments so local runs and CI never phone home.
        """
        if not self.telemetry_enabled:
            return False
        return self.environment.lower() not in ("development", "dev", "local", "test")

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        """Refuse to start with unsafe defaults in non-dev environments."""
        if self.environment.lower() in ("development", "dev", "local", "test"):
            return self

        errors: list[str] = []

        if self.jwt_secret_key == _JWT_PLACEHOLDER:
            errors.append(
                "JWT_SECRET_KEY is set to the placeholder value "
                f"{_JWT_PLACEHOLDER!r}. Generate a strong random value "
                "(e.g. `openssl rand -base64 48`) and set it in the "
                "environment before starting the API."
            )

        if "*" in self.allowed_origins_list:
            errors.append(
                "ALLOWED_ORIGINS contains '*'. Wildcard CORS combined with "
                "allow_credentials=True is a credential-theft vector. "
                "Set ALLOWED_ORIGINS to an explicit list of trusted origins."
            )

        if errors:
            msg = "Refusing to start with unsafe configuration:\n  - " + "\n  - ".join(
                errors,
            )
            raise ValueError(msg)

        return self

    @property
    def pseudonymisation_key(self) -> bytes:
        """Return the HMAC key used for pseudonymising IP/UA values.

        If ``pseudonymisation_secret`` is not set, derives a per-instance
        key from the JWT secret so operators don't have to configure two
        secrets. Using JWT_SECRET directly is acceptable because the
        HMAC is one-way and the resulting hashes are not reversible.
        """
        source = self.pseudonymisation_secret or self.jwt_secret_key
        return source.encode("utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
