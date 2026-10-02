"""The LLM providers. The OpenAI-compatible one runs against a fake HTTP server, so the tests see
exactly what would be sent, with no network and no cost."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx2 as httpx  # the HTTP library the OpenAI SDK 3.x is built on
import pytest
from openai import OpenAI
from pydantic import ValidationError

from app.ai.factory import build_provider
from app.ai.fake_provider import FakeLlmProvider
from app.ai.openai_provider import OpenAiCompatibleProvider
from app.ai.output import validate_model_output
from app.ai.prompt import SYSTEM_PROMPT
from app.ai.provider import ProviderRejectedError, ProviderUnavailableError
from app.config import Settings
from app.domain.enums import Category, IndicatorType
from app.domain.redaction import redact

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "complaints.json"


# --- Fake provider -------------------------------------------------------------------------------


def test_fake_provider_answers_pass_validation_for_every_seed_complaint() -> None:
    provider = FakeLlmProvider()
    for complaint in json.loads(SEED_FILE.read_text(encoding="utf-8")):
        text = redact(complaint["body"], sender_name=complaint["sender_name"])

        validate_model_output(provider.complete(text), text.value)  # raises if invalid


def test_fake_provider_finds_bereavement_with_a_real_quote() -> None:
    text = redact("My husband passed away last month. You charged a fee anyway.")

    result = validate_model_output(FakeLlmProvider().complete(text), text.value)

    assert result.category is Category.FEES_AND_CHARGES
    assert [i.type for i in result.indicators] == [IndicatorType.BEREAVEMENT]
    assert result.indicators[0].evidence_quote == "My husband passed away last month."


# --- OpenAI-compatible provider ------------------------------------------------------------------

GOOD_ANSWER = json.dumps(
    {"category": "other", "summary": "s", "priority": "low", "vulnerability_indicators": []}
)


def provider_with(responder: Callable[[httpx.Request], httpx.Response]) -> OpenAiCompatibleProvider:
    client = OpenAI(
        api_key="test-key",
        base_url="https://llm.test/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(responder)),
    )
    return OpenAiCompatibleProvider(
        name="openai",
        model="test-model",
        api_key="unused",
        base_url=None,
        timeout_seconds=5,
        client=client,
    )


def chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
        },
    )


def test_sends_only_the_redacted_text_in_json_mode() -> None:
    sent: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return chat_response(GOOD_ANSWER)

    complaint = redact("Email me at jane@example.com", sender_name="Jane Doe")

    answer = provider_with(responder).complete(complaint)

    [body] = sent
    assert answer == GOOD_ANSWER
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    messages = body["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1]["content"] == "<complaint>\nEmail me at [EMAIL_1]\n</complaint>"
    assert "jane@example.com" not in json.dumps(body)


def test_the_retry_tells_the_model_what_was_wrong() -> None:
    sent: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return chat_response(GOOD_ANSWER)

    provider_with(responder).complete(redact("text"), previous_error="Schema errors: summary")

    messages = sent[0]["messages"]
    assert isinstance(messages, list)
    assert "Schema errors: summary" in messages[-1]["content"]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_temporary_failures_are_reported_as_unavailable(status: int) -> None:
    provider = provider_with(lambda _: httpx.Response(status, json={"error": {"message": "x"}}))

    with pytest.raises(ProviderUnavailableError):
        provider.complete(redact("text"))


def test_a_network_failure_is_reported_as_unavailable() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(ProviderUnavailableError):
        provider_with(responder).complete(redact("text"))


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_failures_are_reported_as_rejected(status: int) -> None:
    provider = provider_with(lambda _: httpx.Response(status, json={"error": {"message": "x"}}))

    with pytest.raises(ProviderRejectedError):
        provider.complete(redact("text"))


# --- Configuration -------------------------------------------------------------------------------


def test_the_default_provider_is_the_fake_one() -> None:
    assert build_provider(Settings(_env_file=None)).name == "fake"


def test_a_real_provider_without_a_key_fails_at_startup() -> None:
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        Settings(_env_file=None, llm_provider="openai")


def test_a_real_provider_is_built_from_settings_and_the_key_stays_secret() -> None:
    settings = Settings(
        _env_file=None, llm_provider="azure_openai", llm_api_key="sk-secret", llm_model="m1"
    )

    provider = build_provider(settings)

    assert (provider.name, provider.model) == ("azure_openai", "m1")
    assert "sk-secret" not in repr(settings)
