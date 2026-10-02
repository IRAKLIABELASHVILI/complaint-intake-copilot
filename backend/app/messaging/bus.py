"""The publishing abstraction. The outbox relay depends on this, not on RabbitMQ.

C# comparison: `interface IMessageBus`. A Protocol is structural: any class with a matching
`publish` method satisfies it, without inheriting from it. Swapping RabbitMQ for Azure Service Bus
means one new class.
"""

import uuid
from typing import Protocol


class MessageBus(Protocol):
    def publish(self, queue: str, message_id: uuid.UUID, body: bytes) -> None:
        """Publish durably, or raise. Returning means the broker has accepted the message."""
        ...
