"""Builds the configured LLM provider. C# comparison: the DI registration that picks the
implementation of ILlmProvider from configuration."""

from app.ai.fake_provider import FakeLlmProvider
from app.ai.openai_provider import OpenAiCompatibleProvider
from app.ai.provider import LlmProvider
from app.config import Settings


def build_provider(settings: Settings) -> LlmProvider:
    if settings.llm_provider == "fake":
        return FakeLlmProvider()
    assert settings.llm_api_key is not None  # guaranteed by Settings validation
    return OpenAiCompatibleProvider(
        name=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
