"""Test doubles. C# comparison: hand-written fakes instead of a mocking library."""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.redaction import RedactedText


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


def model_answer(**overrides: object) -> str:
    """A valid model answer as JSON, with optional changes."""
    answer: dict[str, object] = {
        "category": "fees_and_charges",
        "summary": "Customer disputes a fee.",
        "priority": "medium",
        "vulnerability_indicators": [],
    }
    return json.dumps(answer | overrides)


@dataclass
class ScriptedProvider:
    """An LlmProvider that plays back a script: each call returns the next answer, or raises it
    if it is an exception. Records exactly what it was sent."""

    script: list[str | Exception]
    name: str = "scripted"
    model: str = "scripted-v1"
    calls: list[tuple[str, str | None]] = field(default_factory=list)  # (text, previous_error)

    def complete(self, complaint: RedactedText, *, previous_error: str | None = None) -> str:
        self.calls.append((complaint.value, previous_error))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step
