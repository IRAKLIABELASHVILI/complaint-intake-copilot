"""Handles one analysis job, in three steps:

1. Short transaction: check idempotency, load the case (case id AND tenant id), new -> analysing.
2. No transaction: redact, call the model, validate. This can take seconds; holding database
   locks that long would block other work.
3. Short transaction: save every attempt, the indicators, the new status, the audit event and
   the "processed" marker together. All or nothing.

If step 2 fails temporarily (model down), the queue retries; the case is still `analysing`, so
the retry resumes at step 2. If the job is dead-lettered, `on_dead_letter` makes the failure
visible: the case goes to `needs_human_review`.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.output import ValidatedAnalysis
from app.ai.provider import ProviderRejectedError
from app.db.models import Case, CaseAnalysis, ProcessedMessage, VulnerabilityIndicator
from app.db.repositories import (
    AnalysisRepository,
    AuditRepository,
    CaseRepository,
    IndicatorRepository,
)
from app.domain.enums import (
    AnalysisStatus,
    AuditSource,
    CaseStatus,
    IndicatorDecision,
    IndicatorSource,
)
from app.messaging.messages import AnalysisJob
from app.services.status_changes import change_status
from app.worker.case_analyser import AnalysisOutcome, CaseAnalyser
from app.worker.jobs import JobOutcome, PermanentJobError

logger = logging.getLogger(__name__)

_IN_PROGRESS_STATUSES = (CaseStatus.NEW, CaseStatus.ANALYSING)


class CaseNotFoundForJobError(PermanentJobError):
    """No case with this id exists in the job's tenant."""


class ProviderRejectedJobError(PermanentJobError):
    """The model provider refused the request (e.g. bad key). Retrying will not help."""


@dataclass(frozen=True)
class _CaseInput:
    subject: str
    body: str
    sender_name: str | None


