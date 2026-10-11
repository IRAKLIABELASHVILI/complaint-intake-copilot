"""Application settings, read from environment variables (and a local .env file).

C# comparison: this is IOptions<T> bound from appsettings.json / environment variables.
Pydantic validates the types at startup, so a bad value fails fast instead of at first use.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProviderName = Literal["fake", "openai", "azure_openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 127.0.0.1, not "localhost": Docker publishes the ports on IPv4 only, and on Windows
    # "localhost" tries IPv6 first and can hang for minutes before falling back.
    database_url: str = "postgresql+psycopg://cic:cic@127.0.0.1:5432/cic"
    rabbitmq_url: str = "amqp://cic:cic@127.0.0.1:5672/%2F"
    log_level: str = "INFO"
    environment: str = "local"
    allow_demo_tokens: bool = False

    # The fake provider needs no key, so the demo and the tests run offline and free.
    llm_provider: LlmProviderName = "fake"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None  # e.g. https://<resource>.openai.azure.com/openai/v1/
    llm_api_key: SecretStr | None = None  # SecretStr: never printed in logs or reprs
    llm_timeout_seconds: float = 30.0

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def empty_base_url(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def real_provider_needs_a_key(self) -> Self:
        if self.llm_provider != "fake" and (
            self.llm_api_key is None or not self.llm_api_key.get_secret_value()
        ):
            raise ValueError(f"LLM_API_KEY is required when LLM_PROVIDER={self.llm_provider}")
        return self


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor. lru_cache makes it behave like services.AddSingleton<Settings>()."""
    return Settings()
