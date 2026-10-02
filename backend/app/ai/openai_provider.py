"""One provider for any OpenAI-compatible API: OpenAI itself, Azure OpenAI (its v1 endpoint), or a
local server. Only `base_url`, the key and the model name change.

Retries are not done here (`max_retries=0`): the queue already retries with backoff, and two
layers of retries would multiply the wait and the cost.
"""

from typing import cast

import openai
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject

from app.ai.prompt import build_messages
from app.ai.provider import ProviderRejectedError, ProviderUnavailableError
from app.domain.redaction import RedactedText

_TEMPORARY_ERRORS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class OpenAiCompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        api_key: str,
        base_url: str | None,
        timeout_seconds: float,
        client: OpenAI | None = None,  # tests pass a client with a fake HTTP transport
    ) -> None:
        self._name = name
        self._model = model
        self._client = client or OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=0
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    def complete(self, complaint: RedactedText, *, previous_error: str | None = None) -> str:
        messages = cast(list[ChatCompletionMessageParam], build_messages(complaint, previous_error))
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                response_format=ResponseFormatJSONObject(type="json_object"),
            )
        except _TEMPORARY_ERRORS as error:
            raise ProviderUnavailableError(type(error).__name__) from None
        except openai.APIError as error:
            # Only the type: error bodies can echo the request back.
            raise ProviderRejectedError(type(error).__name__) from None
        return response.choices[0].message.content or ""
