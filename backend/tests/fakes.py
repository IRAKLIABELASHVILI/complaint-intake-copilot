"""Test doubles for messaging. C# comparison: hand-written fakes instead of a mocking library."""

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PublishedMessage:
    queue: str
    message_id: uuid.UUID
    body: bytes


@dataclass
class RecordingMessageBus:
    """A MessageBus that keeps what was published. Can be told to fail."""

    published: list[PublishedMessage] = field(default_factory=list)
    fail_with: Exception | None = None

    def publish(self, queue: str, message_id: uuid.UUID, body: bytes) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.published.append(PublishedMessage(queue, message_id, body))


@dataclass
class FakeMethod:
    delivery_tag: int = 1


@dataclass
class FakeProperties:
    headers: dict[str, Any] | None = None


@dataclass
class FakeChannel:
    """Records what a consumer did with a delivery: ack, nack or re-publish."""

    acked: list[int] = field(default_factory=list)
    nacked: list[tuple[int, bool]] = field(default_factory=list)  # (delivery_tag, requeue)
    published: list[dict[str, Any]] = field(default_factory=list)

    def basic_ack(self, delivery_tag: int) -> None:
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag: int, requeue: bool) -> None:
        self.nacked.append((delivery_tag, requeue))

    def basic_publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)
