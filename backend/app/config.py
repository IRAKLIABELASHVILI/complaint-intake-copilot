"""Application settings, read from environment variables (and a local .env file).

C# comparison: this is IOptions<T> bound from appsettings.json / environment variables.
Pydantic validates the types at startup, so a bad value fails fast instead of at first use.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://cic:cic@localhost:5432/cic"
    log_level: str = "INFO"
    environment: str = "local"


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor. lru_cache makes it behave like services.AddSingleton<Settings>()."""
    return Settings()
