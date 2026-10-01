"""Use cases for complaint cases. Endpoints stay thin; the rules live here.

C# comparison: an application service (CaseService : ICaseService) that receives its repositories.
"""

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Case, User
from app.db.repositories import AuditRepository, CaseRepository, UserRepository
from app.domain.enums import AuditSource
from app.logging_config import correlation_id_var
from app.schemas.cases import CaseCreate

logger = logging.getLogger(__name__)


class CaseNotFoundError(Exception):
    pass


class AssigneeNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class CreateCaseResult:
    case: Case
    created: bool  # False when an existing case was returned for a duplicate external_message_id


def new_reference(received_at: datetime) -> str:
    """Human-readable, unguessable reference such as CMP-2026-3F9A1C2B."""
    return f"CMP-{received_at.year}-{secrets.token_hex(4).upper()}"


class CaseService:
    def __init__(self, session: Session, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.cases = CaseRepository(session, actor.tenant_id)
        self.users = UserRepository(session, actor.tenant_id)
        self.audit = AuditRepository(session, actor.tenant_id)

    def create(self, data: CaseCreate) -> CreateCaseResult:
        if data.external_message_id is not None:
            existing = self.cases.get_by_external_message_id(data.external_message_id)
            if existing is not None:
                logger.info("Duplicate intake ignored", extra={"case_id": existing.id})
                return CreateCaseResult(case=existing, created=False)

        received_at = (data.received_at or datetime.now(UTC)).astimezone(UTC)
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
            )
        )
        # Milestone 3: calculate deadlines here. Milestone 4: publish the analysis job.
        self._record(case, action="case_created", source=AuditSource.SYSTEM)

        self.session.commit()  # case + audit event in ONE transaction (US-3.6)
        logger.info("Case created", extra={"case_id": case.id, "tenant_id": case.tenant_id})
        return CreateCaseResult(case=case, created=True)

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
