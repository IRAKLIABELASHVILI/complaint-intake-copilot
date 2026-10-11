from fastapi import APIRouter

from app.api.deps import DashboardServiceDep, NowDep
from app.api.errors import CALENDAR_OUT_OF_DATE
from app.schemas.dashboard import DashboardRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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
    dashboard = service.dashboard(now)
    return DashboardRead.model_validate(dashboard)
