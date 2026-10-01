"""Case intake and CRUD (US-1, US-3 audit basics). Written by the mentor; these tell you
whether the tenant-scoped repository works for a single tenant."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import TwoTenants, complaint_payload


def test_create_case_returns_201_with_new_status_and_reference(
    client: TestClient, tenants: TwoTenants
) -> None:
    response = client.post("/cases", json=complaint_payload(), headers=tenants.handler_a.headers)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "new"
    assert body["reference"].startswith("CMP-2026-")
    assert body["received_at"] == "2026-09-14T08:30:00Z"  # stored and returned in UTC


def test_create_case_without_received_at_uses_server_time(
    client: TestClient, tenants: TwoTenants
) -> None:
    payload = complaint_payload()
    del payload["received_at"]

    response = client.post("/cases", json=payload, headers=tenants.handler_a.headers)

    assert response.status_code == 201
    assert response.json()["received_at"] is not None


def test_create_case_requires_authentication(client: TestClient, tenants: TwoTenants) -> None:
    assert client.post("/cases", json=complaint_payload()).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.post("/cases", json=complaint_payload(), headers=bad).status_code == 401


def test_create_case_rejects_invalid_input(client: TestClient, tenants: TwoTenants) -> None:
    headers = tenants.handler_a.headers
    invalid_payloads = [
        complaint_payload(body=""),
        complaint_payload(body="   "),  # whitespace only is stripped to empty
        complaint_payload(sender_email="not-an-email"),
        complaint_payload(received_at="2099-01-01T09:00:00+00:00"),  # future
        complaint_payload(received_at="2026-09-14T09:30:00"),  # no timezone
        complaint_payload(tenant_id="00000000-0000-0000-0000-000000000000"),  # unknown field
    ]
    for payload in invalid_payloads:
        response = client.post("/cases", json=payload, headers=headers)
        assert response.status_code == 422, payload

    listing = client.get("/cases", headers=headers).json()
    assert listing["total"] == 0  # nothing was created


def test_duplicate_external_message_id_returns_existing_case(
    client: TestClient, tenants: TwoTenants
) -> None:
    payload = complaint_payload(external_message_id="<abc123@mail.example.com>")
    headers = tenants.handler_a.headers

    first = client.post("/cases", json=payload, headers=headers)
    second = client.post("/cases", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert client.get("/cases", headers=headers).json()["total"] == 1


def test_get_case_by_id(
    client: TestClient, tenants: TwoTenants, create_case: Callable[..., dict[str, object]]
) -> None:
    case = create_case(tenants.handler_a)

    response = client.get(f"/cases/{case['id']}", headers=tenants.handler_a.headers)

    assert response.status_code == 200
    assert response.json()["body"] == complaint_payload()["body"]


def test_get_unknown_case_returns_404(client: TestClient, tenants: TwoTenants) -> None:
    response = client.get(
        "/cases/3f0c2b7e-0000-4000-8000-000000000000", headers=tenants.handler_a.headers
    )
    assert response.status_code == 404


def test_list_cases_newest_first_with_pagination_and_status_filter(
    client: TestClient, tenants: TwoTenants, create_case: Callable[..., dict[str, object]]
) -> None:
    create_case(tenants.handler_a, subject="older", received_at="2026-09-01T10:00:00+00:00")
    create_case(tenants.handler_a, subject="newer", received_at="2026-09-10T10:00:00+00:00")
    headers = tenants.handler_a.headers

    page = client.get("/cases?limit=1", headers=headers).json()
    assert page["total"] == 2
    assert [item["subject"] for item in page["items"]] == ["newer"]

    assert client.get("/cases?status=new", headers=headers).json()["total"] == 2
    assert client.get("/cases?status=resolved", headers=headers).json()["total"] == 0
    assert client.get("/cases?status=nonsense", headers=headers).status_code == 422


def test_creating_a_case_writes_an_audit_event(
    client: TestClient, tenants: TwoTenants, create_case: Callable[..., dict[str, object]]
) -> None:
    case = create_case(tenants.handler_a)

    events = client.get(f"/cases/{case['id']}/audit", headers=tenants.handler_a.headers).json()

    assert len(events) == 1
    assert events[0]["action"] == "case_created"
    assert events[0]["actor_user_id"] == str(tenants.handler_a.id)
    assert events[0]["correlation_id"]


def test_assign_case_to_colleague_is_audited(
    client: TestClient, tenants: TwoTenants, create_case: Callable[..., dict[str, object]]
) -> None:
    case = create_case(tenants.handler_a)
    colleague_id = str(tenants.second_handler_a.id)

    response = client.patch(
        f"/cases/{case['id']}/assignment",
        json={"assigned_to_user_id": colleague_id},
        headers=tenants.handler_a.headers,
    )

    assert response.status_code == 200
    assert response.json()["assigned_to_user_id"] == colleague_id
    events = client.get(f"/cases/{case['id']}/audit", headers=tenants.handler_a.headers).json()
    assignment = next(event for event in events if event["action"] == "case_assigned")
    assert assignment["old_value"] is None
    assert assignment["new_value"] == colleague_id


def test_correlation_id_is_echoed_or_generated(client: TestClient, tenants: TwoTenants) -> None:
    given = client.get("/health/live", headers={"X-Correlation-ID": "abc-123"})
    assert given.headers["X-Correlation-ID"] == "abc-123"

    generated = client.get("/health/live", headers={"X-Correlation-ID": "bad value!\n"})
    assert generated.headers["X-Correlation-ID"] != "bad value!\n"
    assert len(generated.headers["X-Correlation-ID"]) == 32
