"""Turns a delivered message into a handler call, and its result into ack / retry / dead-letter.

Retries go through a separate retry queue: the message waits there for its backoff delay
(a per-message TTL), then RabbitMQ dead-letters it back into the main queue. The attempt number
travels in a header. Rejected messages (nack without requeue) go to the dead-letter queue.

The channel is only used through four methods, so tests drive this class with a fake channel.
"""

import logging
from typing import Any

import pika

from app.logging_config import correlation_id_var
from app.messaging.messages import (
    ANALYSIS_RETRY_QUEUE,
    AnalysisJob,
    InvalidMessageError,
    parse_analysis_job,
)
from app.messaging.retry_policy import retry_delay
from app.worker.jobs import JobHandler, PermanentJobError

logger = logging.getLogger(__name__)

ATTEMPT_HEADER = "x-attempt"


class JobConsumer:
    def __init__(self, handler: JobHandler) -> None:
        self.handler = handler

    def on_message(self, channel: Any, method: Any, properties: Any, body: bytes) -> None:
        """pika's consumer callback signature: (channel, method, properties, body)."""
        delivery_tag = method.delivery_tag
        attempt = _attempt_of(properties)

        try:
            job = parse_analysis_job(body)
        except InvalidMessageError as error:
            logger.error("Rejected invalid message", extra={"error_type": str(error)})
            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
            return

        token = correlation_id_var.set(job.correlation_id)
        context = {"message_id": job.message_id, "case_id": job.case_id, "attempt": attempt}
        try:
            outcome = self.handler.handle(job)
        except PermanentJobError as error:
            logger.error(
                "Job failed permanently; dead-lettered",
                extra=context | {"error_type": type(error).__name__},
            )
            self._dead_letter(
                channel, delivery_tag, job, f"Failed permanently: {type(error).__name__}"
            )
        except Exception as error:  # transient: database down, timeouts...
            self._retry_or_dead_letter(channel, delivery_tag, job, attempt, context, error)
        else:
            logger.info("Job handled", extra=context | {"outcome": outcome})
            channel.basic_ack(delivery_tag=delivery_tag)
        finally:
            correlation_id_var.reset(token)

    def _retry_or_dead_letter(
        self,
        channel: Any,
        delivery_tag: int,
        job: AnalysisJob,
        attempt: int,
        context: dict[str, object],
        error: Exception,
    ) -> None:
        context = context | {"error_type": type(error).__name__}
        delay = retry_delay(attempt)
        if delay is None:
            logger.error("Job failed after all attempts; dead-lettered", extra=context)
            reason = f"Gave up after {attempt} attempts: {type(error).__name__}"
            self._dead_letter(channel, delivery_tag, job, reason)
            return

        logger.warning("Job failed; retrying later", extra=context, exc_info=True)
        channel.basic_publish(
            exchange="",
            routing_key=ANALYSIS_RETRY_QUEUE,
            body=job.to_bytes(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
                expiration=str(int(delay.total_seconds() * 1000)),
                headers={ATTEMPT_HEADER: attempt + 1},
            ),
        )
        # Ack only after the retry copy is safely queued. A crash in between means one extra
        # delivery, which the idempotent handler absorbs.
        channel.basic_ack(delivery_tag=delivery_tag)

    def _dead_letter(self, channel: Any, delivery_tag: int, job: AnalysisJob, reason: str) -> None:
        try:
            self.handler.on_dead_letter(job, reason)
        except Exception as error:  # e.g. the database is the thing that is down
            logger.error(
                "Could not record the dead-lettered job on its case",
                extra={"message_id": job.message_id, "error_type": type(error).__name__},
            )
        channel.basic_nack(delivery_tag=delivery_tag, requeue=False)


def _attempt_of(properties: Any) -> int:
    headers = getattr(properties, "headers", None) or {}
    attempt = headers.get(ATTEMPT_HEADER, 1)
    return attempt if isinstance(attempt, int) and attempt >= 1 else 1
