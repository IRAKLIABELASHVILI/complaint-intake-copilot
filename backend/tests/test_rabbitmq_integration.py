"""Against a real RabbitMQ: topology, publishing, retry and dead-lettering.

Skipped unless TEST_RABBITMQ_URL is set (CI sets it). Locally:
    docker compose up -d rabbitmq
    TEST_RABBITMQ_URL=amqp://cic:cic@127.0.0.1:5672/%2F pytest tests/test_rabbitmq_integration.py
"""

import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from app.messaging.messages import (
    ANALYSIS_DEAD_LETTER_QUEUE,
    ANALYSIS_QUEUE,
    ANALYSIS_RETRY_QUEUE,
    AnalysisJob,
)
from app.messaging.rabbitmq import RabbitMqMessageBus, connect, declare_topology
from app.worker.consumer import JobConsumer
from app.worker.jobs import JobOutcome, PermanentJobError

RABBITMQ_URL = os.environ.get("TEST_RABBITMQ_URL")
pytestmark = pytest.mark.skipif(RABBITMQ_URL is None, reason="TEST_RABBITMQ_URL not set")

QUEUES = (ANALYSIS_QUEUE, ANALYSIS_RETRY_QUEUE, ANALYSIS_DEAD_LETTER_QUEUE)


class RaisingHandler:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def handle(self, job: AnalysisJob) -> JobOutcome:
        raise self.error


@pytest.fixture
def channel() -> Iterator[Any]:
    assert RABBITMQ_URL is not None
    connection = connect(RABBITMQ_URL)
    channel = connection.channel()
    channel.confirm_delivery()
    declare_topology(channel)
    for queue in QUEUES:
        channel.queue_purge(queue)
    yield channel
    connection.close()


@pytest.fixture
def job() -> AnalysisJob:
    return AnalysisJob(
        message_id=uuid.uuid4(), case_id=uuid.uuid4(), tenant_id=uuid.uuid4(), correlation_id="it"
    )


def publish(job: AnalysisJob) -> None:
    assert RABBITMQ_URL is not None
    bus = RabbitMqMessageBus(RABBITMQ_URL)
    try:
        bus.publish(ANALYSIS_QUEUE, job.message_id, job.to_bytes())
    finally:
        bus.close()


def get_one(channel: Any, queue: str, timeout_seconds: float = 0) -> tuple[Any, Any, bytes]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        method, properties, body = channel.basic_get(queue=queue, auto_ack=False)
        if method is not None:
            return method, properties, body
        if time.monotonic() >= deadline:
            pytest.fail(f"No message arrived on {queue}")
        time.sleep(0.2)


def test_published_job_arrives_durable_with_its_message_id(channel: Any, job: AnalysisJob) -> None:
    publish(job)

    method, properties, body = get_one(channel, ANALYSIS_QUEUE, timeout_seconds=5)

    assert body == job.to_bytes()
    assert properties.message_id == str(job.message_id)
    assert properties.delivery_mode == 2  # persistent: survives a broker restart
    channel.basic_ack(method.delivery_tag)


def test_permanent_failure_ends_in_the_dead_letter_queue(channel: Any, job: AnalysisJob) -> None:
    publish(job)
    consumer = JobConsumer(RaisingHandler(PermanentJobError("no such case")))

    consumer.on_message(channel, *get_one(channel, ANALYSIS_QUEUE, timeout_seconds=5))

    method, _, body = get_one(channel, ANALYSIS_DEAD_LETTER_QUEUE, timeout_seconds=5)
    assert body == job.to_bytes()
    channel.basic_ack(method.delivery_tag)


def test_transient_failure_comes_back_after_the_backoff(channel: Any, job: AnalysisJob) -> None:
    publish(job)
    consumer = JobConsumer(RaisingHandler(ConnectionError("db down")))

    consumer.on_message(channel, *get_one(channel, ANALYSIS_QUEUE, timeout_seconds=5))

    # It waits 2 s in the retry queue, then RabbitMQ moves it back to the main queue.
    method, properties, body = get_one(channel, ANALYSIS_QUEUE, timeout_seconds=10)
    assert body == job.to_bytes()
    assert properties.headers["x-attempt"] == 2
    channel.basic_ack(method.delivery_tag)
