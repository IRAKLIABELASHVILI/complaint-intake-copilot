"""The team lead dashboard (US-5) and the case list filters its numbers link to (US-5.4).

One realistic tenant is built through the real API and the real worker, with the clock frozen on
Monday 2026-09-21 at 10:00 UK time, then every number is checked against what a person would
count by hand.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Case, CaseAnalysis
from app.domain.enums import AnalysisStatus, CaseStatus, Category, ResolutionType
from tests.conftest import SeededUser, TwoTenants
from tests.fakes import model_answer

Json = dict[str, Any]
CreateCase = Callable[..., Json]

NOW = datetime(2026, 9, 21, 9, tzinfo=UTC)  # Monday 10:00 BST
BEREAVEMENT = "My husband passed away last month."
ANXIETY = "This has made my anxiety much worse."
BODY = f"{BEREAVEMENT} {ANXIETY} You charged me a late fee of £35 anyway."


def answer(category: str, *indicators: tuple[str, str]) -> str:
    return model_answer(
        category=category,
        vulnerability_indicators=[
            {"type": kind, "evidence_quote": quote} for kind, quote in indicators
        ],
    )


def put(client: TestClient, user: SeededUser, path: str, body: Json) -> Json:
    response = client.put(path, json=body, headers=user.headers)
    assert response.status_code == 200, response.text
    result: Json = response.json()
    return result


@pytest.fixture
def busy_tenant(
    client: TestClient,
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
    analyse: Callable[..., None],
    freeze_time: Callable[[datetime], None],
) -> TwoTenants:
    """Tenant A with one case for each situation the dashboard must tell apart."""
    handler = tenants.handler_a

    def received(when: str) -> Json:
        return create_case(handler, received_at=when, body=BODY)

    # SRC due Tuesday 22nd 17:00: one business day left -> SRC at risk.
    # AI: fees and charges, bereavement + mental health. The handler confirms bereavement,
    # rejects mental health, and adds a second bereavement quote: still ONE bereaved case.
    at_risk = received("2026-09-17T10:00:00+01:00")
    analyse(
        handler,
        at_risk,
        answer("fees_and_charges", ("bereavement", BEREAVEMENT), ("mental_health", ANXIETY)),
    )
    indicators = client.get(f"/cases/{at_risk['id']}", headers=handler.headers).json()[
        "vulnerability_indicators"
    ]
    for indicator in indicators:
        decision = "confirmed" if indicator["indicator_type"] == "bereavement" else "rejected"
        path = f"/cases/{at_risk['id']}/vulnerability-indicators/{indicator['id']}/decision"
        put(client, handler, path, {"decision": decision})
    response = client.post(
        f"/cases/{at_risk['id']}/vulnerability-indicators",
        json={"indicator_type": "bereavement", "evidence_quote": "passed away last month"},
        headers=handler.headers,
    )
    assert response.status_code == 201, response.text

    # Received this morning: SRC Thursday, three business days left -> not at risk.
    # The AI said service quality; the handler overrode it to fraud and scams.
    fresh = received("2026-09-21T08:00:00+01:00")
    analyse(handler, fresh, answer("service_quality"))
    put(client, handler, f"/cases/{fresh['id']}/category", {"category": "fraud_and_scams"})

    # SRC was Thursday 17th -> SRC overdue. Never analysed (still "new") -> uncategorised.
    received("2026-09-14T09:30:00+01:00")

    # Final response due Tuesday 22nd 23:59 -> final response at risk (and SRC long missed).
    # The analysis failed twice -> needs human review, no suggestion -> uncategorised.
    final_at_risk = received("2026-07-28T10:00:00+01:00")
    analyse(handler, final_at_risk, "not json", "still not json")

    # Final response was due Monday 14th -> a breach. The AI suggestion was accepted.
    # Its bereavement indicator is still pending, so it is not counted.
    breached = received("2026-07-20T10:00:00+01:00")
    analyse(handler, breached, answer("fees_and_charges", ("bereavement", BEREAVEMENT)))
    put(client, handler, f"/cases/{breached['id']}/category", {"category": "fees_and_charges"})

    # Resolved: counted nowhere, even though its deadlines are long gone.
    resolved = received("2026-07-20T11:00:00+01:00")
    case = db.get_one(Case, uuid.UUID(resolved["id"]))
    case.status = CaseStatus.RESOLVED
    case.resolved_at = datetime(2026, 8, 1, tzinfo=UTC)
    case.resolution_type = ResolutionType.FINAL_RESPONSE
    db.commit()

    # Another tenant's overdue case: never seen by tenant A (US-5.3).
    create_case(tenants.handler_b, received_at="2026-07-20T10:00:00+01:00")

    freeze_time(NOW)
    return tenants


def dashboard(client: TestClient, user: SeededUser) -> Json:
    response = client.get("/dashboard", headers=user.headers)
    assert response.status_code == 200, response.text
    body: Json = response.json()
    return body


def cases(client: TestClient, user: SeededUser, query: dict[str, str]) -> Json:
    response = client.get("/cases", params=query, headers=user.headers)
    assert response.status_code == 200, response.text
    body: Json = response.json()
    return body


# --- What a team lead sees (US-5.1) --------------------------------------------------------------


def test_deadline_counts(client: TestClient, busy_tenant: TwoTenants) -> None:
    body = dashboard(client, busy_tenant.lead_a)

    assert body["open_cases"] == 5
    assert body["at_risk_business_days"] == 2
    assert body["summary_resolution"] == {"at_risk": 1, "overdue": 3}
    assert body["final_response"] == {"at_risk": 1, "overdue": 1}


def test_category_counts_keep_decided_and_suggested_apart(
    client: TestClient, busy_tenant: TwoTenants
) -> None:
    body = dashboard(client, busy_tenant.lead_a)

    by_category = {
        row["category"]: (row["decided"], row["suggested"]) for row in body["categories"]
    }
    assert by_category["fees_and_charges"] == (1, 1)
    assert by_category["fraud_and_scams"] == (1, 0)
    assert by_category["service_quality"] == (0, 0)  # the overridden suggestion is gone
    assert len(by_category) == 9  # every category, zeros included
    assert body["uncategorised"] == 2


def test_vulnerability_counts_confirmed_indicators_only_once_per_case(
    client: TestClient, busy_tenant: TwoTenants
) -> None:
    body = dashboard(client, busy_tenant.lead_a)

    by_type = {row["indicator_type"]: row for row in body["vulnerabilities"]}
    assert by_type["bereavement"] == {
        "indicator_type": "bereavement",
        "driver": "life_events",
        "cases": 1,
    }
    assert by_type["mental_health"]["cases"] == 0  # rejected
    assert sum(row["cases"] for row in body["vulnerabilities"]) == 1
    assert len(by_type) == 8


# --- Every number opens the matching cases (US-5.4) ---------------------------------------------


def _links(body: Json) -> list[tuple[int, dict[str, str]]]:
    """Each dashboard number with the list query the web app links it to."""
    links: list[tuple[int, dict[str, str]]] = [(body["open_cases"], {"open": "true"})]
    for kind in ("summary_resolution", "final_response"):
        deadline = "src" if kind == "summary_resolution" else kind
        for risk in ("at_risk", "overdue"):
            query = {"open": "true", "deadline": deadline, "deadline_risk": risk}
            links.append((body[kind][risk], query))
    for row in body["categories"]:
        links.append((row["decided"], {"open": "true", "final_category": row["category"]}))
        links.append((row["suggested"], {"open": "true", "suggested_category": row["category"]}))
    links.append((body["uncategorised"], {"open": "true", "uncategorised": "true"}))
    for row in body["vulnerabilities"]:
        links.append((row["cases"], {"open": "true", "vulnerability": row["indicator_type"]}))
    return links


def test_every_number_matches_the_list_it_links_to(
    client: TestClient, busy_tenant: TwoTenants
) -> None:
    lead = busy_tenant.lead_a
    for count, query in _links(dashboard(client, lead)):
        assert cases(client, lead, query)["total"] == count, query


def test_deadline_filters_return_the_right_cases(
    client: TestClient, busy_tenant: TwoTenants
) -> None:
    query = {"deadline": "final_response", "deadline_risk": "overdue"}
    [breached] = cases(client, busy_tenant.lead_a, query)["items"]

    final_response = breached["deadline_tracking"]["final_response"]
    assert final_response["is_overdue"] is True
    assert breached["received_at"] == "2026-07-20T09:00:00Z"  # not the resolved one at 10:00


def test_filters_combine_with_and(client: TestClient, busy_tenant: TwoTenants) -> None:
    query = {
        "suggested_category": "fees_and_charges",
        "deadline": "src",
        "deadline_risk": "at_risk",
    }
    assert cases(client, busy_tenant.handler_a, query)["total"] == 1

    query = {"final_category": "fees_and_charges", "deadline": "src", "deadline_risk": "at_risk"}
    assert cases(client, busy_tenant.handler_a, query)["total"] == 0


def test_without_open_the_list_still_includes_resolved_cases(
    client: TestClient, busy_tenant: TwoTenants
) -> None:
    assert cases(client, busy_tenant.lead_a, {})["total"] == 6
    assert cases(client, busy_tenant.lead_a, {"open": "true"})["total"] == 5


def test_deadline_filter_needs_both_parts(client: TestClient, tenants: TwoTenants) -> None:
    response = client.get("/cases?deadline=src", headers=tenants.handler_a.headers)

    assert response.status_code == 422


# --- Who may see it (US-5.2, US-5.3) -----------------------------------------------------------


def test_a_handler_gets_403(client: TestClient, tenants: TwoTenants) -> None:
    response = client.get("/dashboard", headers=tenants.handler_a.headers)

    assert response.status_code == 403


def test_without_a_token_the_answer_is_401(client: TestClient) -> None:
    assert client.get("/dashboard").status_code == 401


def test_an_empty_tenant_has_an_all_zero_dashboard(
    client: TestClient, tenants: TwoTenants, freeze_time: Callable[[datetime], None]
) -> None:
    freeze_time(NOW)

    body = dashboard(client, tenants.lead_a)

    assert body["open_cases"] == 0
    assert body["summary_resolution"] == {"at_risk": 0, "overdue": 0}
    assert all(row["decided"] == row["suggested"] == 0 for row in body["categories"])


# --- When the calendar cannot answer -------------------------------------------------------------


def test_out_of_date_bank_holidays_give_503_not_a_guess(
    client: TestClient, tenants: TwoTenants, freeze_time: Callable[[datetime], None]
) -> None:
    freeze_time(datetime(2099, 6, 1, tzinfo=UTC))

    dashboard_response = client.get("/dashboard", headers=tenants.lead_a.headers)
    at_risk = {"deadline": "src", "deadline_risk": "at_risk"}
    list_response = client.get("/cases", params=at_risk, headers=tenants.lead_a.headers)

    assert dashboard_response.status_code == 503
    assert list_response.status_code == 503


def test_the_open_filter_has_one_name_only(client: TestClient, busy_tenant: TwoTenants) -> None:
    """The Python name `open_only` is not a second, undocumented query parameter."""
    assert cases(client, busy_tenant.lead_a, {"open_only": "true"})["total"] == 6  # ignored
    assert cases(client, busy_tenant.lead_a, {"open": "true"})["total"] == 5


def test_only_the_newest_completed_analysis_counts_as_the_suggestion(
    client: TestClient,
    db: Session,
    tenants: TwoTenants,
    create_case: CreateCase,
    analyse: Callable[..., None],
) -> None:
    """A re-analysed case keeps its old analysis as history; only the newest one suggests."""
    case = create_case(tenants.handler_a)
    analyse(tenants.handler_a, case, answer("fees_and_charges"))
    db.add(
        CaseAnalysis(
            tenant_id=tenants.handler_a.tenant_id,
            case_id=uuid.UUID(case["id"]),
            attempt=1,
            status=AnalysisStatus.COMPLETED,
            provider="scripted",
            model="scripted-v1",
            suggested_category=Category.SERVICE_QUALITY,
            created_at=datetime.now(UTC) + timedelta(minutes=1),
        )
    )
    db.commit()

    body = dashboard(client, tenants.lead_a)

    suggested = {row["category"]: row["suggested"] for row in body["categories"]}
    assert suggested["service_quality"] == 1
    assert suggested["fees_and_charges"] == 0
    query = {"suggested_category": "fees_and_charges"}
    assert cases(client, tenants.lead_a, query)["total"] == 0


def test_assignment_workload_and_filters(
    client: TestClient, db: Session, tenants: TwoTenants, create_case: CreateCase
) -> None:
    owned = create_case(tenants.handler_a)
    create_case(tenants.handler_a)
    create_case(tenants.handler_b)
    row = db.get_one(Case, uuid.UUID(owned["id"]))
    row.assigned_to_user_id = tenants.handler_a.id
    db.commit()
    body = dashboard(client, tenants.lead_a)
    counts = {item["user_id"]: item["open_cases"] for item in body["assignments"]}
    assert counts == {str(tenants.handler_a.id): 1, None: 1}
    assert (
        cases(client, tenants.lead_a, {"assigned_to_user_id": str(tenants.handler_a.id)})["total"]
        == 1
    )
    assert cases(client, tenants.lead_a, {"unassigned": "true"})["total"] == 1
    assert (
        cases(client, tenants.handler_b, {"assigned_to_user_id": str(tenants.handler_a.id)})[
            "total"
        ]
        == 0
    )
    row.status = CaseStatus.RESOLVED
    db.commit()
    assert dashboard(client, tenants.lead_a)["assignments"] == [
        {"user_id": None, "display_name": "Unassigned", "open_cases": 1}
    ]


def test_close_case_records_outcome_and_removes_open_workload(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase, analyse: Callable[..., None]
) -> None:
    case = create_case(tenants.handler_a)
    path = f"/cases/{case['id']}/resolve"
    payload = {
        "resolution_type": "final_response",
        "note": "Refund completed and outcome explained.",
    }
    assert client.post(path, json=payload, headers=tenants.handler_b.headers).status_code == 404
    assert client.post(path, json=payload, headers=tenants.handler_a.headers).status_code == 409
    analyse(tenants.handler_a, case, answer("fees_and_charges"))
    assert (
        client.post(
            path, json={**payload, "note": "   "}, headers=tenants.handler_a.headers
        ).status_code
        == 422
    )
    response = client.post(path, json=payload, headers=tenants.handler_a.headers)
    assert response.status_code == 200
    closed = response.json()
    assert closed["status"] == "resolved"
    assert closed["resolved_at"] is not None
    assert closed["resolution_type"] == "final_response"
    assert closed["deadline_tracking"]["src"] is None
    assert dashboard(client, tenants.lead_a)["open_cases"] == 0
    repeat = client.post(path, json=payload, headers=tenants.handler_a.headers)
    assert repeat.json()["resolved_at"] == closed["resolved_at"]
    audit = client.get(f"/cases/{case['id']}/audit", headers=tenants.handler_a.headers).json()
    events = [item for item in audit if item["action"] == "case_resolved"]
    assert len(events) == 1
    assert events[0]["new_value"]["note"] == payload["note"]
