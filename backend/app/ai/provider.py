"""The LLM provider abstraction.

`complete` only accepts `RedactedText`, which only `redact()` produces. Sending unredacted text to
a model is therefore a type error caught by mypy, not something a reviewer has to spot.

C# comparison: `interface ILlmProvider` with a fake for tests and one real implementation.
"""

from typing import Protocol

from app.domain.redaction import RedactedText


class ProviderUnavailableError(Exception):
    """Temporary: timeout, rate limit, connection or server error. Retrying later can succeed."""


class ProviderRejectedError(Exception):
    """Permanent: bad credentials, unknown model, request refused. Retrying will not help."""


class LlmProvider(Protocol):
    @property
    def name(self) -> str:
        """Stored with each analysis, e.g. "fake", "openai", "azure_openai" (US-2.7)."""
        ...

    @property
    def model(self) -> str: ...

    def complete(self, complaint: RedactedText, *, previous_error: str | None = None) -> str:
        """Return the model's raw answer. It is untrusted: the caller validates it.

        `previous_error` describes why the last answer was invalid, for the single retry.
        """
        ...
