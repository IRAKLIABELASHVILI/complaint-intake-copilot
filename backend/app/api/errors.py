"""Translate expected application failures into consistent HTTP responses."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.business_calendar import HolidayDataUnavailableError
from app.services.case_service import (
    AssigneeNotFoundError,
    AssignmentConflictError,
    CaseNotFoundError,
)
from app.services.decision_service import (
    CaseNotDecidableError,
    EvidenceNotInComplaintError,
    IndicatorNotFoundError,
)

CALENDAR_OUT_OF_DATE = "Bank holiday data does not cover the coming days. Refresh it."

# Missing cases always return 404, including cases belonging to another tenant.
# None means the exception carries a message intended for the caller.
_ERROR_RESPONSES: dict[type[Exception], tuple[int, str | None]] = {
    CaseNotFoundError: (status.HTTP_404_NOT_FOUND, "Case not found"),
    IndicatorNotFoundError: (status.HTTP_404_NOT_FOUND, "Vulnerability indicator not found"),
    AssignmentConflictError: (status.HTTP_409_CONFLICT, None),
    CaseNotDecidableError: (status.HTTP_409_CONFLICT, None),
    AssigneeNotFoundError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Assignee not found in your organisation",
    ),
    EvidenceNotInComplaintError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "The evidence quote must appear word for word in the complaint",
    ),
    HolidayDataUnavailableError: (status.HTTP_503_SERVICE_UNAVAILABLE, CALENDAR_OUT_OF_DATE),
}


def register_error_handlers(app: FastAPI) -> None:
    for error_type, (status_code, detail) in _ERROR_RESPONSES.items():
        app.add_exception_handler(error_type, _handler(status_code, detail))


def _handler(
    status_code: int, detail: str | None
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def respond(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": detail or str(error)})

    return respond
