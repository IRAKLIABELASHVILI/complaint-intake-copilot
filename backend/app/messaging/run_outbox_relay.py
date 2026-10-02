"""Outbox relay entry point: `python -m app.messaging.run_outbox_relay`.

Polls the outbox and publishes pending messages. When there is nothing to do, or the database
or broker is down, it waits and tries again: nothing is lost, the rows stay pending.
"""

import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.session import new_session
from app.logging_config import configure_logging
from app.messaging.outbox import OutboxRelay
from app.messaging.rabbitmq import RabbitMqMessageBus

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    bus = RabbitMqMessageBus(settings.rabbitmq_url)
    relay = OutboxRelay(new_session, bus)
    logger.info("Outbox relay started")
    try:
        while True:
            try:
                published = relay.publish_pending()
            except SQLAlchemyError as error:
                logger.warning("Database unavailable", extra={"error_type": type(error).__name__})
                published = 0
            if published == 0:
                time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Outbox relay stopped")
    finally:
        bus.close()


if __name__ == "__main__":
    main()
