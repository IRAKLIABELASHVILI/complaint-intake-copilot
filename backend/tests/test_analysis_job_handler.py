"""The worker's job handler end to end, with a scripted model (US-2, US-6, US-7.6, idempotency)."""

import json
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import ProviderRejectedError, ProviderUnavailableError
from app.db.models import (
    AuditEvent,
    Case,
    CaseAnalysis,
    ProcessedMessage,
    VulnerabilityIndicator,
)
from app.domain import redaction
from app.domain.enums import (
    AnalysisStatus,
    CaseStatus,
    IndicatorDecision,
    IndicatorSource,
    IndicatorType,
    Priority,
    VulnerabilityDriver,
)
from app.messaging.messages import AnalysisJob
from app.worker.analysis_job_handler import (
    AnalysisJobHandler,
    CaseNotFoundForJobError,
    ProviderRejectedJobError,
)
from app.worker.case_analyser import INVALID_TWICE, REDACTION_FAILED, CaseAnalyser
from app.worker.jobs import JobOutcome
from tests.conftest import SeededUser, TwoTenants
from tests.fakes import ScriptedProvider, model_answer

CreateCase = Callable[..., dict[str, object]]

BEREAVED = (
    "My husband passed away last month. You charged a late fee anyway. "
    "Call me on 07700 900123.\n\nRegards,\nJane Doe"
)


def make_handler(
    session_factory: sessionmaker[Session], *script: str | Exception
) -> tuple[AnalysisJobHandler, ScriptedProvider]:
    provider = ScriptedProvider(list(script))
    return AnalysisJobHandler(session_factory, CaseAnalyser(provider)), provider


def job_for(case: dict[str, object], user: SeededUser, **overrides: object) -> AnalysisJob:
    values: dict[str, object] = {
        "message_id": uuid.uuid4(),
        "case_id": case["id"],
        "tenant_id": user.tenant_id,
        "correlation_id": "corr-1",
    }
    return AnalysisJob.model_validate(values | overrides)


def load(db: Session, case: dict[str, object]) -> Case:
    db.expire_all()
    loaded = db.get(Case, uuid.UUID(str(case["id"])))
    assert loaded is not None
    return loaded


def rows[T](db: Session, model: type[T], case: dict[str, object]) -> list[T]:
    db.expire_all()
    statement = select(model).where(model.case_id == uuid.UUID(str(case["id"])))  # type: ignore[attr-defined]
    return list(db.scalars(statement))


def status_actions(db: Session, case: dict[str, object]) -> list[str]:
    events = rows(db, AuditEvent, case)
    return [e.action for e in sorted(events, key=lambda e: e.created_at) if e.field == "status"]


# --- Success -------------------------------------------------------------------------------------


def test_a_valid_answer_puts_the_case_in_awaiting_review_with_suggestions(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a, body=BEREAVED, sender_name="Jane Doe")
    indicator = {"type": "bereavement", "evidence_quote": "My husband passed away last month."}
    handler, _ = make_handler(
        session_factory, model_answer(priority="low", vulnerability_indicators=[indicator])
    )
    job = job_for(case, tenants.handler_a)

    assert handler.handle(job) is JobOutcome.PROCESSED

    assert load(db, case).status is CaseStatus.AWAITING_REVIEW
    assert status_actions(db, case) == ["analysis_started", "analysis_completed"]
    [analysis] = rows(db, CaseAnalysis, case)
    assert analysis.status is AnalysisStatus.COMPLETED
    assert (analysis.provider, analysis.model) == ("scripted", "scripted-v1")
    assert analysis.suggested_priority is Priority.HIGH  # lifted by the vulnerability rule
    assert analysis.correlation_id == "corr-1"
    [flag] = rows(db, VulnerabilityIndicator, case)
    assert (flag.indicator_type, flag.driver) == (
        IndicatorType.BEREAVEMENT,
        VulnerabilityDriver.LIFE_EVENTS,
    )
    assert (flag.source, flag.decision) == (IndicatorSource.AI, IndicatorDecision.PENDING)
    assert flag.analysis_id == analysis.id
    assert db.get(ProcessedMessage, job.message_id) is not None


def test_only_redacted_text_reaches_the_model_and_it_is_stored_as_sent(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a, body=BEREAVED, sender_name="Jane Doe")
    handler, provider = make_handler(session_factory, model_answer())

    handler.handle(job_for(case, tenants.handler_a))

    [(sent, _)] = provider.calls
    assert "07700 900123" not in sent and "Jane Doe" not in sent
    assert "[PHONE_1]" in sent and "[NAME_1]" in sent
    assert rows(db, CaseAnalysis, case)[0].redacted_input == sent
    assert load(db, case).body == BEREAVED  # the original stays in our database only


# --- Invalid answers (US-2.5) --------------------------------------------------------------------


def test_one_invalid_answer_is_retried_with_the_reason(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a)
    handler, provider = make_handler(session_factory, "not json", model_answer())

    assert handler.handle(job_for(case, tenants.handler_a)) is JobOutcome.PROCESSED

    assert load(db, case).status is CaseStatus.AWAITING_REVIEW
    assert provider.calls[1][1] == "The answer is not valid JSON"
    statuses = sorted(a.status for a in rows(db, CaseAnalysis, case))
    assert statuses == [AnalysisStatus.COMPLETED, AnalysisStatus.INVALID_OUTPUT]


