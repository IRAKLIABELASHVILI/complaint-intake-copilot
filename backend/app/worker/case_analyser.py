"""Redact -> ask the model -> validate, retrying once on an invalid answer (US-2.5, US-6).

No database here: this is pure orchestration, so every path is easy to test with a fake provider.
Provider errors are not caught: a temporary one is retried later by the queue, a permanent one
dead-letters the job.
"""

import logging
from dataclasses import dataclass

from app.ai.output import InvalidModelOutputError, ValidatedAnalysis, validate_model_output
from app.ai.prompt import MAX_MODEL_INPUT_CHARS
from app.ai.provider import LlmProvider
from app.domain.redaction import RedactionError, redact

logger = logging.getLogger(__name__)

MAX_MODEL_ATTEMPTS = 2  # the first answer, plus one retry if it is invalid

REDACTION_FAILED = "Redaction failed, so nothing was sent to the model"
INVALID_TWICE = "The model's answer failed validation twice"


@dataclass(frozen=True)
class ModelAttempt:
    number: int
    raw_output: str
    result: ValidatedAnalysis | None  # None when the answer was invalid
    error: str | None


@dataclass(frozen=True)
class AnalysisOutcome:
    provider: str
    model: str
    redacted_input: str | None  # None when redaction failed: nothing left our system
    attempts: tuple[ModelAttempt, ...]
    failure_reason: str | None  # None on success

    @property
    def result(self) -> ValidatedAnalysis | None:
        return self.attempts[-1].result if self.attempts else None


class CaseAnalyser:
    def __init__(self, provider: LlmProvider) -> None:
        self.provider = provider

    def analyse(self, *, subject: str, body: str, sender_name: str | None) -> AnalysisOutcome:
        try:
            redacted = redact(f"Subject: {subject}\n\n{body}", sender_name=sender_name)
        except RedactionError as error:
            # Fail closed (US-6.5): no model call at all.
            logger.error("Redaction failed; model not called", extra={"error_type": str(error)})
            return self._outcome(None, (), REDACTION_FAILED)

        sent = redacted.truncated(MAX_MODEL_INPUT_CHARS)
        logger.info("Text redacted", extra={"redactions": dict(redacted.counts)})

        attempts: list[ModelAttempt] = []
        previous_error: str | None = None
        for number in range(1, MAX_MODEL_ATTEMPTS + 1):
            raw = self.provider.complete(sent, previous_error=previous_error)
            try:
                result = validate_model_output(raw, sent.value)
            except InvalidModelOutputError as error:
                previous_error = str(error)
                attempts.append(ModelAttempt(number, raw, None, previous_error))
                logger.warning("Model answer invalid", extra={"attempt": number})
                continue
            attempts.append(ModelAttempt(number, raw, result, None))
            return self._outcome(sent.value, tuple(attempts), None)

        return self._outcome(sent.value, tuple(attempts), INVALID_TWICE)

    def _outcome(
        self, redacted_input: str | None, attempts: tuple[ModelAttempt, ...], failure: str | None
    ) -> AnalysisOutcome:
        return AnalysisOutcome(
            self.provider.name, self.provider.model, redacted_input, attempts, failure
        )
