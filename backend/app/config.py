"""Application settings, read from environment variables (and a local .env file).

C# comparison: this is IOptions<T> bound from appsettings.json / environment variables.
Pydantic validates the types at startup, so a bad value fails fast instead of at first use.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 127.0.0.1, not "localhost": Docker publishes the ports on IPv4 only, and on Windows
    # "localhost" tries IPv6 first and can hang for minutes before falling back.
    database_url: str = "postgresql+psycopg://cic:cic@127.0.0.1:5432/cic"
    rabbitmq_url: str = "amqp://cic:cic@127.0.0.1:5672/%2F"
    log_level: str = "INFO"
    environment: str = "local"


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor. lru_cache makes it behave like services.AddSingleton<Settings>()."""
    return Settings()
