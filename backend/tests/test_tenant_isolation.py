"""Tenant isolation (US-7). This file proves one tenant can never see or change another's data.

Each test is a promise in docs/user-stories.md (US-7); together they are the evidence.
"""

import ast
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Case, Tenant
from app.db.repositories import CaseRepository, CrossTenantWriteError
from app.seed import seed
from tests.conftest import TwoTenants, complaint_payload
from tests.fakes import model_answer

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


def test_dashboard_and_its_filters_count_only_own_tenants_cases(
    client: TestClient,
    tenants: TwoTenants,
    create_case: CreateCase,
    analyse: Callable[..., None],
) -> None:
    """US-5.3, US-7.5: tenant B's overdue, categorised, vulnerable case shows up nowhere for A."""
    # Arrange: tenant B has an overdue case with a suggestion and a confirmed indicator
    quote = "My husband passed away last month."
    case_b = create_case(tenants.handler_b, received_at="2026-07-20T10:00:00+01:00", body=quote)
    answer = model_answer(
        vulnerability_indicators=[{"type": "bereavement", "evidence_quote": quote}]
    )
    analyse(tenants.handler_b, case_b, answer)
    case_b = client.get(f"/cases/{case_b['id']}", headers=tenants.handler_b.headers).json()
    indicator_id = case_b["vulnerability_indicators"][0]["id"]
    decision = client.put(
        f"/cases/{case_b['id']}/vulnerability-indicators/{indicator_id}/decision",
        json={"decision": "confirmed"},
        headers=tenants.handler_b.headers,
    )
    assert decision.status_code == 200

    # Act
    dashboard = client.get("/dashboard", headers=tenants.lead_a.headers).json()
    filtered = [
        client.get("/cases", params=query, headers=tenants.lead_a.headers).json()["total"]
        for query in (
            {"suggested_category": "fees_and_charges"},
            {"vulnerability": "bereavement"},
            {"deadline": "final_response", "deadline_risk": "overdue"},
        )
    ]

    # Assert
    assert dashboard["open_cases"] == 0
    assert dashboard["final_response"]["overdue"] == 0
    assert all(row["suggested"] == 0 for row in dashboard["categories"])
    assert all(row["cases"] == 0 for row in dashboard["vulnerabilities"])
    assert filtered == [0, 0, 0]


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


# --- The schema and the code base (US-7.1, US-7.3) ---------------------------------------------

# Tables that are not owned by a tenant, and why. A new table must be added here or get tenant_id.
NOT_TENANT_OWNED = {
    "tenants": "the tenants themselves",
    "outbox_messages": "infrastructure; the tenant id travels inside the payload",
    "processed_messages": "infrastructure; only message ids the worker has handled",
}


def test_every_tenant_owned_table_has_an_indexed_non_null_tenant_id() -> None:
    """US-7.1. Read from the models, which `alembic check` in CI proves match the migrations."""
    for table in Base.metadata.sorted_tables:
        if table.name in NOT_TENANT_OWNED:
            assert "tenant_id" not in table.columns, table.name
            continue
        assert "tenant_id" in table.columns, f"{table.name} has no tenant_id"
        assert not table.columns["tenant_id"].nullable, table.name
        leading_columns = [next(iter(index.columns)).name for index in table.indexes]
        assert "tenant_id" in leading_columns, f"{table.name}.tenant_id has no index"


APP_DIR = Path(__file__).resolve().parent.parent / "app"
TENANT_FILTER_HOME = APP_DIR / "db" / "repositories.py"


def _filters_on_tenant_id(node: ast.expr) -> bool:
    """`X.tenant_id == ...` / `... == X.tenant_id`, or `.filter_by(tenant_id=...)`."""
    if isinstance(node, ast.Compare):
        sides = [node.left, *node.comparators]
        return any(isinstance(side, ast.Attribute) and side.attr == "tenant_id" for side in sides)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "filter_by" and any(
            keyword.arg == "tenant_id" for keyword in node.keywords
        )
    return False


def test_tenant_filtering_happens_only_in_the_repositories() -> None:
    """US-7.3: endpoints, services and the worker never write their own tenant filter. They get
    a repository built for the user's tenant, and the repository adds the filter."""
    offenders = [
        f"{path.relative_to(APP_DIR)}:{node.lineno}"
        for path in APP_DIR.rglob("*.py")
        if path != TENANT_FILTER_HOME
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.expr) and _filters_on_tenant_id(node)
    ]

    assert offenders == []


# --- Demo data (US-7.7) ------------------------------------------------------------------------


def test_the_demo_data_has_two_tenants_with_cases_and_can_be_loaded_twice(db: Session) -> None:
    seed(db)
    seed(db)  # safe to run again: an existing tenant is skipped

    cases_per_tenant = dict(
        db.execute(select(Case.tenant_id, func.count()).group_by(Case.tenant_id)).all()
    )
    assert db.scalar(select(func.count()).select_from(Tenant)) == 2
    assert len(cases_per_tenant) == 2
    assert all(count > 0 for count in cases_per_tenant.values())
