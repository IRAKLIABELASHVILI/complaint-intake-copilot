"""Business days (US-4.2): weekends and the region's bank holidays are skipped."""

from datetime import date

import pytest

from app.domain.business_calendar import BusinessCalendar, HolidayDataUnavailableError
from app.domain.enums import BankHolidayRegion
from app.reference_data.bank_holidays import calendar_for_region

ENGLAND = calendar_for_region(BankHolidayRegion.ENGLAND_AND_WALES)
SCOTLAND = calendar_for_region(BankHolidayRegion.SCOTLAND)

CHRISTMAS_2026 = date(2026, 12, 25)  # Friday
BOXING_DAY_SUBSTITUTE_2026 = date(2026, 12, 28)  # Monday (Boxing Day is a Saturday)


def test_weekdays_are_business_days_and_weekends_are_not() -> None:
    assert ENGLAND.is_business_day(date(2026, 10, 2))  # Friday
    assert not ENGLAND.is_business_day(date(2026, 10, 3))  # Saturday
    assert not ENGLAND.is_business_day(date(2026, 10, 4))  # Sunday


def test_bank_holidays_and_substitute_days_are_not_business_days() -> None:
    assert not ENGLAND.is_business_day(CHRISTMAS_2026)
    assert not ENGLAND.is_business_day(BOXING_DAY_SUBSTITUTE_2026)


def test_bank_holidays_depend_on_the_region() -> None:
    second_of_january_2026 = date(2026, 1, 2)  # a bank holiday in Scotland only

    assert ENGLAND.is_business_day(second_of_january_2026)
    assert not SCOTLAND.is_business_day(second_of_january_2026)


def test_add_business_days_never_counts_the_start_day() -> None:
    friday = date(2026, 10, 2)

    assert ENGLAND.add_business_days(friday, 1) == date(2026, 10, 5)  # Monday
    assert ENGLAND.add_business_days(friday, 0) == friday


def test_business_days_between_excludes_start_and_includes_end() -> None:
    monday, wednesday = date(2026, 10, 5), date(2026, 10, 7)

    assert ENGLAND.business_days_between(monday, wednesday) == 2
    assert ENGLAND.business_days_between(wednesday, wednesday) == 0
    assert ENGLAND.business_days_between(wednesday, monday) == 0


def test_a_date_outside_the_holiday_data_is_refused_not_guessed() -> None:
    calendar = BusinessCalendar(bank_holidays=frozenset(), first_year=2026, last_year=2026)

    with pytest.raises(HolidayDataUnavailableError):
        calendar.is_business_day(date(2027, 1, 4))
