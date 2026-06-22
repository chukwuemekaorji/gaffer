"""central place for env config. everything that touches the outside world
reads from here so we don't end up with os.getenv calls scattered around."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # most of these are empty for now and get filled in as we add features.
    # keeping them all in one model means missing keys fail loudly on startup
    # instead of halfway through a request.

    app_env: str = "dev"
    log_level: str = "INFO"

    # llm
    anthropic_api_key: str = ""

    # embeddings + rerank (added later)
    voyage_api_key: str = ""
    cohere_api_key: str = ""

    # database
    database_url: str = ""

    # cache + observability (added later)
    redis_url: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # stats
    football_data_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    # cached so we only parse the env once per process
    return Settings()