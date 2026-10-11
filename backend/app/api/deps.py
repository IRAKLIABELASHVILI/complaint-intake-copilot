"""FastAPI dependencies.

C# comparison: FastAPI's `Depends(...)` is constructor injection per request. A dependency that
`yield`s is like a scoped service with Dispose(): code after `yield` runs when the request ends.
"""

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Tenant, User
from app.db.repositories import AccountRepository
from app.db.session import new_session
from app.domain.business_calendar import BusinessCalendar
from app.domain.enums import UserRole
from app.reference_data.bank_holidays import calendar_for_region
from app.services.case_service import CaseService
from app.services.dashboard_service import DashboardService
from app.services.decision_service import DecisionService

_bearer = HTTPBearer(auto_error=False)


def get_session() -> Iterator[Session]:
    session = new_session()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the user from `Authorization: Bearer <token>`.

    This is the ONLY source of tenant_id in the whole API (US-7.2). Nothing in the request body,
    query string or headers can choose the tenant.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token_hash = hash_token(credentials.credentials)
    user = AccountRepository(session).by_session(token_hash, datetime.now(UTC))
    if user is None and get_settings().allow_demo_tokens:
        user = session.scalars(select(User).where(User.api_token_hash == token_hash)).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_now() -> datetime:
    """The current time. A dependency, so tests can freeze the clock (C#: TimeProvider)."""
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]


def get_business_calendar(session: SessionDep, user: CurrentUser) -> BusinessCalendar:
    """The bank holidays of the user's tenant. The region comes from the tenant row only."""
    tenant = session.get_one(Tenant, user.tenant_id)
    return calendar_for_region(tenant.bank_holiday_region)


def get_case_service(
    session: SessionDep,
    user: CurrentUser,
    calendar: Annotated[BusinessCalendar, Depends(get_business_calendar)],
) -> CaseService:
    return CaseService(session, user, calendar)


CaseServiceDep = Annotated[CaseService, Depends(get_case_service)]


def get_decision_service(session: SessionDep, user: CurrentUser) -> DecisionService:
    return DecisionService(session, user)


DecisionServiceDep = Annotated[DecisionService, Depends(get_decision_service)]


def require_team_lead(user: CurrentUser) -> User:
    """US-5.2: the dashboard is for team leads. A handler gets 403 (they are signed in, but the
    answer is "not allowed", unlike another tenant's case, where it is "not found")."""
    if user.role is not UserRole.TEAM_LEAD:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only team leads can see the dashboard")
    return user


TeamLead = Annotated[User, Depends(require_team_lead)]


def get_dashboard_service(
    session: SessionDep,
    user: TeamLead,
    calendar: Annotated[BusinessCalendar, Depends(get_business_calendar)],
) -> DashboardService:
    return DashboardService(session, user, calendar)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
