"""RabbitMQ adapter: queue topology and a MessageBus implementation (pika, blocking).

Topology (all durable, all on the default exchange):

    case.analysis --(nack)--> case.analysis.dead
    case.analysis.retry --(per-message TTL expires)--> case.analysis

Both the relay and the worker declare it on connect. Declaring is idempotent, so start-up order
does not matter.
"""

import uuid
from typing import Any

import pika

from app.messaging.messages import (
    ANALYSIS_DEAD_LETTER_QUEUE,
    ANALYSIS_QUEUE,
    ANALYSIS_RETRY_QUEUE,
)

HEARTBEAT_SECONDS = 30


def connect(url: str) -> Any:
    """A blocking connection. The URL holds credentials: never log it."""
    parameters = pika.URLParameters(url)
    parameters.heartbeat = HEARTBEAT_SECONDS
    parameters.blocked_connection_timeout = 60
    return pika.BlockingConnection(parameters)


def declare_topology(channel: Any) -> None:
    channel.queue_declare(queue=ANALYSIS_DEAD_LETTER_QUEUE, durable=True)
    channel.queue_declare(
        queue=ANALYSIS_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": ANALYSIS_DEAD_LETTER_QUEUE,
        },
    )
    channel.queue_declare(
        queue=ANALYSIS_RETRY_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": ANALYSIS_QUEUE},
    )


class RabbitMqMessageBus:
    """Publishes with publisher confirms: `publish` returns only once the broker has the message.

    The connection is opened lazily and dropped on any error, so the next call reconnects.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: Any = None
        self._channel: Any = None

    def publish(self, queue: str, message_id: uuid.UUID, body: bytes) -> None:
        try:
            self._open_channel().basic_publish(
                exchange="",
                routing_key=queue,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent,
                    message_id=str(message_id),
                ),
                mandatory=True,  # raise if no queue would receive it
            )
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._connection is not None and self._connection.is_open:
            self._connection.close()
        self._connection = None
        self._channel = None

    def _open_channel(self) -> Any:
        if self._channel is None or not self._channel.is_open:
            self.close()
            self._connection = connect(self._url)
            self._channel = self._connection.channel()
            self._channel.confirm_delivery()
            declare_topology(self._channel)
        return self._channel
