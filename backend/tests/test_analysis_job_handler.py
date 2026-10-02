"""The worker's job handler: idempotent, tenant-safe, and audited (US-1, US-3.6, US-7.6)."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuditEvent, Case, ProcessedMessage
from app.domain.enums import CaseStatus
from app.messaging.messages import AnalysisJob
from app.worker.analysis_job_handler import AnalysisJobHandler, CaseNotFoundForJobError
from app.worker.jobs import JobOutcome
from tests.conftest import SeededUser, TwoTenants

CreateCase = Callable[..., dict[str, object]]


@pytest.fixture
def handler(session_factory: sessionmaker[Session]) -> AnalysisJobHandler:
    return AnalysisJobHandler(session_factory)


def _job(case: dict[str, object], user: SeededUser, **overrides: object) -> AnalysisJob:
    values: dict[str, object] = {
        "message_id": uuid.uuid4(),
        "case_id": case["id"],
        "tenant_id": user.tenant_id,
        "correlation_id": "corr-1",
    }
    return AnalysisJob.model_validate(values | overrides)


def _case(db: Session, case_id: object) -> Case:
    db.expire_all()
    case = db.get(Case, uuid.UUID(str(case_id)))
    assert case is not None
    return case


def _status_audit_events(db: Session, case_id: object) -> list[AuditEvent]:
    statement = select(AuditEvent).where(
        AuditEvent.case_id == uuid.UUID(str(case_id)), AuditEvent.action == "analysis_started"
    )
    return list(db.scalars(statement))


def test_a_new_case_moves_to_analysing_with_an_audit_event(
    handler: AnalysisJobHandler, db: Session, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)
    job = _job(case, tenants.handler_a)

    assert handler.handle(job) is JobOutcome.PROCESSED

    assert _case(db, case["id"]).status is CaseStatus.ANALYSING
    [event] = _status_audit_events(db, case["id"])
    assert (event.old_value, event.new_value) == ("new", "analysing")
    assert event.correlation_id == "corr-1"
    assert event.actor_user_id is None  # done by the system, not a person
    assert db.get(ProcessedMessage, job.message_id) is not None


def test_the_same_message_twice_is_handled_once(
    handler: AnalysisJobHandler, db: Session, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)
    job = _job(case, tenants.handler_a)

    handler.handle(job)
    assert handler.handle(job) is JobOutcome.DUPLICATE

    assert len(_status_audit_events(db, case["id"])) == 1


def test_a_second_job_for_a_case_already_started_changes_nothing(
    handler: AnalysisJobHandler, db: Session, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)
    handler.handle(_job(case, tenants.handler_a))

    outcome = handler.handle(_job(case, tenants.handler_a))  # different message id

    assert outcome is JobOutcome.ALREADY_STARTED
    assert len(_status_audit_events(db, case["id"])) == 1


def test_a_job_with_another_tenants_id_cannot_touch_the_case(
    handler: AnalysisJobHandler, db: Session, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.6: the case is loaded by case id AND tenant id from the message."""
    case_b = create_case(tenants.handler_b)
    job = _job(case_b, tenants.handler_a)  # tenant A's id on tenant B's case

    with pytest.raises(CaseNotFoundForJobError):
        handler.handle(job)

    assert _case(db, case_b["id"]).status is CaseStatus.NEW
    assert db.get(ProcessedMessage, job.message_id) is None
