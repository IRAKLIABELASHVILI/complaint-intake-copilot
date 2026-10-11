"""At risk / overdue windows (US-5.1). The dashboard counts with these windows in SQL, and each
case shows its own countdown (`track_deadlines`). The two must never disagree, so the main test
compares them for every hour of a month that has weekends, a clock change and Christmas.
"""

from datetime import UTC, datetime, time, timedelta

import pytest

from app.domain.deadline_risk import (
    AT_RISK_BUSINESS_DAYS,
    DeadlineWindow,
    at_risk_window,
    deadline_window,
    overdue_window,
)
from app.domain.deadlines import (
    END_OF_DAY,
    SRC_CLOSE_OF_BUSINESS,
    UK_TIMEZONE,
    CaseDeadlines,
    track_deadlines,
)
from app.domain.enums import BankHolidayRegion, DeadlineRisk
from app.reference_data.bank_holidays import calendar_for_region

ENGLAND = calendar_for_region(BankHolidayRegion.ENGLAND_AND_WALES)


def uk(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UK_TIMEZONE)


def contains(window: DeadlineWindow, deadline: datetime) -> bool:
    """What the SQL condition does (app/db/repositories.py), in Python."""
    after_start = window.starts_at is None or deadline >= window.starts_at
    return after_start and deadline < window.ends_at


def test_wednesday_a_saturday_deadline_is_at_risk_and_a_monday_one_is_not() -> None:
    """Days left count business days after today up to the deadline day: Thursday and Friday
    for Saturday (2, at risk); Thursday, Friday and Monday for Monday (3, not at risk)."""
    window = at_risk_window(uk(2026, 10, 7, 9), ENGLAND)

    assert contains(window, uk(2026, 10, 10, 23, 59))
    assert not contains(window, uk(2026, 10, 12, 17))
    assert window.ends_at == uk(2026, 10, 12)  # midnight, UK time, at the start of Monday


def test_a_deadline_due_now_is_at_risk_and_one_a_minute_ago_is_overdue() -> None:
    now = uk(2026, 10, 7, 17)

    assert contains(at_risk_window(now, ENGLAND), now)
    assert not contains(overdue_window(now), now)
    assert contains(overdue_window(now), now - timedelta(minutes=1))
    assert not contains(at_risk_window(now, ENGLAND), now - timedelta(minutes=1))


def test_bank_holidays_stretch_the_at_risk_window() -> None:
    """Seen on Wednesday 2026-12-23: Thursday 24th (1), then Christmas and the Boxing Day
    substitute are not business days, so Tuesday 29th is the second business day."""
    window = at_risk_window(uk(2026, 12, 23, 10), ENGLAND)

    assert contains(window, uk(2026, 12, 29, 17))
    assert not contains(window, uk(2026, 12, 30, 17))


def test_deadline_window_picks_the_rule_for_the_risk() -> None:
    now = uk(2026, 10, 7, 9)

    assert deadline_window(DeadlineRisk.OVERDUE, now, ENGLAND) == overdue_window(now)
    assert deadline_window(DeadlineRisk.AT_RISK, now, ENGLAND) == at_risk_window(now, ENGLAND)


def _deadlines_around(start: datetime, days: int) -> list[datetime]:
    """Both kinds of deadline time (17:00 SRC, end-of-day final response) on every day, in UTC
    as stored. (Python compares two datetimes with the same tzinfo by wall-clock time, which is
    wrong across a clock change, so everything here is UTC.)"""
    first = start.date() - timedelta(days=3)
    return [
        datetime.combine(first + timedelta(days=offset), at, tzinfo=UK_TIMEZONE).astimezone(UTC)
        for offset in range(days + 10)
        for at in (SRC_CLOSE_OF_BUSINESS, END_OF_DAY, time(9, 0))
    ]


@pytest.mark.parametrize(
    "start",
    [
        uk(2026, 10, 19),  # includes the clock change on Sunday 25 October
        uk(2026, 12, 14),  # includes Christmas, the Boxing Day substitute and New Year
    ],
)
def test_windows_agree_with_the_countdown_shown_on_each_case(start: datetime) -> None:
    deadlines = _deadlines_around(start, days=21)

    for hour in range(0, 21 * 24, 5):
        now = start.astimezone(UTC) + timedelta(hours=hour)
        at_risk = at_risk_window(now, ENGLAND)
        overdue = overdue_window(now)
        for deadline in deadlines:
            progress = track_deadlines(
                CaseDeadlines(deadline, deadline),
                now=now,
                calendar=ENGLAND,
                resolved_at=None,
                resolution_type=None,
            ).src
            assert progress is not None
            expected_at_risk = (
                not progress.is_overdue
                and progress.business_days_remaining <= AT_RISK_BUSINESS_DAYS
            )
            assert contains(at_risk, deadline) == expected_at_risk, (now, deadline)
            assert contains(overdue, deadline) == progress.is_overdue, (now, deadline)


def test_the_tenants_own_bank_holidays_count() -> None:
    """Seen on Thursday 2026-11-26, a Tuesday 17:00 deadline is two business days away in
    Scotland (Friday; Monday is St Andrew's Day; Tuesday) and three in England."""
    scotland = calendar_for_region(BankHolidayRegion.SCOTLAND)
    now = uk(2026, 11, 26, 10)
    deadline = uk(2026, 12, 1, 17)

    assert contains(at_risk_window(now, scotland), deadline)
    assert not contains(at_risk_window(now, ENGLAND), deadline)
