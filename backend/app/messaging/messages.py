"""The message contract between the API and the worker.

A message carries ids only, never complaint text: the worker loads the case from the database.
Messages are validated on the way in like any other untrusted input.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.logging_config import CORRELATION_ID_PATTERN

ANALYSIS_QUEUE = "case.analysis"
ANALYSIS_RETRY_QUEUE = "case.analysis.retry"  # waits out the backoff, then back to the main queue
ANALYSIS_DEAD_LETTER_QUEUE = "case.analysis.dead"  # gave up: needs a person to look

MAX_MESSAGE_BYTES = 4096  # a job is ~200 bytes; anything far bigger is not one of ours


class InvalidMessageError(Exception):
    """The message body is not a valid job. Retrying cannot fix it."""


class AnalysisJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: uuid.UUID
    case_id: uuid.UUID
    tenant_id: uuid.UUID
    correlation_id: str = Field(pattern=CORRELATION_ID_PATTERN.pattern)

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


def parse_analysis_job(body: bytes) -> AnalysisJob:
    if len(body) > MAX_MESSAGE_BYTES:
        raise InvalidMessageError(f"Message is larger than {MAX_MESSAGE_BYTES} bytes")
    try:
        return AnalysisJob.model_validate_json(body)
    except ValidationError as error:
        # Only the count: validation errors can echo the input back, and logs stay ids-only.
        raise InvalidMessageError(f"Invalid analysis job ({error.error_count()} errors)") from None
