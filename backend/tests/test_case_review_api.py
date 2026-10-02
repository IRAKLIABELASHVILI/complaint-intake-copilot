"""Reviewing AI suggestions and recording decisions through the API (US-2, US-3)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.messaging.messages import AnalysisJob
from app.worker.analysis_job_handler import AnalysisJobHandler
from app.worker.case_analyser import INVALID_TWICE, CaseAnalyser
from tests.conftest import SeededUser, TwoTenants
from tests.fakes import ScriptedProvider, model_answer

CreateCase = Callable[..., dict[str, object]]
Json = dict[str, Any]  # API responses, as parsed JSON

BODY = "My husband passed away last month. You charged me a late fee of £35 anyway."
QUOTE = "My husband passed away last month."
SUGGESTION = model_answer(
    category="fees_and_charges",
    priority="medium",
    summary="Late fee after a bereavement.",
    vulnerability_indicators=[{"type": "bereavement", "evidence_quote": QUOTE}],
)


@pytest.fixture
def analysed_case(
    session_factory: sessionmaker[Session], create_case: CreateCase
) -> Callable[..., Json]:
    """Create a case as `user`, then run the worker on it with the given model answers."""

    def _analysed(user: SeededUser, *answers: str) -> Json:
        case = create_case(user, body=BODY)
        provider = ScriptedProvider(list(answers or [SUGGESTION]))
        job = AnalysisJob(
            message_id=uuid.uuid4(),
            case_id=uuid.UUID(str(case["id"])),
            tenant_id=user.tenant_id,
            correlation_id="review-test",
        )
        AnalysisJobHandler(session_factory, CaseAnalyser(provider)).handle(job)
        return case

    return _analysed


def get(client: TestClient, case: Json, user: SeededUser) -> Json:
    response = client.get(f"/cases/{case['id']}", headers=user.headers)
    assert response.status_code == 200, response.text
    body: Json = response.json()
    return body


def audit(client: TestClient, case: Json, user: SeededUser) -> list[Json]:
    events: list[Json] = client.get(f"/cases/{case['id']}/audit", headers=user.headers).json()
    return events


def put(
    client: TestClient, case: Json, path: str, body: Json, user: SeededUser
) -> tuple[int, Json]:
    response = client.put(f"/cases/{case['id']}{path}", json=body, headers=user.headers)
    return response.status_code, response.json()


# --- Seeing suggestions (US-2) -------------------------------------------------------------------


def test_no_suggestions_are_shown_before_the_analysis(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    """US-2.4: the case is usable (deadlines) but shows no suggestions while new / analysing."""
    case = get(client, create_case(tenants.handler_a, body=BODY), tenants.handler_a)

    assert case["suggestion"] is None
    assert case["vulnerability_indicators"] == []
    assert case["deadline_tracking"] is not None


def test_the_analysed_case_shows_suggestions_with_evidence_and_provenance(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = get(client, analysed_case(tenants.handler_a), tenants.handler_a)

    assert case["status"] == "awaiting_review"
    suggestion = case["suggestion"]
    assert suggestion["suggested_category"] == "fees_and_charges"
    assert suggestion["suggested_priority"] == "high"  # lifted: vulnerability (US-2.6)
    assert suggestion["summary"] == "Late fee after a bereavement."
    assert (suggestion["provider"], suggestion["model"]) == ("scripted", "scripted-v1")  # US-2.7
    [indicator] = case["vulnerability_indicators"]
    assert indicator["indicator_type"] == "bereavement"
    assert indicator["driver"] == "life_events"
    assert indicator["evidence_quote"] == QUOTE
    assert (indicator["source"], indicator["decision"]) == ("ai", "pending")
    assert case["final_category"] is None  # nothing is final until a person decides


def test_a_failed_analysis_shows_why_and_no_suggestion(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = get(client, analysed_case(tenants.handler_a, "bad", "still bad"), tenants.handler_a)

    assert case["status"] == "needs_human_review"
    assert case["review_reason"] == INVALID_TWICE
    assert case["suggestion"] is None


# --- Category and priority decisions (US-3.1 - 3.3) ----------------------------------------------


def test_accepting_the_suggested_category(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)

    code, body = put(client, case, "/category", {"category": "fees_and_charges"}, tenants.handler_a)

    assert code == 200
    assert body["final_category"] == "fees_and_charges"
    assert body["status"] == "in_progress"  # a person has started on it
    decision = next(e for e in audit(client, case, tenants.handler_a) if e["field"] == "category")
    assert decision["source"] == "accepted_suggestion"
    assert (decision["old_value"], decision["new_value"]) == (None, "fees_and_charges")
    assert decision["actor_user_id"] == str(tenants.handler_a.id)


def test_overriding_the_category_keeps_the_original_suggestion(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)

    _, body = put(client, case, "/category", {"category": "service_quality"}, tenants.handler_a)

    assert body["final_category"] == "service_quality"
    suggestion = body["suggestion"]
    assert suggestion["suggested_category"] == "fees_and_charges"  # not overwritten (US-3.2)
    decision = next(e for e in audit(client, case, tenants.handler_a) if e["field"] == "category")
    assert decision["source"] == "override"


def test_priority_follows_the_same_rules(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)

    put(client, case, "/priority", {"priority": "high"}, tenants.handler_a)  # = suggestion
    put(client, case, "/priority", {"priority": "urgent"}, tenants.handler_a)  # override

    sources = [
        e["source"] for e in audit(client, case, tenants.handler_a) if e["field"] == "priority"
    ]
    assert sorted(sources) == ["accepted_suggestion", "override"]
    assert get(client, case, tenants.handler_a)["final_priority"] == "urgent"


def test_without_a_suggestion_the_decision_is_the_handlers_own(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a, "bad", "still bad")

    code, body = put(client, case, "/category", {"category": "other"}, tenants.handler_a)

    assert (code, body["status"]) == (200, "in_progress")
    decision = next(e for e in audit(client, case, tenants.handler_a) if e["field"] == "category")
    assert decision["source"] == "handler"


def test_repeating_a_decision_records_nothing_new(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)
    put(client, case, "/category", {"category": "other"}, tenants.handler_a)
    events_before = len(audit(client, case, tenants.handler_a))

    put(client, case, "/category", {"category": "other"}, tenants.handler_a)

    assert len(audit(client, case, tenants.handler_a)) == events_before


def test_decisions_are_refused_while_the_case_is_not_analysed(
    client: TestClient, tenants: TwoTenants, create_case: CreateCase
) -> None:
    case = create_case(tenants.handler_a)

    code, body = put(client, case, "/category", {"category": "other"}, tenants.handler_a)

    assert code == 409
    assert "new" in str(body["detail"])


def test_an_unknown_category_is_rejected(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)

    code, _ = put(client, case, "/category", {"category": "parking"}, tenants.handler_a)

    assert code == 422


# --- Vulnerability indicators (US-3.4, 3.5) ------------------------------------------------------


def indicator_id(client: TestClient, case: Json, user: SeededUser) -> str:
    [indicator] = get(client, case, user)["vulnerability_indicators"]
    return str(indicator["id"])


@pytest.mark.parametrize("decision", ["confirmed", "rejected"])
def test_an_indicator_decision_is_stored_with_who_and_when(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json], decision: str
) -> None:
    case = analysed_case(tenants.handler_a)
    path = f"/vulnerability-indicators/{indicator_id(client, case, tenants.handler_a)}/decision"

    code, body = put(client, case, path, {"decision": decision}, tenants.handler_a)

    assert code == 200
    [indicator] = body["vulnerability_indicators"]
    assert indicator["decision"] == decision  # a rejected one stays visible as rejected
    assert indicator["decided_by_user_id"] == str(tenants.handler_a.id)
    assert indicator["decided_at"] is not None
    event = next(
        e for e in audit(client, case, tenants.handler_a) if e["action"] == "indicator_decided"
    )
    assert event["new_value"] == {"id": indicator["id"], "decision": decision}


def test_pending_is_not_a_decision(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)
    path = f"/vulnerability-indicators/{indicator_id(client, case, tenants.handler_a)}/decision"

    code, _ = put(client, case, path, {"decision": "pending"}, tenants.handler_a)

    assert code == 422


def test_an_indicator_of_another_case_is_not_found(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case_1 = analysed_case(tenants.handler_a)
    case_2 = analysed_case(tenants.handler_a)
    path = f"/vulnerability-indicators/{indicator_id(client, case_1, tenants.handler_a)}/decision"

    code, _ = put(client, case_2, path, {"decision": "confirmed"}, tenants.handler_a)

    assert code == 404


def test_a_handler_can_add_an_indicator_the_ai_missed(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)

    response = client.post(
        f"/cases/{case['id']}/vulnerability-indicators",
        json={"indicator_type": "financial_hardship", "evidence_quote": "late fee of £35"},
        headers=tenants.handler_a.headers,
    )

    assert response.status_code == 201
    added = [i for i in response.json()["vulnerability_indicators"] if i["source"] == "handler"]
    assert [(i["indicator_type"], i["driver"], i["decision"]) for i in added] == [
        ("financial_hardship", "resilience", "confirmed")
    ]


def test_a_handlers_evidence_must_be_in_the_complaint_too(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)

    response = client.post(
        f"/cases/{case['id']}/vulnerability-indicators",
        json={"indicator_type": "job_loss", "evidence_quote": "I lost my job"},
        headers=tenants.handler_a.headers,
    )

    assert response.status_code == 422
    assert len(get(client, case, tenants.handler_a)["vulnerability_indicators"]) == 1


# --- Tenant isolation and audit integrity --------------------------------------------------------


def test_another_tenant_cannot_decide_anything(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)
    path = f"/vulnerability-indicators/{indicator_id(client, case, tenants.handler_a)}/decision"

    assert put(client, case, "/category", {"category": "other"}, tenants.handler_b)[0] == 404
    assert put(client, case, "/priority", {"priority": "low"}, tenants.handler_b)[0] == 404
    assert put(client, case, path, {"decision": "rejected"}, tenants.handler_b)[0] == 404
    unchanged = get(client, case, tenants.handler_a)
    assert (unchanged["final_category"], unchanged["status"]) == (None, "awaiting_review")


def test_the_audit_trail_is_newest_first_and_cannot_be_changed(
    client: TestClient, tenants: TwoTenants, analysed_case: Callable[..., Json]
) -> None:
    case = analysed_case(tenants.handler_a)
    put(client, case, "/category", {"category": "other"}, tenants.handler_a)

    events = audit(client, case, tenants.handler_a)

    times = [str(e["created_at"]) for e in events]
    assert times == sorted(times, reverse=True)  # US-3.8
    for method in ("put", "patch", "delete"):  # US-3.7: no way to edit or delete
        response = client.request(
            method, f"/cases/{case['id']}/audit", headers=tenants.handler_a.headers
        )
        assert response.status_code == 405