class AnalysisJobHandler:
    def __init__(self, session_factory: Callable[[], Session], analyser: CaseAnalyser) -> None:
        self.session_factory = session_factory
        self.analyser = analyser

    def handle(self, job: AnalysisJob) -> JobOutcome:
        case_input = self._start(job)
        if isinstance(case_input, JobOutcome):
            return case_input

        try:
            outcome = self.analyser.analyse(
                subject=case_input.subject,
                body=case_input.body,
                sender_name=case_input.sender_name,
            )
        except ProviderRejectedError as error:
            raise ProviderRejectedJobError(str(error)) from None

        return self._finish(job, outcome)

    def on_dead_letter(self, job: AnalysisJob, reason: str) -> None:
        """The job is given up: make that visible on the case instead of leaving it stuck."""
        with self.session_factory() as session:
            case = CaseRepository(session, job.tenant_id).get(job.case_id)
            if case is None or case.status is not CaseStatus.ANALYSING:
                return
            AnalysisRepository(session, job.tenant_id).add(
                CaseAnalysis(
                    case=case,
                    attempt=0,
                    status=AnalysisStatus.FAILED,
                    provider=self.analyser.provider.name,
                    model=self.analyser.provider.model,
                    error=reason,
                    correlation_id=job.correlation_id,
                )
            )
            self._change_status(session, case, CaseStatus.NEEDS_HUMAN_REVIEW, job, reason=reason)
            session.commit()

    # --- step 1 ---------------------------------------------------------------------------------

    def _start(self, job: AnalysisJob) -> _CaseInput | JobOutcome:
        with self.session_factory() as session:
            if session.get(ProcessedMessage, job.message_id) is not None:
                return JobOutcome.DUPLICATE

            # Both ids from the message (US-7.6): a case is only found inside its own tenant.
            case = CaseRepository(session, job.tenant_id).get(job.case_id)
            if case is None:
                raise CaseNotFoundForJobError(f"Case {job.case_id} not found for its tenant")

            if case.status not in _IN_PROGRESS_STATUSES:
                return self._mark_processed(session, job, case.id, JobOutcome.ALREADY_STARTED)

            if case.status is CaseStatus.NEW:
                self._change_status(session, case, CaseStatus.ANALYSING, job)
                session.commit()
            return _CaseInput(case.subject, case.body, case.sender_name)

    # --- step 3 ---------------------------------------------------------------------------------

    def _finish(self, job: AnalysisJob, outcome: AnalysisOutcome) -> JobOutcome:
        with self.session_factory() as session:
            case = CaseRepository(session, job.tenant_id).get(job.case_id)
            if case is None:
                raise CaseNotFoundForJobError(f"Case {job.case_id} not found for its tenant")
            if case.status is not CaseStatus.ANALYSING:  # finished by a concurrent delivery
                return self._mark_processed(session, job, case.id, JobOutcome.ALREADY_STARTED)

            analysis = self._save_attempts(session, job, case, outcome)
            if outcome.result is not None and analysis is not None:
                self._save_indicators(session, job, case, analysis, outcome.result)
                self._change_status(session, case, CaseStatus.AWAITING_REVIEW, job)
            else:
                reason = outcome.failure_reason or "Analysis failed"
                self._change_status(
                    session, case, CaseStatus.NEEDS_HUMAN_REVIEW, job, reason=reason
                )
            return self._mark_processed(session, job, case.id, JobOutcome.PROCESSED)

    def _save_attempts(
        self, session: Session, job: AnalysisJob, case: Case, outcome: AnalysisOutcome
    ) -> CaseAnalysis | None:
        """One row per model attempt (or one FAILED row if redaction stopped us). Returns the
        successful one, if any."""
        analyses = AnalysisRepository(session, job.tenant_id)
        if not outcome.attempts:
            analyses.add(self._analysis_row(job, case, outcome, attempt=0))
            return None

        successful = None
        for attempt in outcome.attempts:
            row = analyses.add(self._analysis_row(job, case, outcome, attempt=attempt.number))
            row.raw_output = attempt.raw_output
            if attempt.result is None:
                row.status = AnalysisStatus.INVALID_OUTPUT
                row.error = attempt.error
            else:
                row.status = AnalysisStatus.COMPLETED
                row.suggested_category = attempt.result.category
                row.summary = attempt.result.summary
                row.suggested_priority = attempt.result.priority
                successful = row
        return successful

    def _analysis_row(
        self, job: AnalysisJob, case: Case, outcome: AnalysisOutcome, *, attempt: int
    ) -> CaseAnalysis:
        return CaseAnalysis(
            id=uuid.uuid4(),
            case=case,
            attempt=attempt,
            status=AnalysisStatus.FAILED,
            provider=outcome.provider,
            model=outcome.model,
            redacted_input=outcome.redacted_input,
            error=outcome.failure_reason,
            correlation_id=job.correlation_id,
        )

    def _save_indicators(
        self,
        session: Session,
        job: AnalysisJob,
        case: Case,
        analysis: CaseAnalysis,
        result: ValidatedAnalysis,
    ) -> None:
        """Every indicator here already passed the evidence check against the text sent."""
        indicators = IndicatorRepository(session, job.tenant_id)
        for suggested in result.indicators:
            indicators.add(
                VulnerabilityIndicator(
                    case=case,
                    analysis_id=analysis.id,
                    indicator_type=suggested.type,
                    driver=suggested.driver,
                    evidence_quote=suggested.evidence_quote,
                    source=IndicatorSource.AI,
                    decision=IndicatorDecision.PENDING,
                )
            )

    # --- shared ---------------------------------------------------------------------------------

    def _change_status(
        self,
        session: Session,
        case: Case,
        new_status: CaseStatus,
        job: AnalysisJob,
        reason: str | None = None,
    ) -> None:
        actions = {
            CaseStatus.ANALYSING: "analysis_started",
            CaseStatus.AWAITING_REVIEW: "analysis_completed",
            CaseStatus.NEEDS_HUMAN_REVIEW: "analysis_failed",
        }
        change_status(
            case,
            new_status,
            audit=AuditRepository(session, job.tenant_id),
            action=actions[new_status],
            source=AuditSource.SYSTEM,
            actor_user_id=None,
            correlation_id=job.correlation_id,
            reason=reason,
        )

    def _mark_processed(
        self, session: Session, job: AnalysisJob, case_id: uuid.UUID, outcome: JobOutcome
    ) -> JobOutcome:
        session.add(ProcessedMessage(message_id=job.message_id, case_id=case_id))
        try:
            session.commit()  # the marker commits together with any work in this transaction
        except IntegrityError:
            session.rollback()  # another delivery of the same message got there first
            return JobOutcome.DUPLICATE
        return outcome
