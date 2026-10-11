import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CaseServiceDep, DecisionServiceDep, NowDep
from app.api.routes.dashboard import CALENDAR_OUT_OF_DATE
from app.db.models import Case
from app.domain.business_calendar import HolidayDataUnavailableError
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
from app.services.case_service import (
    AssigneeNotFoundError,
    AssignmentConflictError,
    CaseNotFoundError,
    CaseService,
)
from app.services.decision_service import (
    CaseNotDecidableError,
    EvidenceNotInComplaintError,
    IndicatorNotFoundError,
)

router = APIRouter(prefix="/cases", tags=["cases"])

_NOT_FOUND = "Case not found"


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
    if case.assigned_to_user_id is not None:
        detail.assigned_to_display_name = service.users.display_names(
            [case.assigned_to_user_id]
        ).get(case.assigned_to_user_id)
    review = service.review(case)
    detail.suggestion = (
        SuggestionRead.model_validate(review.suggestion) if review.suggestion else None
    )
    detail.review_reason = review.review_reason
    detail.vulnerability_indicators = [IndicatorRead.model_validate(i) for i in review.indicators]
    return detail


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
    try:
        cases, total = service.list(query, now, limit=query.limit, offset=query.offset)
    except HolidayDataUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CALENDAR_OUT_OF_DATE) from None
    flags = service.indicators.open_counts([case.id for case in cases])
    items = [_to_response(CaseSummary, case, service, now) for case in cases]
    assignees = service.users.display_names(
        [case.assigned_to_user_id for case in cases if case.assigned_to_user_id is not None]
    )
    for item in items:
        item.open_vulnerability_flags = flags.get(item.id, 0)
        if item.assigned_to_user_id is not None:
            item.assigned_to_display_name = assignees.get(item.assigned_to_user_id)
    return CaseList(
        items=items,
        total=total,
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: uuid.UUID, service: CaseServiceDep, now: NowDep) -> CaseRead:
    try:
        case = service.get(case_id)
    except CaseNotFoundError:
        # 404, not 403: we never reveal that another tenant's case exists (US-7.4).
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from None
    return _case_detail(case, service, now)


@router.patch("/{case_id}/assignment", response_model=CaseRead)
def assign_case(
    case_id: uuid.UUID, data: CaseAssign, service: CaseServiceDep, now: NowDep
) -> CaseRead:
    try:
        case = service.assign(
            case_id, data.assigned_to_user_id, only_if_unassigned=data.only_if_unassigned
        )
    except CaseNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from None
    except AssignmentConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except AssigneeNotFoundError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Assignee not found in your organisation"
        ) from None
    return _case_detail(case, service, now)


@router.get("/{case_id}/audit", response_model=list[AuditEventRead])
def get_case_audit(case_id: uuid.UUID, service: CaseServiceDep) -> list[AuditEventRead]:
    try:
        service.get(case_id)
    except CaseNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from None
    return [AuditEventRead.model_validate(event) for event in service.audit.list_for_case(case_id)]


# --- Decisions (US-3). The AI suggests; only these endpoints make anything final. ---------------

_DECISION_FAILURES = (
    CaseNotFoundError,
    IndicatorNotFoundError,
    CaseNotDecidableError,
    EvidenceNotInComplaintError,
)


def _decision_error(error: Exception) -> HTTPException:
    """The HTTP answer for each way a decision can be refused."""
    if isinstance(error, CaseNotDecidableError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, EvidenceNotInComplaintError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The evidence quote must appear word for word in the complaint",
        )
    if isinstance(error, IndicatorNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Vulnerability indicator not found")
    return HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)  # also for other tenants' cases


@router.put("/{case_id}/category", response_model=CaseRead)
def decide_category(
    case_id: uuid.UUID,
    data: CategoryDecision,
    decisions: DecisionServiceDep,
    service: CaseServiceDep,
    now: NowDep,
) -> CaseRead:
    """Accept the suggested category (send the same value) or override it (send another)."""
    try:
        case = decisions.set_category(case_id, data.category)
    except _DECISION_FAILURES as error:
        raise _decision_error(error) from None
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
    try:
        case = decisions.set_priority(case_id, data.priority)
    except _DECISION_FAILURES as error:
        raise _decision_error(error) from None
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
    try:
        case = decisions.decide_indicator(case_id, indicator_id, data.decision)
    except _DECISION_FAILURES as error:
        raise _decision_error(error) from None
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
    try:
        case = decisions.add_indicator(case_id, data.indicator_type, data.evidence_quote)
    except _DECISION_FAILURES as error:
        raise _decision_error(error) from None
    return _case_detail(case, service, now)


@router.post("/{case_id}/resolve", response_model=CaseRead)
def resolve_case(
    case_id: uuid.UUID, data: CaseResolve, service: CaseServiceDep, now: NowDep
) -> CaseRead:
    try:
        case = service.resolve(case_id, data.resolution_type, data.note, now)
    except CaseNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from None
    except AssignmentConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return _case_detail(case, service, now)
