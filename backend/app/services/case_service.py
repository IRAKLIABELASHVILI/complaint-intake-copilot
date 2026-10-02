"""Use cases for complaint cases. Endpoints stay thin; the rules live here.

C# comparison: an application service (CaseService : ICaseService) that receives its repositories.
"""

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Case, CaseAnalysis, User, VulnerabilityIndicator
from app.db.repositories import (
    AnalysisRepository,
    AuditRepository,
    CaseRepository,
    IndicatorRepository,
    OutboxRepository,
    UserRepository,
)
from app.domain.business_calendar import BusinessCalendar, HolidayDataUnavailableError
from app.domain.deadlines import (
    CaseDeadlines,
    DeadlineTracking,
    calculate_deadlines,
    track_deadlines,
)
from app.domain.enums import AnalysisStatus, AuditSource, CaseStatus
from app.logging_config import correlation_id_var
from app.messaging.outbox import analysis_job_message
from app.schemas.cases import CaseCreate

logger = logging.getLogger(__name__)


class CaseNotFoundError(Exception):
    pass


class AssigneeNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class CaseReview:
    """What a handler reviews: the AI's suggestion, why it needs a person, the indicators."""

    suggestion: CaseAnalysis | None
    review_reason: str | None
    indicators: tuple[VulnerabilityIndicator, ...]


_NOT_YET_ANALYSED = (CaseStatus.NEW, CaseStatus.ANALYSING)


@dataclass(frozen=True)
class CreateCaseResult:
    case: Case
    created: bool  # False when an existing case was returned for a duplicate external_message_id


def new_reference(received_at: datetime) -> str:
    """Human-readable, unguessable reference such as CMP-2026-3F9A1C2B."""
    return f"CMP-{received_at.year}-{secrets.token_hex(4).upper()}"


class CaseService:
    def __init__(self, session: Session, actor: User, calendar: BusinessCalendar) -> None:
        self.session = session
        self.actor = actor
        self.calendar = calendar  # the actor's tenant's bank holidays
        self.cases = CaseRepository(session, actor.tenant_id)
        self.users = UserRepository(session, actor.tenant_id)
        self.audit = AuditRepository(session, actor.tenant_id)
        self.analyses = AnalysisRepository(session, actor.tenant_id)
        self.indicators = IndicatorRepository(session, actor.tenant_id)
        self.outbox = OutboxRepository(session)

    def create(self, data: CaseCreate) -> CreateCaseResult:
        if data.external_message_id is not None:
            existing = self.cases.get_by_external_message_id(data.external_message_id)
            if existing is not None:
                logger.info("Duplicate intake ignored", extra={"case_id": existing.id})
                return CreateCaseResult(case=existing, created=False)

        received_at = (data.received_at or datetime.now(UTC)).astimezone(UTC)
        deadlines = self._calculate_deadlines(received_at)
        case = self.cases.add(
            Case(
                id=uuid.uuid4(),
                reference=new_reference(received_at),
                external_message_id=data.external_message_id,
                subject=data.subject,
                body=data.body,
                sender_email=str(data.sender_email),
                sender_name=data.sender_name,
                received_at=received_at,
                src_deadline_at=deadlines.src_deadline_at if deadlines else None,
                final_response_deadline_at=(
                    deadlines.final_response_deadline_at if deadlines else None
                ),
            )
        )
        self._record(case, action="case_created", source=AuditSource.SYSTEM)
        correlation_id = correlation_id_var.get() or uuid.uuid4().hex
        self.outbox.add(analysis_job_message(case, correlation_id))

        # Case + audit event + analysis job in ONE transaction (US-3.6, US-1.5).
        self.session.commit()
        logger.info("Case created", extra={"case_id": case.id, "tenant_id": case.tenant_id})
        return CreateCaseResult(case=case, created=True)

    def deadline_tracking(self, case: Case, now: datetime) -> DeadlineTracking | None:
        """Business days remaining / overdue / resolved in time. None when deadlines are unknown."""
        if case.src_deadline_at is None or case.final_response_deadline_at is None:
            return None
        deadlines = CaseDeadlines(case.src_deadline_at, case.final_response_deadline_at)
        try:
            return track_deadlines(
                deadlines,
                now=now,
                calendar=self.calendar,
                resolved_at=case.resolved_at,
                resolution_type=case.resolution_type,
            )
        except HolidayDataUnavailableError:
            logger.warning("Bank holiday data out of range", extra={"case_id": case.id})
            return None

    def review(self, case: Case) -> CaseReview:
        """US-2.4: nothing is shown while the analysis is running. A failed attempt is never
        shown as a suggestion: only a COMPLETED analysis is (US-2.5)."""
        if case.status in _NOT_YET_ANALYSED:
            return CaseReview(None, None, ())
        reason = None
        if case.status is CaseStatus.NEEDS_HUMAN_REVIEW:
            # The audit event of the failure is the one record of why a person is needed.
            failure = self.audit.latest_for_case_with_action(case.id, "analysis_failed")
            if failure is not None and isinstance(failure.new_value, dict):
                reason = failure.new_value.get("reason")
        return CaseReview(
            suggestion=self.analyses.latest_for_case(case.id, status=AnalysisStatus.COMPLETED),
            review_reason=reason,
            indicators=tuple(self.indicators.list_for_case(case.id)),
        )

    def get(self, case_id: uuid.UUID) -> Case:
        case = self.cases.get(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        return case

    def assign(self, case_id: uuid.UUID, assignee_id: uuid.UUID | None) -> Case:
        case = self.get(case_id)
        # The assignee must belong to the same tenant. UserRepository is tenant-scoped,
        # so a user from another tenant simply "does not exist" here.
        if assignee_id is not None and self.users.get(assignee_id) is None:
            raise AssigneeNotFoundError(assignee_id)

        old_value = case.assigned_to_user_id
        if old_value != assignee_id:
            case.assigned_to_user_id = assignee_id
            self._record(
                case,
                action="case_assigned",
                source=AuditSource.HANDLER,
                field="assigned_to_user_id",
                old_value=str(old_value) if old_value else None,
                new_value=str(assignee_id) if assignee_id else None,
            )
            self.session.commit()
        return case

    def _calculate_deadlines(self, received_at: datetime) -> CaseDeadlines | None:
        """The case is saved even when deadlines cannot be calculated (US-1): an unknown deadline
        stays empty and is logged as an error, rather than being guessed."""
        try:
            return calculate_deadlines(received_at, self.calendar)
        except HolidayDataUnavailableError:
            logger.error(
                "Deadlines not set: bank holiday data out of range",
                extra={"tenant_id": self.actor.tenant_id},
            )
            return None

    def _record(
        self,
        case: Case,
        *,
        action: str,
        source: AuditSource,
        field: str | None = None,
        old_value: object = None,
        new_value: object = None,
    ) -> None:
        self.audit.add(
            AuditEvent(
                case=case,
                actor_user_id=self.actor.id,
                action=action,
                field=field,
                old_value=old_value,
                new_value=new_value,
                source=source,
                correlation_id=correlation_id_var.get(),
            )
        )
