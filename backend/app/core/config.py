from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "MICEPP-Tracker"
    app_version: str = "0.1.0"
    app_log_level: str = "INFO"
    app_secret_key: str = "development-only-change-me"
    database_url: str = "postgresql+asyncpg://micepp:micepp@localhost:5432/micepp"
    redis_url: str = "redis://localhost:6379/0"
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8080",
        "http://localhost:5173",
    ]
    expected_database_revision: str = "20260714_0010"
    import_max_file_bytes: int = 5 * 1024 * 1024
    import_max_uncompressed_bytes: int = 20 * 1024 * 1024
    import_max_rows: int = 1000
    import_max_columns: int = 50
    import_timeout_seconds: int = 15
    ai_provider: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: Annotated[int, Field(ge=5, le=120)] = 30
    scan_detector_mode: Literal["mock", "nmap", "web", "combined"] = "mock"
    scan_tasks_eager: bool = False
    allowed_scan_networks: Annotated[list[str], NoDecode] = []
    allow_private_network_scans: bool = False
    max_scan_duration_seconds: int = 600
    scan_max_ports: int = 100
    scan_max_redirects: int = 3
    web_scan_max_body_bytes: Annotated[int, Field(ge=65_536, le=10_485_760)] = 2_097_152
    web_scan_max_assets: Annotated[int, Field(ge=0, le=32)] = 8
    web_scan_max_asset_bytes: Annotated[int, Field(ge=65_536, le=5_242_880)] = 1_048_576
    nmap_binary: str = "nmap"
    whatweb_enabled: bool = True
    whatweb_binary: str = "/opt/whatweb/whatweb"
    whatweb_timeout_seconds: Annotated[int, Field(ge=5, le=120)] = 30
    nvd_mode: Literal["mock", "live", "disabled"] = "mock"
    nvd_api_key: str | None = None
    nvd_cpe_url: str = "https://services.nvd.nist.gov/rest/json/cpes/2.0"
    nvd_cve_url: str = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    cve_api_url: str = "https://cveawg.mitre.org/api/cve"
    nvd_timeout_seconds: int = 30
    nvd_cache_ttl_seconds: int = 86_400
    nvd_max_pages: int = 20
    nvd_min_cpe_confidence: float = 0.82
    osv_mode: Literal["live", "mock", "disabled"] = "disabled"
    osv_api_url: str = "https://api.osv.dev/v1"
    deps_dev_api_url: str = "https://api.deps.dev/v3"
    osv_timeout_seconds: int = 20
    realtime_default_interval_seconds: int = 3600
    realtime_min_interval_seconds: int = 60
    realtime_batch_size: int = 25
    realtime_max_concurrency: int = 2
    realtime_lock_ttl_seconds: int = 3600
    realtime_scheduler_poll_seconds: int = 60
    realtime_tasks_eager: bool = False
    expensive_rate_window_seconds: Annotated[int, Field(ge=1, le=3600)] = 60
    manual_service_check_rate_limit: Annotated[int, Field(ge=1, le=1000)] = 10
    scan_create_rate_limit: Annotated[int, Field(ge=1, le=1000)] = 5
    import_upload_rate_limit: Annotated[int, Field(ge=1, le=1000)] = 5
    ai_categorization_rate_limit: Annotated[int, Field(ge=1, le=1000)] = 10
    realtime_run_rate_limit: Annotated[int, Field(ge=1, le=1000)] = 2
    jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    jwt_private_key: str | None = None
    jwt_public_key: str | None = None
    jwt_access_ttl_seconds: int = 900
    # Long-lived refresh cookies avoid interrupting dedicated dashboard sessions.
    # Access tokens remain short-lived and are transparently renewed by the client.
    jwt_refresh_ttl_seconds: int = 315_360_000
    jwt_remember_refresh_ttl_seconds: int = 315_360_000
    refresh_cookie_name: str = "micepp_refresh"
    csrf_cookie_name: str = "micepp_csrf"
    auth_cookie_path: str = "/api/v1/auth"
    login_max_attempts: int = 5
    login_rate_window_seconds: int = 300
    login_lock_seconds: int = 900
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str | None = None
    bootstrap_admin_display_name: str = "Administrateur"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("allowed_scan_networks", mode="before")
    @classmethod
    def parse_scan_networks(cls, value: object) -> object:
        if isinstance(value, str):
            return [network.strip() for network in value.split(",") if network.strip()]
        return value

    @model_validator(mode="after")
    def reject_default_secret_in_production(self) -> "Settings":
        if self.app_env == "production" and self.app_secret_key == "development-only-change-me":
            raise ValueError("APP_SECRET_KEY must be configured in production")
        if self.app_env == "production" and self.jwt_algorithm != "RS256":
            raise ValueError("JWT_ALGORITHM must be RS256 in production")
        if self.app_env == "production" and (
            not self.allowed_origins or "*" in self.allowed_origins
        ):
            raise ValueError("ALLOWED_ORIGINS must contain explicit origins in production")
        if self.jwt_algorithm == "RS256" and not (self.jwt_private_key and self.jwt_public_key):
            raise ValueError("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are required for RS256")
        return self

    @property
    def jwt_signing_key(self) -> str:
        if self.jwt_algorithm == "RS256":
            assert self.jwt_private_key is not None
            return self.jwt_private_key
        return self.app_secret_key

    @property
    def jwt_verification_key(self) -> str:
        if self.jwt_algorithm == "RS256":
            assert self.jwt_public_key is not None
            return self.jwt_public_key
        return self.app_secret_key

    @property
    def secure_cookies(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
