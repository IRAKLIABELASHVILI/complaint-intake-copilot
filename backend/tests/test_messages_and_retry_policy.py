"""The job message contract and the retry schedule."""

import json
import uuid
from datetime import timedelta

import pytest

from app.messaging.messages import AnalysisJob, InvalidMessageError, parse_analysis_job
from app.messaging.retry_policy import MAX_ATTEMPTS, MAX_DELAY, retry_delay

VALID = {
    "message_id": str(uuid.uuid4()),
    "case_id": str(uuid.uuid4()),
    "tenant_id": str(uuid.uuid4()),
    "correlation_id": "abc-123",
}


def test_a_job_round_trips_through_bytes() -> None:
    job = AnalysisJob.model_validate(VALID)

    assert parse_analysis_job(job.to_bytes()) == job


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        json.dumps(VALID | {"extra": 1}).encode(),
        json.dumps(VALID | {"correlation_id": "has spaces; and symbols"}).encode(),
        json.dumps({k: v for k, v in VALID.items() if k != "tenant_id"}).encode(),
    ],
    ids=["not-json", "unknown-field", "unsafe-correlation-id", "missing-tenant"],
)
def test_invalid_messages_are_rejected(body: bytes) -> None:
    with pytest.raises(InvalidMessageError):
        parse_analysis_job(body)


def test_the_error_never_echoes_the_message_content() -> None:
    with pytest.raises(InvalidMessageError) as caught:
        parse_analysis_job(b'{"case_id": "secret complaint text"}')

    assert "secret" not in str(caught.value)


def test_retry_delays_double_each_time() -> None:
    delays = [retry_delay(attempt) for attempt in range(1, MAX_ATTEMPTS)]

    assert delays == [timedelta(seconds=s) for s in (2, 4, 8, 16)]


def test_no_retry_after_the_last_attempt() -> None:
    assert retry_delay(MAX_ATTEMPTS) is None


def test_delays_never_exceed_the_cap() -> None:
    assert all((retry_delay(n) or timedelta()) <= MAX_DELAY for n in range(1, MAX_ATTEMPTS))
