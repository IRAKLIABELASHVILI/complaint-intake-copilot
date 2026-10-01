import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CaseServiceDep
from app.domain.enums import CaseStatus
from app.schemas.cases import (
    AuditEventRead,
    CaseAssign,
    CaseCreate,
    CaseList,
    CaseRead,
    CaseSummary,
)
from app.services.case_service import AssigneeNotFoundError, CaseNotFoundError

router = APIRouter(prefix="/cases", tags=["cases"])

_NOT_FOUND = "Case not found"


@router.post(
    "",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": CaseRead, "description": "Duplicate: existing case returned"}},
)
def create_case(data: CaseCreate, service: CaseServiceDep, response: Response) -> CaseRead:
    result = service.create(data)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return CaseRead.model_validate(result.case)


@router.get("", response_model=CaseList)
def list_cases(
    service: CaseServiceDep,
    status_filter: Annotated[CaseStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CaseList:
    cases, total = service.cases.list(status=status_filter, limit=limit, offset=offset)
    return CaseList(
        items=[CaseSummary.model_validate(case) for case in cases],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: uuid.UUID, service: CaseServiceDep) -> CaseRead:
    try:
        return CaseRead.model_validate(service.get(case_id))
    except CaseNotFoundError:
        # 404, not 403: we never reveal that another tenant's case exists (US-7.4).
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from None


@router.patch("/{case_id}/assignment", response_model=CaseRead)
def assign_case(case_id: uuid.UUID, data: CaseAssign, service: CaseServiceDep) -> CaseRead:
    try:
        return CaseRead.model_validate(service.assign(case_id, data.assigned_to_user_id))
    except CaseNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from None
    except AssigneeNotFoundError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Assignee not found in your organisation"
        ) from None


@router.get("/{case_id}/audit", response_model=list[AuditEventRead])
def get_case_audit(case_id: uuid.UUID, service: CaseServiceDep) -> list[AuditEventRead]:
    try:
        service.get(case_id)
    except CaseNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND) from None
    return [AuditEventRead.model_validate(event) for event in service.audit.list_for_case(case_id)]
