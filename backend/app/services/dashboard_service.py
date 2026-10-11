"""The team lead dashboard (US-5): what is close to breach, what is overdue, and the mix of
categories and vulnerability, for the open cases of the team lead's tenant.

C# comparison: a read-side query service (the "Q" of CQRS) returning a view model.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import User
from app.db.repositories import CaseRepository, DeadlineCriterion, UserRepository
from app.domain.business_calendar import BusinessCalendar
from app.domain.deadline_risk import AT_RISK_BUSINESS_DAYS, deadline_window
from app.domain.enums import (
    Category,
    DeadlineKind,
    DeadlineRisk,
    IndicatorType,
    VulnerabilityDriver,
)
from app.domain.vulnerability import driver_for


@dataclass(frozen=True)
class DeadlineCounts:
    at_risk: int
    overdue: int


@dataclass(frozen=True)
class CategoryCount:
    category: Category
    decided: int
    suggested: int


@dataclass(frozen=True)
class VulnerabilityCount:
    indicator_type: IndicatorType
    driver: VulnerabilityDriver
    cases: int


@dataclass(frozen=True)
class AssigneeCount:
    user_id: uuid.UUID | None
    display_name: str
    open_cases: int


@dataclass(frozen=True)
class Dashboard:
    generated_at: datetime
    open_cases: int
    at_risk_business_days: int
    summary_resolution: DeadlineCounts
    final_response: DeadlineCounts
    categories: tuple[CategoryCount, ...]
    uncategorised: int
    vulnerabilities: tuple[VulnerabilityCount, ...]
    assignments: tuple[AssigneeCount, ...]


class DashboardService:
    def __init__(self, session: Session, actor: User, calendar: BusinessCalendar) -> None:
        self.cases = CaseRepository(session, actor.tenant_id)
        self.users = UserRepository(session, actor.tenant_id)
        self.calendar = calendar  # the actor's tenant's bank holidays

    def dashboard(self, now: datetime) -> Dashboard:
        """Raises HolidayDataUnavailableError when the bank holidays do not cover the next days."""
        deadline_counts = self._deadline_counts(now)
        decided = self.cases.count_by_final_category()
        suggested = self.cases.count_by_suggested_category()
        vulnerable = self.cases.count_by_confirmed_vulnerability()
        return Dashboard(
            generated_at=now,
            open_cases=self.cases.count_open(),
            at_risk_business_days=AT_RISK_BUSINESS_DAYS,
            summary_resolution=deadline_counts[DeadlineKind.SUMMARY_RESOLUTION],
            final_response=deadline_counts[DeadlineKind.FINAL_RESPONSE],
            # Every category and type, zeros included: "no fraud cases" is information too.
            categories=tuple(
                CategoryCount(category, decided.get(category, 0), suggested.get(category, 0))
                for category in Category
            ),
            uncategorised=self.cases.count_uncategorised(),
            vulnerabilities=tuple(
                VulnerabilityCount(kind, driver_for(kind), vulnerable.get(kind, 0))
                for kind in IndicatorType
            ),
            assignments=self._assignee_counts(),
        )

    def _assignee_counts(self) -> tuple[AssigneeCount, ...]:
        """Open cases per person, busiest first; cases nobody owns are one more row."""
        counts = self.cases.count_by_assignee()
        names = self.users.display_names([user_id for user_id in counts if user_id is not None])

        def name_of(user_id: uuid.UUID | None) -> str:
            if user_id is None:
                return "Unassigned"
            return names.get(user_id, "Assigned colleague")

        busiest_first = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))
        return tuple(
            AssigneeCount(user_id, name_of(user_id), open_cases)
            for user_id, open_cases in busiest_first
        )

    def _deadline_counts(self, now: datetime) -> dict[DeadlineKind, DeadlineCounts]:
        criteria = {
            (kind, risk): DeadlineCriterion(kind, deadline_window(risk, now, self.calendar))
            for kind in DeadlineKind
            for risk in DeadlineRisk
        }
        counts = self.cases.count_deadlines(list(criteria.values()))
        return {
            kind: DeadlineCounts(
                at_risk=counts[criteria[kind, DeadlineRisk.AT_RISK]],
                overdue=counts[criteria[kind, DeadlineRisk.OVERDUE]],
            )
            for kind in DeadlineKind
        }
