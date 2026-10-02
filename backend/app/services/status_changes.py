"""The one way to change a case's status: check the state machine, change it, audit it.

Used by both the worker (system changes) and the case service (handler decisions), so every
status change is validated and audited the same way, in the caller's transaction (US-3.6).
"""

import uuid

from app.db.models import AuditEvent, Case
from app.db.repositories import AuditRepository
from app.domain.case_status import ensure_transition
from app.domain.enums import AuditSource, CaseStatus


def change_status(
    case: Case,
    new_status: CaseStatus,
    *,
    audit: AuditRepository,
    action: str,
    source: AuditSource,
    actor_user_id: uuid.UUID | None,
    correlation_id: str | None,
    reason: str | None = None,
) -> None:
    ensure_transition(case.status, new_status)  # raises InvalidStatusTransitionError
    old_status = case.status
    case.status = new_status
    new_value: object = (
        new_status.value
        if reason is None
        else {
            "status": new_status.value,
            "reason": reason,
        }
    )
    audit.add(
        AuditEvent(
            case=case,
            actor_user_id=actor_user_id,
            action=action,
            field="status",
            old_value=old_status.value,
            new_value=new_value,
            source=source,
            correlation_id=correlation_id,
        )
    )
