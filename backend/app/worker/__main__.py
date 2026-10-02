"""Worker entry point: `python -m app.worker`.

C# comparison: a Worker Service (`BackgroundService`) consuming a RabbitMQ queue.

Stopping at any moment is safe: a message is acknowledged only after it is handled, so an
interrupted one is redelivered, and the handler is idempotent.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

import pika.exceptions

from app.ai.factory import build_provider
from app.config import get_settings
from app.db.session import new_session
from app.logging_config import configure_logging
from app.messaging.messages import ANALYSIS_QUEUE
from app.messaging.rabbitmq import connect, declare_topology
from app.worker.analysis_job_handler import AnalysisJobHandler
from app.worker.case_analyser import CaseAnalyser
from app.worker.consumer import JobConsumer

logger = logging.getLogger(__name__)

RECONNECT_DELAY_SECONDS = 5

# Broker down, connection dropped, or its host name not resolving (socket.gaierror is an OSError,
# and pika raises it as-is). All mean the same thing here: wait, then reconnect.
RECOVERABLE_ERRORS = (pika.exceptions.AMQPError, OSError)


def consume_forever(
    rabbitmq_url: str,
    consumer: JobConsumer,
    *,
    open_connection: Callable[[str], Any] = connect,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    while True:
        try:
            connection = open_connection(rabbitmq_url)
            channel = connection.channel()
            channel.confirm_delivery()  # retry copies are confirmed before the original is acked
            declare_topology(channel)
            channel.basic_qos(prefetch_count=1)  # one job at a time per worker
            channel.basic_consume(queue=ANALYSIS_QUEUE, on_message_callback=consumer.on_message)
            logger.info("Worker consuming")
            channel.start_consuming()
        except RECOVERABLE_ERRORS as error:
            logger.warning(
                "RabbitMQ unavailable; reconnecting", extra={"error_type": type(error).__name__}
            )
            sleep(RECONNECT_DELAY_SECONDS)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    analyser = CaseAnalyser(build_provider(settings))
    consumer = JobConsumer(AnalysisJobHandler(new_session, analyser))
    logger.info("Worker starting with LLM provider '%s'", settings.llm_provider)
    try:
        consume_forever(settings.rabbitmq_url, consumer)
    except KeyboardInterrupt:
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
