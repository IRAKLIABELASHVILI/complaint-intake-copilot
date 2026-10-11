from fastapi import APIRouter, HTTPException, status

from app.api.deps import DashboardServiceDep, NowDep
from app.domain.business_calendar import HolidayDataUnavailableError
from app.schemas.dashboard import DashboardRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CALENDAR_OUT_OF_DATE = "Bank holiday data does not cover the coming days. Refresh it."


@router.get(
    "",
    response_model=DashboardRead,
    responses={403: {"description": "Not a team lead"}, 503: {"description": CALENDAR_OUT_OF_DATE}},
)
def get_dashboard(service: DashboardServiceDep, now: NowDep) -> DashboardRead:
    """US-5: open cases close to breach and overdue, by category and by vulnerability.

    Team leads only, and for their own tenant only. Every number links to `GET /cases` with the
    matching filters.
    """
    try:
        dashboard = service.dashboard(now)
    except HolidayDataUnavailableError:
        # Never guess a business day (US-4): say the reference data needs refreshing instead.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, CALENDAR_OUT_OF_DATE) from None
    return DashboardRead.model_validate(dashboard)
