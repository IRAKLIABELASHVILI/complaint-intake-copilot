"""Transactional outbox (US-1.5, US-1.6).

1. Intake saves the case, its audit event AND an outbox row in one transaction.
2. The relay (a separate process) publishes pending rows and marks them published.

So the API never talks to RabbitMQ: a broker outage cannot lose a job or fail an intake. Delivery
is at-least-once (a crash between publish and commit re-sends), which is why the worker is
idempotent.

C# comparison: the outbox pattern as in MassTransit / NServiceBus, written out by hand.
"""

import logging
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import Case, OutboxMessage
from app.db.repositories import OutboxRepository
from app.logging_config import correlation_id_var
from app.messaging.bus import MessageBus
from app.messaging.messages import ANALYSIS_QUEUE, AnalysisJob

logger = logging.getLogger(__name__)


def analysis_job_message(case: Case, correlation_id: str) -> OutboxMessage:
    job = AnalysisJob(
        message_id=uuid.uuid4(),
        case_id=case.id,
        tenant_id=case.tenant_id,
        correlation_id=correlation_id,
    )
    return OutboxMessage(
        id=job.message_id,
        queue=ANALYSIS_QUEUE,
        payload=job.model_dump(mode="json"),
        attempts=0,
    )


class OutboxRelay:
    def __init__(
        self, session_factory: Callable[[], Session], bus: MessageBus, batch_size: int = 50
    ) -> None:
        self.session_factory = session_factory
        self.bus = bus
        self.batch_size = batch_size

    def publish_pending(self) -> int:
        """Publish waiting messages, oldest first. Returns how many were published.

        Stops at the first failure: order is kept, and a broker outage costs one failed attempt
        per run instead of one per message.
        """
        published = 0
        with self.session_factory() as session:
            for message in OutboxRepository(session).lock_pending(self.batch_size):
                if not self._publish(message):
                    break
                published += 1
            session.commit()
        return published

    def _publish(self, message: OutboxMessage) -> bool:
        job = AnalysisJob.model_validate(message.payload)
        token = correlation_id_var.set(job.correlation_id)
        try:
            self.bus.publish(message.queue, message.id, job.to_bytes())
        except Exception as error:  # broker down, connection lost, message refused...
            message.attempts += 1
            message.last_error = type(error).__name__  # the type only: no hosts or credentials
            logger.warning(
                "Outbox publish failed; will retry",
                extra={
                    "message_id": message.id,
                    "case_id": job.case_id,
                    "attempt": message.attempts,
                },
            )
            return False
        else:
            message.published_at = utc_now()
            logger.info("Outbox message published", extra={"message_id": message.id})
            return True
        finally:
            correlation_id_var.reset(token)
