"""Regulatory complaint deadlines (US-4). Pure functions: no database, no clock.

"Now" is always a parameter, so every rule can be tested at its exact boundary.

Rules (FCA Handbook, DISP):
- Summary resolution (SRC), DISP 1.5.1R: close of business (17:00) on the third business day
  following the day of receipt.
- Final response, DISP 1.6.2R: within eight weeks (56 calendar days) of receipt; we use the end
  of that day.
Days are UK calendar days (Europe/London), whatever the UTC timestamp says.

C# comparison: a static domain service where `TimeProvider` is replaced by a `now` argument.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.business_calendar import BusinessCalendar
from app.domain.enums import ResolutionType

UK_TIMEZONE = ZoneInfo("Europe/London")

SRC_BUSINESS_DAYS = 3
SRC_CLOSE_OF_BUSINESS = time(17, 0)
FINAL_RESPONSE_PERIOD = timedelta(weeks=8)
END_OF_DAY = time(23, 59, 59)


@dataclass(frozen=True)
class CaseDeadlines:
    src_deadline_at: datetime  # UTC
    final_response_deadline_at: datetime  # UTC


@dataclass(frozen=True)
class DeadlineProgress:
    deadline_at: datetime
    business_days_remaining: int  # 0 = due today; negative = business days overdue
    is_overdue: bool


@dataclass(frozen=True)
class DeadlineTracking:
    src: DeadlineProgress | None  # None once the case is resolved: the countdown stops
    final_response: DeadlineProgress | None
    resolved_in_time: bool | None  # None while the case is open


def calculate_deadlines(received_at: datetime, calendar: BusinessCalendar) -> CaseDeadlines:
    day_of_receipt = _uk_date(received_at)
    src_day = calendar.add_business_days(day_of_receipt, SRC_BUSINESS_DAYS)
    final_response_day = day_of_receipt + FINAL_RESPONSE_PERIOD
    return CaseDeadlines(
        src_deadline_at=_uk_time_as_utc(src_day, SRC_CLOSE_OF_BUSINESS),
        final_response_deadline_at=_uk_time_as_utc(final_response_day, END_OF_DAY),
    )


def track_deadlines(
    deadlines: CaseDeadlines,
    *,
    now: datetime,
    calendar: BusinessCalendar,
    resolved_at: datetime | None,
    resolution_type: ResolutionType | None,
) -> DeadlineTracking:
    if resolved_at is not None:
        return DeadlineTracking(
            src=None,
            final_response=None,
            resolved_in_time=_resolved_in_time(deadlines, resolved_at, resolution_type),
        )
    return DeadlineTracking(
        src=_progress(deadlines.src_deadline_at, now, calendar),
        final_response=_progress(deadlines.final_response_deadline_at, now, calendar),
        resolved_in_time=None,
    )


def _progress(deadline_at: datetime, now: datetime, calendar: BusinessCalendar) -> DeadlineProgress:
    today = _uk_date(now)
    deadline_day = _uk_date(deadline_at)

    if now <= deadline_at:
        remaining = calendar.business_days_between(today, deadline_day)
        return DeadlineProgress(deadline_at, business_days_remaining=remaining, is_overdue=False)

    # Missed earlier today (e.g. 18:00 against a 17:00 deadline) still counts as one day late.
    days_late = max(1, calendar.business_days_between(deadline_day, today))
    return DeadlineProgress(deadline_at, business_days_remaining=-days_late, is_overdue=True)


def _resolved_in_time(
    deadlines: CaseDeadlines, resolved_at: datetime, resolution_type: ResolutionType | None
) -> bool:
    """An SRC must land by the SRC deadline; any other resolution by the final response one."""
    if resolution_type is ResolutionType.SUMMARY_RESOLUTION:
        return resolved_at <= deadlines.src_deadline_at
    return resolved_at <= deadlines.final_response_deadline_at


def _uk_date(moment: datetime) -> date:
    _require_aware(moment)
    return moment.astimezone(UK_TIMEZONE).date()


def _uk_time_as_utc(day: date, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=UK_TIMEZONE).astimezone(UTC)


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed; pass an aware datetime")
