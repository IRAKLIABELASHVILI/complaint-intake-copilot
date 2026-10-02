"""The worker survives the broker going away (found in an end-to-end outage test)."""

import socket

import pika.exceptions
import pytest

from app.messaging.messages import AnalysisJob
from app.worker.__main__ import RECONNECT_DELAY_SECONDS, consume_forever
from app.worker.consumer import JobConsumer
from app.worker.jobs import JobOutcome


class NeverCalledHandler:
    def handle(self, job: AnalysisJob) -> JobOutcome:
        raise AssertionError("no message should arrive")

    def on_dead_letter(self, job: AnalysisJob, reason: str) -> None:
        raise AssertionError("no message should arrive")


class StopTest(Exception):
    """Ends the otherwise endless loop once the test has seen enough."""


@pytest.mark.parametrize(
    "error",
    [
        socket.gaierror(-2, "Name or service not known"),  # broker container stopped
        ConnectionRefusedError(),  # broker host up, RabbitMQ not listening
        pika.exceptions.AMQPConnectionError(),  # pika's own connection failure
        pika.exceptions.StreamLostError(),  # connection dropped while consuming
    ],
    ids=["dns", "refused", "amqp", "stream-lost"],
)
def test_worker_waits_and_reconnects_instead_of_crashing(error: Exception) -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    def failing_connect(url: str) -> None:
        attempts.append(url)
        if len(attempts) > 2:
            raise StopTest
        raise error

    with pytest.raises(StopTest):
        consume_forever(
            "amqp://test",
            JobConsumer(NeverCalledHandler()),
            open_connection=failing_connect,
            sleep=sleeps.append,
        )

    assert len(attempts) == 3
    assert sleeps == [RECONNECT_DELAY_SECONDS, RECONNECT_DELAY_SECONDS]
