"""Run the whole backend on one machine without Docker: `python -m app.devtools.local_stack`.

For front-end work, or a computer where Docker cannot run. Everything is the real code except
the infrastructure:

- SQLite (one file) instead of PostgreSQL. Tables come from the models, not from Alembic.
- No RabbitMQ: a background thread takes jobs from the outbox and hands them straight to the
  same worker code (redaction, LLM provider, validation) that consumes the queue in Docker.

Docker Compose remains the real way to run the system; this trades fidelity for convenience.
"""

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import uvicorn
from sqlalchemy.orm import Session, sessionmaker

from app.ai.factory import build_provider
from app.api.deps import get_session
from app.config import get_settings
from app.db.base import Base
from app.db.session import build_engine
from app.logging_config import configure_logging
from app.main import app
from app.messaging.messages import parse_analysis_job
from app.messaging.outbox import OutboxRelay
from app.seed import seed
from app.worker.analysis_job_handler import AnalysisJobHandler
from app.worker.case_analyser import CaseAnalyser

logger = logging.getLogger(__name__)

DATABASE_FILE = Path(os.environ.get("LOCAL_DB_FILE", "local-demo.db"))
POLL_SECONDS = 1.0


class InlineBus:
    """A MessageBus that does not send anything over a network: it runs the job at once."""

    def __init__(self, handler: AnalysisJobHandler) -> None:
        self.handler = handler

    def publish(self, queue: str, message_id: uuid.UUID, body: bytes) -> None:
        self.handler.handle(parse_analysis_job(body))


def run_outbox_forever(relay: OutboxRelay) -> None:
    while True:
        try:
            if relay.publish_pending() == 0:
                time.sleep(POLL_SECONDS)
        except Exception:
            logger.exception("Local outbox loop failed; retrying")
            time.sleep(POLL_SECONDS)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = build_engine(f"sqlite:///{DATABASE_FILE}")
    Base.metadata.create_all(engine)
    sessions: Callable[[], Session] = sessionmaker(bind=engine, expire_on_commit=False)

    with sessions() as session:
        seed(session)  # skips tenants that already exist

    handler = AnalysisJobHandler(sessions, CaseAnalyser(build_provider(settings)))
    relay = OutboxRelay(sessions, InlineBus(handler))
    threading.Thread(target=run_outbox_forever, args=(relay,), daemon=True).start()

    def local_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = local_session
    logger.info("Local stack ready on http://127.0.0.1:8000 (database: %s)", DATABASE_FILE)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)


if __name__ == "__main__":
    main()
