from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "contracts").exists():
            return parent
    return current.parents[min(2, len(current.parents) - 1)]


PROJECT_ROOT = _find_project_root()


class Settings(BaseSettings):
    app_name: str = "KISANAI C2C"
    app_env: Literal["development", "test", "production"] = "development"
    node_id: str = "india-node"
    node_country_code: str = "IN"
    auth_mode: Literal["local", "firebase"] = "local"
    expert_subjects: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    store_provider: Literal["sqlite", "firestore"] = "sqlite"
    sqlite_path: str = str(PROJECT_ROOT / "work" / "kisanai-c2c.sqlite3")
    firestore_database: str = "kisanai-c2c"
    media_provider: Literal["local", "gcs"] = "local"
    media_directory: str = str(PROJECT_ROOT / "work" / "media")
    media_bucket: str | None = None
    media_max_bytes: int = 8 * 1024 * 1024

    google_cloud_project: str | None = None
    vertex_location: str = "global"
    ai_provider: Literal["vertex", "gemini_api"] = "vertex"
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str | None = None
    ai_enabled: bool = True

    imd_enabled: bool = True
    imd_base_url: str = "https://api.imd.gov.in"
    imd_api_key: str | None = None
    imd_jwt_token: str | None = None
    imd_email: str | None = None
    imd_password: str | None = None
    imd_auth_mode: Literal["none", "header", "query", "jwt", "unverified"] = "jwt"
    imd_auth_header_name: str | None = None
    imd_auth_query_name: str = "api_key"
    imd_auth_scheme: str = ""
    imd_retry_attempts: int = 1
    open_meteo_enabled: bool = True
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    earth_engine_enabled: bool = False
    google_maps_api_key: str | None = None

    speech_enabled: bool = False
    speech_location: str = "global"
    default_locale: str = "en-IN"

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def expert_subject_set(self) -> set[str]:
        return {item.strip() for item in self.expert_subjects.split(",") if item.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_production(self):
        if self.app_env == "production":
            if self.auth_mode != "firebase":
                raise ValueError("AUTH_MODE=firebase is required in production")
            if self.store_provider != "firestore":
                raise ValueError("STORE_PROVIDER=firestore is required in production")
            if self.media_provider != "gcs" or not self.media_bucket:
                raise ValueError("MEDIA_PROVIDER=gcs and MEDIA_BUCKET are required in production")
            if not self.google_cloud_project:
                raise ValueError("GOOGLE_CLOUD_PROJECT is required in production")
            if self.imd_enabled and self.imd_auth_mode == "unverified":
                raise ValueError("IMD authentication must be verified before enabling it in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
