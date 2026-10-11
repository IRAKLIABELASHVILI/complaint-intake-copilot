import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CaseServiceDep, DecisionServiceDep, NowDep
from app.api.errors import CALENDAR_OUT_OF_DATE
from app.db.models import Case
from app.schemas.cases import (
    AuditEventRead,
    CaseAssign,
    CaseCreate,
    CaseList,
    CaseListQuery,
    CaseRead,
    CaseResolve,
    CaseSummary,
    CategoryDecision,
    DeadlineTrackingRead,
    IndicatorCreate,
    IndicatorDecisionRequest,
    IndicatorRead,
    PriorityDecision,
    SuggestionRead,
)
from app.services.case_service import CaseService

router = APIRouter(prefix="/cases", tags=["cases"])


def _to_response[ResponseT: (CaseRead, CaseSummary)](
    response_model: type[ResponseT], case: Case, service: CaseService, now: datetime
) -> ResponseT:
    """Map a case to its response model, adding the deadline countdown for `now`."""
    response = response_model.model_validate(case)
    tracking = service.deadline_tracking(case, now)
    response.deadline_tracking = DeadlineTrackingRead.model_validate(tracking) if tracking else None
    return response


def _case_detail(case: Case, service: CaseService, now: datetime) -> CaseRead:
    """The full case: deadlines plus what a handler reviews (suggestion, reason, indicators)."""
    detail = _to_response(CaseRead, case, service, now)
    detail.assigned_to_display_name = _assignee_name(case, service.assignee_names([case]))
    review = service.review(case)
    detail.suggestion = (
        SuggestionRead.model_validate(review.suggestion) if review.suggestion else None
    )
    detail.review_reason = review.review_reason
    detail.vulnerability_indicators = [IndicatorRead.model_validate(i) for i in review.indicators]
    return detail


def _assignee_name(case: Case, names: dict[uuid.UUID, str]) -> str | None:
    return names.get(case.assigned_to_user_id) if case.assigned_to_user_id else None


@router.post(
    "",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": CaseRead, "description": "Duplicate: existing case returned"}},
)
def create_case(
    data: CaseCreate, service: CaseServiceDep, now: NowDep, response: Response
) -> CaseRead:
    result = service.create(data)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _case_detail(result.case, service, now)


@router.get(
    "",
    response_model=CaseList,
    responses={503: {"description": CALENDAR_OUT_OF_DATE}},
)
def list_cases(
    service: CaseServiceDep,
    now: NowDep,
    query: Annotated[CaseListQuery, Query()],
) -> CaseList:
    cases, total = service.list(query, now, limit=query.limit, offset=query.offset)
    flags = service.indicators.open_counts([case.id for case in cases])
    names = service.assignee_names(cases)
    items = []
    for case in cases:
        item = _to_response(CaseSummary, case, service, now)
        item.open_vulnerability_flags = flags.get(case.id, 0)
        item.assigned_to_display_name = _assignee_name(case, names)
        items.append(item)
    return CaseList(items=items, total=total, limit=query.limit, offset=query.offset)


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: uuid.UUID, service: CaseServiceDep, now: NowDep) -> CaseRead:
    case = service.get(case_id)
    return _case_detail(case, service, now)


@router.patch("/{case_id}/assignment", response_model=CaseRead)
def assign_case(
    case_id: uuid.UUID, data: CaseAssign, service: CaseServiceDep, now: NowDep
) -> CaseRead:
    case = service.assign(
        case_id, data.assigned_to_user_id, only_if_unassigned=data.only_if_unassigned
    )
    return _case_detail(case, service, now)


@router.get("/{case_id}/audit", response_model=list[AuditEventRead])
def get_case_audit(case_id: uuid.UUID, service: CaseServiceDep) -> list[AuditEventRead]:
    service.get(case_id)
    return [AuditEventRead.model_validate(event) for event in service.audit.list_for_case(case_id)]


# --- Decisions (US-3). The AI suggests; only these endpoints make anything final. ---------------


@router.put("/{case_id}/category", response_model=CaseRead)
def decide_category(
    case_id: uuid.UUID,
    data: CategoryDecision,
    decisions: DecisionServiceDep,
    service: CaseServiceDep,
    now: NowDep,
) -> CaseRead:
    """Accept the suggested category (send the same value) or override it (send another)."""
    case = decisions.set_category(case_id, data.category)
    return _case_detail(case, service, now)


@router.put("/{case_id}/priority", response_model=CaseRead)
def decide_priority(
    case_id: uuid.UUID,
    data: PriorityDecision,
    decisions: DecisionServiceDep,
    service: CaseServiceDep,
    now: NowDep,
) -> CaseRead:
    """Accept the suggested priority (send the same value) or override it (send another)."""
    case = decisions.set_priority(case_id, data.priority)
    return _case_detail(case, service, now)


@router.put("/{case_id}/vulnerability-indicators/{indicator_id}/decision", response_model=CaseRead)
def decide_indicator(
    case_id: uuid.UUID,
    indicator_id: uuid.UUID,
    data: IndicatorDecisionRequest,
    decisions: DecisionServiceDep,
    service: CaseServiceDep,
    now: NowDep,
) -> CaseRead:
    """Confirm or reject an indicator. A rejected one stays visible as rejected (US-3.4)."""
    case = decisions.decide_indicator(case_id, indicator_id, data.decision)
    return _case_detail(case, service, now)


@router.post(
    "/{case_id}/vulnerability-indicators",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
)
def add_indicator(
    case_id: uuid.UUID,
    data: IndicatorCreate,
    decisions: DecisionServiceDep,
    service: CaseServiceDep,
    now: NowDep,
) -> CaseRead:
    """Add an indicator the AI missed, with a quote from the complaint as evidence (US-3.5)."""
    case = decisions.add_indicator(case_id, data.indicator_type, data.evidence_quote)
    return _case_detail(case, service, now)


@router.post("/{case_id}/resolve", response_model=CaseRead)
def resolve_case(
    case_id: uuid.UUID,
    data: CaseResolve,
    decisions: DecisionServiceDep,
    service: CaseServiceDep,
    now: NowDep,
) -> CaseRead:
    """Record the outcome and stop the countdown. It does not send anything to the customer."""
    case = decisions.resolve(case_id, data.resolution_type, data.note, now)
    return _case_detail(case, service, now)
