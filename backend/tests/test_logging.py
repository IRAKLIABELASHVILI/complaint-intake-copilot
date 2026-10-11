"""What the logs may contain (US-6.6 and the logging requirement in docs/user-stories.md).

One complaint full of personal data goes through every step that logs: intake, a duplicate,
an invalid intake, the outbox relay, the worker, an invalid model answer, invented evidence,
and a decision. Every line is then checked: valid JSON, a correlation id, and none of the
complaint's text or personal data.

C# comparison: like asserting on what an ILogger received, with a test sink attached.
"""

import json
import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.logging_config import JsonFormatter
from app.messaging.outbox import OutboxRelay
from app.worker.analysis_job_handler import AnalysisJobHandler
from app.worker.case_analyser import CaseAnalyser
from app.worker.consumer import JobConsumer
from tests.conftest import TwoTenants, complaint_payload
from tests.fakes import (
    FakeChannel,
    FakeMethod,
    FakeProperties,
    RecordingMessageBus,
    ScriptedProvider,
    model_answer,
)

SENDER_NAME = "Priya Fictional"
SENDER_EMAIL = "priya.fictional@example.com"
PHONE = "07700 900123"
CARD = "4111 1111 1111 1111"
SUBJECT = "Overdraft fee after my mother's funeral"
BODY = (
    f"My mother passed away in March and the fee pushed me into my overdraft. "
    f"Call me on {PHONE}. The card was {CARD}."
)
# Words that must never reach a log line, whichever part of the code wrote it.
NEVER_LOGGED = [SENDER_NAME, "Priya", SENDER_EMAIL, PHONE, CARD, SUBJECT, "passed away"]


class FormatAtEmit(logging.Handler):
    """Formats each record when it is logged, as the real handler does, so the correlation id
    is read while it is still set."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def log_lines() -> Iterator[list[str]]:
    handler = FormatAtEmit()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield handler.lines
    root.removeHandler(handler)
    root.setLevel(previous_level)


def test_logs_carry_ids_but_never_the_complaint_or_personal_data(
    client: TestClient,
    tenants: TwoTenants,
    session_factory: sessionmaker[Session],
    log_lines: list[str],
) -> None:
    user = tenants.handler_a
    payload = complaint_payload(
        subject=SUBJECT,
        body=BODY,
        sender_name=SENDER_NAME,
        sender_email=SENDER_EMAIL,
        external_message_id=f"<{uuid.uuid4()}@mail.example.com>",
    )
    headers = user.headers | {"X-Correlation-ID": "intake-1"}

    # Intake, the same email again, and an invalid one that still carries the personal data.
    case = client.post("/cases", json=payload, headers=headers).json()
    assert client.post("/cases", json=payload, headers=headers).status_code == 200  # existing
    invalid = payload | {"sender_email": f"{SENDER_NAME} at home", "external_message_id": None}
    assert client.post("/cases", json=invalid, headers=headers).status_code == 422

    # The relay publishes the job; the worker runs it. The model first answers with the
    # complaint itself (invalid), then with evidence it made up, quoting personal data.
    bus = RecordingMessageBus()
    OutboxRelay(session_factory, bus).publish_pending()
    invented = [{"type": "physical_illness", "evidence_quote": f"{SENDER_EMAIL} is very ill"}]
    provider = ScriptedProvider([f"Sure! {BODY}", model_answer(vulnerability_indicators=invented)])
    consumer = JobConsumer(AnalysisJobHandler(session_factory, CaseAnalyser(provider)))
    channel = FakeChannel()
    consumer.on_message(channel, FakeMethod(1), FakeProperties(), bus.published[0].body)
    assert channel.acked == [1]

    decision = client.put(
        f"/cases/{case['id']}/category", json={"category": "other"}, headers=headers
    )
    assert decision.status_code == 200

    records = [json.loads(line) for line in log_lines]  # every line is JSON
    messages = {record["message"] for record in records}
    assert {"Case created", "Duplicate intake ignored", "Outbox message published"} <= messages
    assert {"Text redacted", "Model answer invalid", "Job handled"} <= messages
    assert "Indicator dropped: evidence not found in the text" in messages

    own_lines = [record for record in records if record["logger"].startswith("app.")]
    assert {record["correlation_id"] for record in own_lines} == {"intake-1"}  # end to end
    assert any(record.get("case_id") == case["id"] for record in own_lines)

    for line in log_lines:
        for value in NEVER_LOGGED:
            assert value not in line, f"{value!r} was logged: {line}"
