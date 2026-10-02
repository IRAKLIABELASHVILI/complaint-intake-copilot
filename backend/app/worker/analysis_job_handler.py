"""Handles one analysis job: idempotency, tenant-safe loading, and the status change.

Milestone 4 moves the case from `new` to `analysing`. Milestone 5 adds the actual analysis
(redaction, the LLM call, validation) inside the same flow.
"""

import logging
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, ProcessedMessage
from app.db.repositories import AuditRepository, CaseRepository
from app.domain.case_status import ensure_transition
from app.domain.enums import AuditSource, CaseStatus
from app.messaging.messages import AnalysisJob
from app.worker.jobs import JobOutcome, PermanentJobError

logger = logging.getLogger(__name__)


class CaseNotFoundForJobError(PermanentJobError):
    """No case with this id exists in the job's tenant."""


class AnalysisJobHandler:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def handle(self, job: AnalysisJob) -> JobOutcome:
        with self.session_factory() as session:
            if session.get(ProcessedMessage, job.message_id) is not None:
                return JobOutcome.DUPLICATE

            # Both ids from the message (US-7.6): a case is only found inside its own tenant.
            case = CaseRepository(session, job.tenant_id).get(job.case_id)
            if case is None:
                raise CaseNotFoundForJobError(f"Case {job.case_id} not found for its tenant")

            session.add(ProcessedMessage(message_id=job.message_id, case_id=case.id))
            outcome = JobOutcome.ALREADY_STARTED
            if case.status is CaseStatus.NEW:
                ensure_transition(case.status, CaseStatus.ANALYSING)
                case.status = CaseStatus.ANALYSING
                AuditRepository(session, job.tenant_id).add(
                    AuditEvent(
                        case=case,
                        action="analysis_started",
                        field="status",
                        old_value=CaseStatus.NEW.value,
                        new_value=CaseStatus.ANALYSING.value,
                        source=AuditSource.SYSTEM,
                        correlation_id=job.correlation_id,
                    )
                )
                outcome = JobOutcome.PROCESSED

            try:
                session.commit()  # processed marker + status + audit: all or nothing
            except IntegrityError:
                # Another worker committed the same message id first.
                session.rollback()
                return JobOutcome.DUPLICATE
            return outcome
