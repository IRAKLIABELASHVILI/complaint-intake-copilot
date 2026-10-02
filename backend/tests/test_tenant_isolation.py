"""Tenant isolation (US-7). This file proves one tenant can never see or change another's data.

Each test is a promise in docs/user-stories.md (US-7); together they are the evidence.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Case
from app.db.repositories import CaseRepository, CrossTenantWriteError
from tests.conftest import TwoTenants, complaint_payload

CreateCase = Callable[..., dict[str, object]]


# --- Reading by id -----------------------------------------------------------------------------


def test_user_cannot_get_another_tenants_case_by_id(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    # Arrange: tenant B has a case
    case_b = create_case(tenants.handler_b)

    # Act: a user of tenant A asks for it by its exact id
    response = client.get(f"/cases/{case_b['id']}", headers=tenants.handler_a.headers)

    # Assert: 404, the same answer as for an id that does not exist at all (US-7.4)
    assert response.status_code == 404


# --- Repository-level guards: they test `_add` -------------------------------------------------


def _case(tenant_id: uuid.UUID | None) -> Case:
    case = Case(
        id=uuid.uuid4(),
        reference=f"CMP-TEST-{uuid.uuid4().hex[:8]}",
        subject="s",
        body="b",
        sender_email="x@example.com",
        received_at=datetime.now(UTC),
    )
    if tenant_id is not None:
        case.tenant_id = tenant_id
    return case


def test_add_sets_tenant_id_when_missing(db: Session, tenants: TwoTenants) -> None:
    repository = CaseRepository(db, tenants.handler_a.tenant_id)

    saved = repository.add(_case(tenant_id=None))

    assert saved.tenant_id == tenants.handler_a.tenant_id


def test_add_refuses_an_entity_from_another_tenant(db: Session, tenants: TwoTenants) -> None:
    repository = CaseRepository(db, tenants.handler_a.tenant_id)

    with pytest.raises(CrossTenantWriteError):
        repository.add(_case(tenant_id=tenants.handler_b.tenant_id))


def test_repository_get_does_not_return_another_tenants_case(
    db: Session, tenants: TwoTenants
) -> None:
    case_b = CaseRepository(db, tenants.handler_b.tenant_id).add(_case(tenant_id=None))
    db.commit()

    assert CaseRepository(db, tenants.handler_a.tenant_id).get(case_b.id) is None
    assert CaseRepository(db, tenants.handler_b.tenant_id).get(case_b.id) is not None


# --- API-level isolation (US-7.2, US-7.5) ------------------------------------------------------


def test_list_cases_only_returns_own_tenants_cases(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.5: each tenant's list contains only its own cases, and the totals match."""
    # Arrange: tenant A has 2 cases, tenant B has 1
    a_ids = {create_case(tenants.handler_a)["id"], create_case(tenants.handler_a)["id"]}
    case_b = create_case(tenants.handler_b)

    # Act
    list_a = client.get("/cases", headers=tenants.handler_a.headers).json()
    list_b = client.get("/cases", headers=tenants.handler_b.headers).json()

    # Assert
    assert list_a["total"] == 2
    assert {item["id"] for item in list_a["items"]} == a_ids
    assert list_b["total"] == 1
    assert [item["id"] for item in list_b["items"]] == [case_b["id"]]


def test_user_cannot_read_another_tenants_audit_trail(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.5: GET /cases/{B's case id}/audit as a user of tenant A returns 404."""
    case_b = create_case(tenants.handler_b)

    response = client.get(f"/cases/{case_b['id']}/audit", headers=tenants.handler_a.headers)

    assert response.status_code == 404


def test_user_cannot_assign_another_tenants_case(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.5: assigning B's case as a user of tenant A returns 404, and B's case is unchanged."""
    case_b = create_case(tenants.handler_b)

    response = client.patch(
        f"/cases/{case_b['id']}/assignment",
        json={"assigned_to_user_id": str(tenants.handler_a.id)},
        headers=tenants.handler_a.headers,
    )

    assert response.status_code == 404
    after = client.get(f"/cases/{case_b['id']}", headers=tenants.handler_b.headers).json()
    assert after["assigned_to_user_id"] is None
    assert after["updated_at"] == case_b["updated_at"]


def test_user_cannot_assign_own_case_to_another_tenants_user(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """A case of tenant A cannot be assigned to handler_b (a user of tenant B): 422, and the
    case stays unassigned."""
    case_a = create_case(tenants.handler_a)

    response = client.patch(
        f"/cases/{case_a['id']}/assignment",
        json={"assigned_to_user_id": str(tenants.handler_b.id)},
        headers=tenants.handler_a.headers,
    )

    assert response.status_code == 422
    after = client.get(f"/cases/{case_a['id']}", headers=tenants.handler_a.headers).json()
    assert after["assigned_to_user_id"] is None


def test_tenant_cannot_be_chosen_by_the_client(client: TestClient, tenants: TwoTenants) -> None:
    """US-7.2: the tenant comes only from the token. CaseCreate forbids unknown fields
    (extra="forbid"), so a client-supplied tenant_id is rejected with 422, not ignored."""
    payload = complaint_payload(tenant_id=str(tenants.handler_b.tenant_id))

    response = client.post("/cases", json=payload, headers=tenants.handler_a.headers)

    assert response.status_code == 422
    assert client.get("/cases", headers=tenants.handler_b.headers).json()["total"] == 0
    assert client.get("/cases", headers=tenants.handler_a.headers).json()["total"] == 0


def test_same_external_message_id_in_two_tenants_creates_two_cases(
    client: TestClient, tenants: TwoTenants
) -> None:
    """Idempotency is per tenant: the same Message-ID sent to tenant A and tenant B creates
    two separate cases (both 201), and B never gets A's case back."""
    payload = complaint_payload(external_message_id="<shared-id@mail.example.com>")

    response_a = client.post("/cases", json=payload, headers=tenants.handler_a.headers)
    response_b = client.post("/cases", json=payload, headers=tenants.handler_b.headers)

    assert response_a.status_code == 201
    assert response_b.status_code == 201
    assert response_a.json()["id"] != response_b.json()["id"]
