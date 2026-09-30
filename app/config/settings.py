from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite:///./data/app.db"
    app_timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"
    notion_token: str = ""
    notion_parent_page_id: str = ""
    notion_api_timeout: float = Field(default=30.0, gt=0)
    notion_max_retries: int = Field(default=3, ge=0, le=10)
    notion_rate_limit_per_second: float = Field(default=2.0, gt=0, le=10)
    sync_worker_poll_seconds: float = Field(default=5.0, gt=0)
    sync_worker_batch_size: int = Field(default=10, ge=1, le=100)

    @field_validator("database_url")
    @classmethod
    def resolve_database_url(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername == "sqlite" and url.database not in (None, ":memory:"):
            path = Path(url.database)
            if not path.is_absolute():
                return value.replace(url.database, (PROJECT_ROOT / path).resolve().as_posix(), 1)
        return value

    @field_validator("app_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
