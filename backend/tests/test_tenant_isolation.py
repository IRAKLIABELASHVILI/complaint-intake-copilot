"""Tenant isolation (US-7). This file proves one tenant can never see or change another's data.

The first test and the repository tests are written for you as examples.
The tests marked TODO(Irakli) are yours: replace `pytest.skip(...)` with the test body.
Each one is a promise in docs/user-stories.md (US-7); together they are the evidence.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Case
from app.db.repositories import CaseRepository, CrossTenantWriteError
from tests.conftest import TwoTenants

CreateCase = Callable[..., dict[str, object]]


# --- Example (written for you): follow this Arrange / Act / Assert shape -----------------------


def test_user_cannot_get_another_tenants_case_by_id(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    # Arrange: tenant B has a case
    case_b = create_case(tenants.handler_b)

    # Act: a user of tenant A asks for it by its exact id
    response = client.get(f"/cases/{case_b['id']}", headers=tenants.handler_a.headers)

    # Assert: 404, the same answer as for an id that does not exist at all (US-7.4)
    assert response.status_code == 404


# --- Repository-level guards (written for you): they test your `_add` -------------------------


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


# --- Your tests: TODO(Irakli) -----------------------------------------------------------------


def test_list_cases_only_returns_own_tenants_cases(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.5: tenant A creates 2 cases, tenant B creates 1.
    A's list must have total == 2 and contain none of B's ids. And B's list must have total == 1.
    """
    pytest.skip("TODO(Irakli)")


def test_user_cannot_read_another_tenants_audit_trail(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.5: GET /cases/{B's case id}/audit as a user of tenant A returns 404."""
    pytest.skip("TODO(Irakli)")


def test_user_cannot_assign_another_tenants_case(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.5: PATCH /cases/{B's case id}/assignment as a user of tenant A returns 404,
    AND the case in tenant B is unchanged (check it as handler_b afterwards)."""
    pytest.skip("TODO(Irakli)")


def test_user_cannot_assign_own_case_to_another_tenants_user(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """A case of tenant A cannot be assigned to handler_b (a user of tenant B).
    Expect 422, and the case stays unassigned."""
    pytest.skip("TODO(Irakli)")


def test_tenant_cannot_be_chosen_by_the_client(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-7.2: the tenant comes only from the token.
    Hint: try to create a case with "tenant_id": <B's tenant id> in the JSON body, as handler_a.
    What status code do you expect, and why? (Look at CaseCreate's model_config.)
    Then also prove that tenant B still has zero cases."""
    pytest.skip("TODO(Irakli)")


def test_same_external_message_id_in_two_tenants_creates_two_cases(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """Idempotency is per tenant: the same Message-ID sent to tenant A and tenant B must create
    two separate cases (both 201), not return A's case to B."""
    pytest.skip("TODO(Irakli)")
