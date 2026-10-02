"""Regulatory deadlines (US-4). Pure functions, so every boundary is tested with a fixed "now".

Times are written in UK local time (`uk(...)`) to match how the rules are stated.
Winter (GMT) is UTC+0 and summer (BST) is UTC+1.
"""

from datetime import UTC, datetime

import pytest

from app.domain.business_calendar import HolidayDataUnavailableError
from app.domain.deadlines import (
    UK_TIMEZONE,
    DeadlineProgress,
    calculate_deadlines,
    track_deadlines,
)
from app.domain.enums import BankHolidayRegion, ResolutionType
from app.reference_data.bank_holidays import calendar_for_region

ENGLAND = calendar_for_region(BankHolidayRegion.ENGLAND_AND_WALES)


def uk(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UK_TIMEZONE)


# --- SRC deadline: 17:00 on the third business day after the day of receipt (DISP 1.5.1R) ------


def test_src_deadline_received_on_friday() -> None:
    """US-4.3: received Friday 2026-12-18 -> Wednesday 2026-12-23 at 17:00."""
    deadlines = calculate_deadlines(uk(2026, 12, 18, 10), ENGLAND)

    assert deadlines.src_deadline_at == uk(2026, 12, 23, 17)


def test_src_deadline_skips_christmas_and_the_boxing_day_substitute() -> None:
    """US-4.4: received Wednesday 2026-12-23 -> Wednesday 2026-12-30 at 17:00."""
    deadlines = calculate_deadlines(uk(2026, 12, 23, 10), ENGLAND)

    assert deadlines.src_deadline_at == uk(2026, 12, 30, 17)


def test_src_deadline_received_on_saturday_counts_from_monday() -> None:
    """US-4.5: received Saturday 2026-10-03 -> Mon (1), Tue (2), Wed (3) 2026-10-07 at 17:00."""
    deadlines = calculate_deadlines(uk(2026, 10, 3, 11), ENGLAND)

    assert deadlines.src_deadline_at == uk(2026, 10, 7, 17)


def test_day_of_receipt_is_the_uk_date_not_the_utc_date() -> None:
    """23:30 UTC on Thursday 2 July is 00:30 BST on Friday 3 July: received on the Friday."""
    received_at = datetime(2026, 7, 2, 23, 30, tzinfo=UTC)

    deadlines = calculate_deadlines(received_at, ENGLAND)

    assert deadlines.src_deadline_at == uk(2026, 7, 8, 17)  # Mon 6, Tue 7, Wed 8


def test_deadlines_are_returned_in_utc() -> None:
    deadlines = calculate_deadlines(uk(2026, 10, 3, 11), ENGLAND)

    assert deadlines.src_deadline_at.tzinfo is UTC
    assert deadlines.src_deadline_at == datetime(2026, 10, 7, 16, tzinfo=UTC)  # 17:00 BST


# --- Final response deadline: end of day, 8 weeks (56 calendar days) after receipt (DISP 1.6.2R) -


def test_final_response_deadline_is_end_of_day_56_calendar_days_later() -> None:
    deadlines = calculate_deadlines(uk(2026, 9, 14, 9, 30), ENGLAND)

    assert deadlines.final_response_deadline_at == uk(2026, 11, 9, 23, 59, 59)


def test_final_response_deadline_uses_uk_time_across_a_clock_change() -> None:
    """Received in GMT, due in BST: still 23:59:59 UK time, which is 22:59:59 UTC."""
    deadlines = calculate_deadlines(uk(2026, 3, 2, 9), ENGLAND)

    assert deadlines.final_response_deadline_at == datetime(2026, 4, 27, 22, 59, 59, tzinfo=UTC)


def test_naive_datetimes_are_refused() -> None:
    with pytest.raises(ValueError, match="Naive"):
        calculate_deadlines(datetime(2026, 10, 2, 9), ENGLAND)


def test_receipt_outside_the_holiday_data_is_refused() -> None:
    with pytest.raises(HolidayDataUnavailableError):
        calculate_deadlines(uk(2035, 1, 10, 9), ENGLAND)


# --- Countdown and overdue (US-4.6) --------------------------------------------------------------

# Received Monday 2026-09-14: SRC due Thursday 17 Sept 17:00, final response 9 Nov 23:59:59.
DEADLINES = calculate_deadlines(uk(2026, 9, 14, 9, 30), ENGLAND)


def src_progress_at(now: datetime) -> DeadlineProgress:
    tracking = track_deadlines(
        DEADLINES, now=now, calendar=ENGLAND, resolved_at=None, resolution_type=None
    )
    assert tracking.src is not None
    return tracking.src


def test_business_days_remaining_before_the_deadline() -> None:
    progress = src_progress_at(uk(2026, 9, 15, 10))  # Tuesday

    assert progress.business_days_remaining == 2  # Wednesday, Thursday
    assert progress.is_overdue is False


def test_due_today_is_zero_and_not_overdue_until_the_deadline_time() -> None:
    progress = src_progress_at(uk(2026, 9, 17, 16, 59))  # Thursday, one minute before

    assert progress.business_days_remaining == 0
    assert progress.is_overdue is False


def test_missed_today_is_one_business_day_overdue() -> None:
    progress = src_progress_at(uk(2026, 9, 17, 18))  # Thursday, one hour after

    assert progress.business_days_remaining == -1
    assert progress.is_overdue is True


def test_overdue_counts_business_days_since_the_deadline() -> None:
    progress = src_progress_at(uk(2026, 9, 21, 10))  # the following Monday

    assert progress.business_days_remaining == -2  # Friday, Monday
    assert progress.is_overdue is True


def test_both_deadlines_are_tracked_while_the_case_is_open() -> None:
    tracking = track_deadlines(
        DEADLINES, now=uk(2026, 9, 15, 10), calendar=ENGLAND, resolved_at=None, resolution_type=None
    )

    assert tracking.final_response is not None
    assert tracking.final_response.is_overdue is False
    assert tracking.resolved_in_time is None


# --- Resolved cases stop counting down (US-4.7) --------------------------------------------------


def test_summary_resolution_by_the_src_deadline_is_in_time() -> None:
    tracking = track_deadlines(
        DEADLINES,
        now=uk(2026, 12, 1),
        calendar=ENGLAND,
        resolved_at=uk(2026, 9, 17, 16),
        resolution_type=ResolutionType.SUMMARY_RESOLUTION,
    )

    assert tracking.src is None
    assert tracking.final_response is None
    assert tracking.resolved_in_time is True


def test_summary_resolution_after_the_src_deadline_is_late() -> None:
    tracking = track_deadlines(
        DEADLINES,
        now=uk(2026, 12, 1),
        calendar=ENGLAND,
        resolved_at=uk(2026, 9, 18, 9),
        resolution_type=ResolutionType.SUMMARY_RESOLUTION,
    )

    assert tracking.resolved_in_time is False


def test_final_response_is_judged_against_the_eight_week_deadline() -> None:
    def resolved_in_time(resolved_at: datetime) -> bool | None:
        return track_deadlines(
            DEADLINES,
            now=uk(2026, 12, 1),
            calendar=ENGLAND,
            resolved_at=resolved_at,
            resolution_type=ResolutionType.FINAL_RESPONSE,
        ).resolved_in_time

    assert resolved_in_time(uk(2026, 11, 9, 23, 59, 59)) is True
    assert resolved_in_time(uk(2026, 11, 10, 0, 0, 0)) is False