def test_two_invalid_answers_send_the_case_to_human_review_with_the_reason(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a)
    handler, _ = make_handler(session_factory, "not json", model_answer(category="nonsense"))

    assert handler.handle(job_for(case, tenants.handler_a)) is JobOutcome.PROCESSED

    assert load(db, case).status is CaseStatus.NEEDS_HUMAN_REVIEW
    analyses = rows(db, CaseAnalysis, case)
    assert [a.status for a in analyses] == [AnalysisStatus.INVALID_OUTPUT] * 2
    assert all(a.suggested_category is None for a in analyses)  # nothing shown as if valid
    assert rows(db, VulnerabilityIndicator, case) == []
    failed = [e for e in rows(db, AuditEvent, case) if e.action == "analysis_failed"]
    assert failed[0].new_value == {"status": "needs_human_review", "reason": INVALID_TWICE}


# --- Redaction fails closed (US-6.5) -------------------------------------------------------------


def test_a_redaction_failure_never_calls_the_model(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_redact(text: str, *, sender_name: str | None = None) -> redaction.RedactedText:
        raise redaction.RedactionError("boom")

    monkeypatch.setattr("app.worker.case_analyser.redact", broken_redact)
    case = create_case(tenants.handler_a)
    handler, provider = make_handler(session_factory, model_answer())

    handler.handle(job_for(case, tenants.handler_a))

    assert provider.calls == []
    assert load(db, case).status is CaseStatus.NEEDS_HUMAN_REVIEW
    [analysis] = rows(db, CaseAnalysis, case)
    assert (analysis.status, analysis.error) == (AnalysisStatus.FAILED, REDACTION_FAILED)
    assert analysis.redacted_input is None


# --- Provider failures ---------------------------------------------------------------------------


def test_a_model_outage_leaves_the_case_analysing_and_the_retry_resumes_it(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a)
    job = job_for(case, tenants.handler_a)
    handler, _ = make_handler(session_factory, ProviderUnavailableError("timeout"), model_answer())

    with pytest.raises(ProviderUnavailableError):  # the queue will retry this job
        handler.handle(job)
    assert load(db, case).status is CaseStatus.ANALYSING
    assert db.get(ProcessedMessage, job.message_id) is None

    assert handler.handle(job) is JobOutcome.PROCESSED  # the redelivery
    assert load(db, case).status is CaseStatus.AWAITING_REVIEW
    assert status_actions(db, case).count("analysis_started") == 1


def test_a_provider_refusal_is_a_permanent_failure(
    session_factory: sessionmaker[Session], tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)
    handler, _ = make_handler(session_factory, ProviderRejectedError("AuthenticationError"))

    with pytest.raises(ProviderRejectedJobError):
        handler.handle(job_for(case, tenants.handler_a))


def test_a_dead_lettered_job_sends_the_case_to_human_review(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a)
    job = job_for(case, tenants.handler_a)
    handler, _ = make_handler(session_factory, ProviderUnavailableError("down"))
    with pytest.raises(ProviderUnavailableError):
        handler.handle(job)

    handler.on_dead_letter(job, "Gave up after 5 attempts: ProviderUnavailableError")

    assert load(db, case).status is CaseStatus.NEEDS_HUMAN_REVIEW
    [analysis] = rows(db, CaseAnalysis, case)
    assert analysis.status is AnalysisStatus.FAILED
    assert analysis.error == "Gave up after 5 attempts: ProviderUnavailableError"


# --- Idempotency and tenant safety ---------------------------------------------------------------


def test_the_same_message_twice_is_handled_once(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a)
    job = job_for(case, tenants.handler_a)
    handler, provider = make_handler(session_factory, model_answer(), model_answer())

    handler.handle(job)
    assert handler.handle(job) is JobOutcome.DUPLICATE

    assert len(provider.calls) == 1  # the model is not asked (or paid) twice
    assert len(rows(db, CaseAnalysis, case)) == 1


def test_a_second_job_for_an_analysed_case_changes_nothing(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a)
    handler, provider = make_handler(session_factory, model_answer())
    handler.handle(job_for(case, tenants.handler_a))

    outcome = handler.handle(job_for(case, tenants.handler_a))  # a different message id

    assert outcome is JobOutcome.ALREADY_STARTED
    assert len(provider.calls) == 1


def test_a_job_with_another_tenants_id_cannot_touch_the_case(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    """US-7.6: the case is loaded by case id AND tenant id from the message."""
    case_b = create_case(tenants.handler_b)
    handler, provider = make_handler(session_factory, model_answer())

    with pytest.raises(CaseNotFoundForJobError):
        handler.handle(job_for(case_b, tenants.handler_a))

    assert load(db, case_b).status is CaseStatus.NEW
    assert provider.calls == []


def test_the_message_payload_is_ids_only() -> None:
    job = AnalysisJob(
        message_id=uuid.uuid4(), case_id=uuid.uuid4(), tenant_id=uuid.uuid4(), correlation_id="c"
    )

    assert set(json.loads(job.to_bytes())) == {
        "message_id",
        "case_id",
        "tenant_id",
        "correlation_id",
    }
