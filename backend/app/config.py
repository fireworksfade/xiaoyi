from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "小yi API"
    app_env: str = "development"
    app_secret_key: str = "development-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./data/xiaoyi.db"
    frontend_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1"]
    session_cookie_name: str = "xiaoyi_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_ttl_hours: int = 24
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini"
    openai_api_mode: str = "responses"
    agent_runtime: str = "mock"
    seed_demo_users: bool = True

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("mcp_allowed_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_cookie_policy(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true")
        if self.is_production and self.app_secret_key in ("", "development-only-change-me"):
            raise ValueError("APP_SECRET_KEY must be set to a strong random value in production")
        if self.is_production and self.seed_demo_users:
            raise ValueError("SEED_DEMO_USERS must be false in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def ensure_local_paths(self) -> None:
        if self.database_url.startswith("sqlite"):
            Path("data").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
