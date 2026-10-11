"""User-visible workspace workflows and their authorization boundaries."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import LoginSession, User
from app.domain.draft_placeholders import unfilled_placeholders
from app.services.accounts import hash_password
from tests.conftest import TwoTenants

CreateCase = Callable[..., dict[str, object]]


def test_search_dates_and_literal_wildcards(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    first = create_case(tenants.handler_a, subject="Refund 100%", body="A missing transfer")
    create_case(
        tenants.handler_a, subject="Other", body="Nothing here", received_at="2026-09-15T00:00:00Z"
    )
    create_case(tenants.handler_b, subject="Refund 100%")
    for q in ["100%", "TRANSFER", str(first["reference"])]:
        result = client.get(
            "/cases",
            params={"q": q, "received_from": "2026-09-14", "received_to": "2026-09-14"},
            headers=tenants.handler_a.headers,
        )
        assert result.status_code == 200
        assert [case["id"] for case in result.json()["items"]] == [first["id"]]
    assert (
        client.get(
            "/cases?received_from=2026-09-15&received_to=2026-09-14",
            headers=tenants.handler_a.headers,
        ).status_code
        == 422
    )


def test_saved_views_are_private_and_persist(client: TestClient, tenants: TwoTenants) -> None:
    response = client.post(
        "/saved-views",
        json={"name": "My overdue", "filters": {"q": "refund", "open": True}},
        headers=tenants.handler_a.headers,
    )
    assert response.status_code == 201
    view = response.json()
    assert (
        client.get("/saved-views", headers=tenants.handler_a.headers).json()[0]["filters"]["q"]
        == "refund"
    )
    for other in [tenants.second_handler_a, tenants.handler_b]:
        assert client.get("/saved-views", headers=other.headers).json() == []
        assert client.delete(f"/saved-views/{view['id']}", headers=other.headers).status_code == 404
    assert (
        client.delete(f"/saved-views/{view['id']}", headers=tenants.handler_a.headers).status_code
        == 204
    )


def test_comments_and_handover_share_history(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)
    path = f"/cases/{case['id']}"
    assert (
        client.post(
            path + "/comments", json={"note": "Called customer"}, headers=tenants.handler_a.headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            path + "/handoff",
            json={
                "note": "Specialist review",
                "assigned_to_user_id": str(tenants.second_handler_a.id),
            },
            headers=tenants.handler_a.headers,
        ).status_code
        == 204
    )
    history = client.get(path + "/audit", headers=tenants.handler_a.headers).json()
    assert {event["action"] for event in history} >= {"comment_added", "case_handed_over"}
    assert client.get(path, headers=tenants.handler_a.headers).json()["assigned_to_user_id"] == str(
        tenants.second_handler_a.id
    )
    assert (
        client.post(
            path + "/comments", json={"note": " "}, headers=tenants.handler_a.headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            path + "/handoff",
            json={"note": "Bad", "assigned_to_user_id": str(tenants.handler_b.id)},
            headers=tenants.handler_a.headers,
        ).status_code
        == 422
    )
    for suffix in ["comments", "handoff"]:
        body = {"note": "Intruder"}
        if suffix == "handoff":
            body["assigned_to_user_id"] = str(tenants.handler_b.id)
        assert (
            client.post(
                path + "/" + suffix, json=body, headers=tenants.handler_b.headers
            ).status_code
            == 404
        )


def test_draft_approval_and_version_conflicts(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a, subject="Jane Doe refund", body="Email jane@example.com")
    path = f"/cases/{case['id']}/drafts"
    response = client.post(path, headers=tenants.handler_a.headers)
    assert response.status_code == 201
    draft = response.json()
    assert "Jane Doe" not in draft["body"]
    assert draft["provider"] == "fake" and draft["approved_at"] is None
    item = f"{path}/{draft['id']}"
    body = {"body": "Verified response", "version": 1, "approve": False}
    assert client.put(item, json=body, headers=tenants.handler_a.headers).status_code == 200
    assert client.put(item, json=body, headers=tenants.handler_a.headers).status_code == 409
    body.update(version=2, approve=True)
    approved = client.put(item, json=body, headers=tenants.handler_a.headers)
    assert approved.json()["approved_by_user_id"] == str(tenants.handler_a.id)
    assert (
        client.put(item, json={**body, "version": 3}, headers=tenants.handler_a.headers).status_code
        == 409
    )
    assert client.get(path, headers=tenants.handler_b.headers).status_code == 404
    assert client.post(path, headers=tenants.handler_b.headers).status_code == 404
    assert client.put(item, json=body, headers=tenants.handler_b.headers).status_code == 404


def test_a_draft_with_unfilled_placeholders_cannot_be_approved(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)
    path = f"/cases/{case['id']}/drafts"
    draft = client.post(path, headers=tenants.handler_a.headers).json()
    assert "[Handler:" in draft["body"]  # the offline template asks for the findings
    item = f"{path}/{draft['id']}"

    as_generated = {"body": draft["body"], "version": 1, "approve": True}
    refused = client.put(item, json=as_generated, headers=tenants.handler_a.headers)
    assert refused.status_code == 422
    assert "[Handler:" in refused.json()["detail"]

    privacy = {"body": "Dear [NAME_1], we have refunded the fee.", "version": 1, "approve": True}
    refused = client.put(item, json=privacy, headers=tenants.handler_a.headers)
    assert refused.status_code == 422 and "[NAME_1]" in refused.json()["detail"]

    # Saving work in progress is fine; only approval needs a finished letter.
    saved = client.put(item, json={**privacy, "approve": False}, headers=tenants.handler_a.headers)
    assert saved.status_code == 200 and saved.json()["approved_at"] is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Dear [NAME_1], about [CARD_1] and [NAME_1].", ["[NAME_1]", "[CARD_1]"]),
        ("[NI_NUMBER_2] [Handler: add findings]", ["[NI_NUMBER_2]", "[Handler: add findings]"]),
        ("We refunded £35 [as promised] on 3 [Oct].", []),
    ],
)
def test_unfilled_placeholders(body: str, expected: list[str]) -> None:
    assert unfilled_placeholders(body) == expected


def test_notices_only_show_handlers_own_cases(
    client: TestClient,
    tenants: TwoTenants,
    create_case: CreateCase,
    freeze_time: Callable[[datetime], None],
) -> None:
    own = create_case(tenants.handler_a)
    other = create_case(tenants.handler_a)
    foreign = create_case(tenants.handler_b)
    client.patch(
        f"/cases/{own['id']}/assignment",
        json={"assigned_to_user_id": str(tenants.handler_a.id)},
        headers=tenants.handler_a.headers,
    )
    freeze_time(datetime(2026, 11, 20, tzinfo=UTC))
    handler = client.get("/notifications", headers=tenants.handler_a.headers).json()
    lead = client.get("/notifications", headers=tenants.lead_a.headers).json()
    assert {notice["case_id"] for notice in handler} == {own["id"]}
    assert {notice["case_id"] for notice in lead} == {own["id"], other["id"]}
    assert all(notice["case_id"] != foreign["id"] for notice in lead)


def test_accounts_sessions_and_admin_permissions(
    client: TestClient, tenants: TwoTenants, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = db.get(User, tenants.lead_a.id)
    assert admin is not None
    admin.is_admin = True
    admin.password_hash = hash_password("correct password 123")
    db.commit()
    monkeypatch.setattr(get_settings(), "allow_demo_tokens", False)
    assert client.get("/me", headers=tenants.lead_a.headers).status_code == 401
    login = client.post(
        "/auth/login", json={"email": admin.email, "password": "correct password 123"}
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["token"]}
    account = {
        "email": "new@example.com",
        "display_name": "New colleague",
        "password": "new password 12345",
        "role": "handler",
    }
    created = client.post("/users", json=account, headers=headers)
    assert created.status_code == 201
    assert "password_hash" not in created.json()
    assert created.json()["tenant_id"] == str(tenants.lead_a.tenant_id)
    assert client.post("/users", json=account, headers=headers).status_code == 409
    token = client.post(
        "/auth/login", json={"email": account["email"], "password": account["password"]}
    ).json()["token"]
    handler_headers = {"Authorization": "Bearer " + token}
    assert (
        client.post(
            "/users", json={**account, "email": "second@example.com"}, headers=handler_headers
        ).status_code
        == 403
    )
    assert client.get("/dashboard", headers=handler_headers).status_code == 403
    assert client.post("/auth/logout", headers=handler_headers).status_code == 204
    assert client.get("/me", headers=handler_headers).status_code == 401
    session = db.scalar(select(LoginSession).where(LoginSession.user_id == admin.id))
    assert session is not None and session.token_hash != login.json()["token"]
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get("/me", headers=headers).status_code == 401


def test_failed_logins_lock_account(client: TestClient, tenants: TwoTenants, db: Session) -> None:
    user = db.get(User, tenants.handler_a.id)
    assert user is not None
    user.password_hash = hash_password("correct password 123")
    db.commit()
    for _ in range(5):
        assert (
            client.post("/auth/login", json={"email": user.email, "password": "wrong"}).status_code
            == 401
        )
    assert (
        client.post(
            "/auth/login", json={"email": user.email, "password": "correct password 123"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={"email": "missing@example.com", "password": "wrong"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("email", ["admin@example.test", "not an address"])
def test_login_answers_401_whatever_the_address_looks_like(client: TestClient, email: str) -> None:
    # Sign-in only looks the address up: no 422 with validation rules for a sign-in form to show.
    response = client.post("/auth/login", json={"email": email, "password": "wrong"})
    assert response.status_code == 401
