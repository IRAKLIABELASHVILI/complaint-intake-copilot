"""Intake queues exactly one analysis job, and the relay publishes it even after an outage.

US-1.5: exactly one job per case. US-1.6: a broker outage never loses a case or a job.
"""

import json
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import OutboxMessage
from app.messaging.messages import ANALYSIS_QUEUE
from app.messaging.outbox import OutboxRelay
from tests.conftest import TwoTenants, complaint_payload
from tests.fakes import RecordingMessageBus

CreateCase = Callable[..., dict[str, object]]


def _outbox(db: Session) -> list[OutboxMessage]:
    db.expire_all()
    return list(db.scalars(select(OutboxMessage).order_by(OutboxMessage.created_at)))


def test_creating_a_case_queues_exactly_one_analysis_job(
    db: Session, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)

    [message] = _outbox(db)
    assert message.queue == ANALYSIS_QUEUE
    assert message.published_at is None
    assert message.payload["case_id"] == case["id"]
    assert message.payload["tenant_id"] == str(tenants.handler_a.tenant_id)
    assert message.payload["message_id"] == str(message.id)


def test_job_carries_the_request_correlation_id(
    client: TestClient, db: Session, tenants: TwoTenants
) -> None:
    headers = tenants.handler_a.headers | {"X-Correlation-ID": "req-123"}

    client.post("/cases", json=complaint_payload(), headers=headers)

    [message] = _outbox(db)
    assert message.payload["correlation_id"] == "req-123"


def test_a_duplicate_submission_does_not_queue_a_second_job(
    client: TestClient, db: Session, tenants: TwoTenants
) -> None:
    payload = complaint_payload(external_message_id="<dup@mail.example.com>")

    client.post("/cases", json=payload, headers=tenants.handler_a.headers)
    client.post("/cases", json=payload, headers=tenants.handler_a.headers)

    assert len(_outbox(db)) == 1


def test_relay_publishes_pending_jobs_once(
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    create_case(tenants.handler_a)
    create_case(tenants.handler_b)
    bus = RecordingMessageBus()
    relay = OutboxRelay(session_factory, bus)

    assert relay.publish_pending() == 2
    assert relay.publish_pending() == 0  # nothing is published twice

    outbox = _outbox(db)
    assert [m.queue for m in bus.published] == [ANALYSIS_QUEUE, ANALYSIS_QUEUE]
    assert [m.message_id for m in bus.published] == [m.id for m in outbox]  # oldest first
    assert json.loads(bus.published[0].body) == outbox[0].payload
    assert all(m.published_at is not None for m in outbox)


def test_broker_outage_keeps_the_case_and_the_job_for_later(
    client: TestClient,
    session_factory: sessionmaker[Session],
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
) -> None:
    case = create_case(tenants.handler_a)  # the API never touches the broker, so this works
    bus = RecordingMessageBus(fail_with=ConnectionError("broker down"))
    relay = OutboxRelay(session_factory, bus)

    assert relay.publish_pending() == 0

    [message] = _outbox(db)
    assert message.published_at is None
    assert message.attempts == 1
    assert message.last_error == "ConnectionError"
    assert client.get(f"/cases/{case['id']}", headers=tenants.handler_a.headers).status_code == 200

    bus.fail_with = None  # the broker is back
    assert relay.publish_pending() == 1
    assert _outbox(db)[0].published_at is not None
