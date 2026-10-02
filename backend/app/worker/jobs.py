"""The contract between the consumer (transport) and a job handler (business logic).

The consumer only needs to know three things about a handler's result:
- it returned an outcome      -> acknowledge
- it raised PermanentJobError -> dead-letter now (retrying cannot help)
- it raised anything else     -> treat as transient and retry with backoff
"""

from enum import StrEnum
from typing import Protocol

from app.messaging.messages import AnalysisJob


class JobOutcome(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"  # this message id was handled before (redelivery)
    ALREADY_STARTED = "already_started"  # the case has moved past `new`: nothing to do


class PermanentJobError(Exception):
    """The job can never succeed as it is (e.g. its case does not exist for that tenant)."""


class JobHandler(Protocol):
    def handle(self, job: AnalysisJob) -> JobOutcome: ...

    def on_dead_letter(self, job: AnalysisJob, reason: str) -> None:
        """Called once when the job is given up, so the failure is visible, not silent."""
        ...
