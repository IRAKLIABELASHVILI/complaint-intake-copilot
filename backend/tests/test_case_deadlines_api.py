"""Deadlines through the API (US-4.1, US-4.6): stored at intake, counted down on every read.

The clock is frozen by overriding the `get_now` dependency, so these tests never depend on
today's date. C# comparison: registering a FakeTimeProvider in WebApplicationFactory.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_now
from app.main import app
from tests.conftest import TwoTenants, complaint_payload

# complaint_payload() is received Monday 2026-09-14 09:30 BST.
SRC_DEADLINE = "2026-09-17T16:00:00Z"  # Thursday 17:00 BST
FINAL_RESPONSE_DEADLINE = "2026-11-09T23:59:59Z"  # Monday 23:59:59 GMT


@pytest.fixture
def freeze_time(client: TestClient) -> Iterator[Callable[[datetime], None]]:
    def _freeze(moment: datetime) -> None:
        app.dependency_overrides[get_now] = lambda: moment

    yield _freeze
    app.dependency_overrides.pop(get_now, None)


def test_new_case_has_both_deadlines_and_a_countdown(
    client: TestClient, tenants: TwoTenants, freeze_time: Callable[[datetime], None]
) -> None:
    freeze_time(datetime(2026, 9, 15, 9, tzinfo=UTC))  # Tuesday

    response = client.post("/cases", json=complaint_payload(), headers=tenants.handler_a.headers)

    body = response.json()
    assert body["src_deadline_at"] == SRC_DEADLINE
    assert body["final_response_deadline_at"] == FINAL_RESPONSE_DEADLINE
    src = body["deadline_tracking"]["src"]
    assert src["business_days_remaining"] == 2
    assert src["is_overdue"] is False
    assert body["deadline_tracking"]["resolved_in_time"] is None


def test_countdown_is_recalculated_on_every_read(
    client: TestClient,
    tenants: TwoTenants,
    create_case: Callable[..., dict[str, object]],
    freeze_time: Callable[[datetime], None],
) -> None:
    case = create_case(tenants.handler_a)
    freeze_time(datetime(2026, 9, 21, 9, tzinfo=UTC))  # the Monday after the SRC deadline

    body = client.get(f"/cases/{case['id']}", headers=tenants.handler_a.headers).json()

    src = body["deadline_tracking"]["src"]
    assert src["business_days_remaining"] == -2
    assert src["is_overdue"] is True
    assert body["deadline_tracking"]["final_response"]["is_overdue"] is False


def test_case_list_shows_the_countdown_too(
    client: TestClient,
    tenants: TwoTenants,
    create_case: Callable[..., dict[str, object]],
    freeze_time: Callable[[datetime], None],
) -> None:
    create_case(tenants.handler_a)
    freeze_time(datetime(2026, 9, 17, 9, tzinfo=UTC))  # deadline day, before 17:00

    item = client.get("/cases", headers=tenants.handler_a.headers).json()["items"][0]

    assert item["src_deadline_at"] == SRC_DEADLINE
    assert item["deadline_tracking"]["src"]["business_days_remaining"] == 0
