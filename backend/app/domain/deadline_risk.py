"""Which open cases are close to a deadline, or past it (US-5). Pure functions, like deadlines.py.

The dashboard counts in SQL, so each rule becomes a time window on a stored deadline column
instead of a countdown calculated case by case. The windows agree exactly with the countdown
shown on every case (`track_deadlines`); tests/test_deadline_risk.py proves it day by day.

C# comparison: a specification object that a repository can turn into a `Where(...)`.
"""

from dataclasses import dataclass
from datetime import datetime, time

from app.domain.business_calendar import BusinessCalendar
from app.domain.deadlines import uk_date, uk_time_as_utc
from app.domain.enums import DeadlineRisk

AT_RISK_BUSINESS_DAYS = 2


@dataclass(frozen=True)
class DeadlineWindow:
    """Deadlines `d` with `starts_at <= d < ends_at`. No start: everything before `ends_at`."""

    starts_at: datetime | None
    ends_at: datetime


def deadline_window(
    risk: DeadlineRisk, now: datetime, calendar: BusinessCalendar
) -> DeadlineWindow:
    if risk is DeadlineRisk.OVERDUE:
        return overdue_window(now)
    return at_risk_window(now, calendar)


def overdue_window(now: datetime) -> DeadlineWindow:
    """Past the deadline. At the exact deadline moment a case is still on time."""
    return DeadlineWindow(starts_at=None, ends_at=now)


def at_risk_window(now: datetime, calendar: BusinessCalendar) -> DeadlineWindow:
    """Not overdue, with AT_RISK_BUSINESS_DAYS business days or fewer left.

    "Days left" counts business days after today up to the deadline day (deadlines.py). So a
    deadline stays at risk until the start of the next business day after that: seen on a
    Wednesday, a deadline on Saturday has two business days left (Thursday, Friday) and is at
    risk; one on Monday has three and is not.
    """
    first_safe_day = calendar.add_business_days(uk_date(now), AT_RISK_BUSINESS_DAYS + 1)
    return DeadlineWindow(starts_at=now, ends_at=uk_time_as_utc(first_safe_day, time(0, 0)))
