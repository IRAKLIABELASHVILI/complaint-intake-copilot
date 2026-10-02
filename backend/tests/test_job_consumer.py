"""What the consumer does with each kind of result: ack, retry later, or dead-letter."""

import uuid
from dataclasses import dataclass, field

from app.logging_config import correlation_id_var
from app.messaging.messages import ANALYSIS_RETRY_QUEUE, MAX_MESSAGE_BYTES, AnalysisJob
from app.messaging.retry_policy import MAX_ATTEMPTS
from app.worker.consumer import ATTEMPT_HEADER, JobConsumer
from app.worker.jobs import JobOutcome, PermanentJobError
from tests.fakes import FakeChannel, FakeMethod, FakeProperties

JOB = AnalysisJob(
    message_id=uuid.uuid4(), case_id=uuid.uuid4(), tenant_id=uuid.uuid4(), correlation_id="c-1"
)


@dataclass
class StubHandler:
    """Returns an outcome or raises, and remembers the correlation id it ran under."""

    raises: Exception | None = None
    seen_correlation_ids: list[str | None] = field(default_factory=list)

    def handle(self, job: AnalysisJob) -> JobOutcome:
        self.seen_correlation_ids.append(correlation_id_var.get())
        if self.raises is not None:
            raise self.raises
        return JobOutcome.PROCESSED


def deliver(
    handler: StubHandler, body: bytes = JOB.to_bytes(), attempt: int | None = None
) -> FakeChannel:
    channel = FakeChannel()
    headers = {ATTEMPT_HEADER: attempt} if attempt is not None else None
    JobConsumer(handler).on_message(channel, FakeMethod(7), FakeProperties(headers), body)
    return channel


def test_a_handled_job_is_acknowledged() -> None:
    channel = deliver(StubHandler())

    assert channel.acked == [7]
    assert channel.nacked == []


def test_the_handler_runs_under_the_jobs_correlation_id() -> None:
    handler = StubHandler()

    deliver(handler)

    assert handler.seen_correlation_ids == ["c-1"]
    assert correlation_id_var.get() is None  # reset afterwards


def test_an_invalid_message_is_dead_lettered_without_calling_the_handler() -> None:
    handler = StubHandler()

    channel = deliver(handler, body=b'{"not": "a job"}')

    assert channel.nacked == [(7, False)]
    assert handler.seen_correlation_ids == []


def test_an_oversized_message_is_dead_lettered() -> None:
    channel = deliver(StubHandler(), body=b"x" * (MAX_MESSAGE_BYTES + 1))

    assert channel.nacked == [(7, False)]


def test_a_permanent_failure_is_dead_lettered_at_once() -> None:
    channel = deliver(StubHandler(raises=PermanentJobError("no such case")))

    assert channel.nacked == [(7, False)]
    assert channel.published == []


def test_a_transient_failure_is_retried_later_with_the_next_attempt_number() -> None:
    channel = deliver(StubHandler(raises=ConnectionError("db down")), attempt=2)

    [retry] = channel.published
    assert retry["routing_key"] == ANALYSIS_RETRY_QUEUE
    assert retry["body"] == JOB.to_bytes()
    assert retry["properties"].headers == {ATTEMPT_HEADER: 3}
    assert retry["properties"].expiration == "4000"  # 4 s backoff after attempt 2
    assert channel.acked == [7]  # the original is done with; the retry copy carries on


def test_a_transient_failure_on_the_last_attempt_is_dead_lettered() -> None:
    channel = deliver(StubHandler(raises=ConnectionError("db down")), attempt=MAX_ATTEMPTS)

    assert channel.nacked == [(7, False)]
    assert channel.published == []


def test_a_missing_or_malformed_attempt_header_counts_as_the_first_attempt() -> None:
    channel = deliver(StubHandler(raises=ConnectionError()), attempt=None)
    assert channel.published[0]["properties"].headers == {ATTEMPT_HEADER: 2}

    channel = deliver(StubHandler(raises=ConnectionError()), attempt=-5)
    assert channel.published[0]["properties"].headers == {ATTEMPT_HEADER: 2}
