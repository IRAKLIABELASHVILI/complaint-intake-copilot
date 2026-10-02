"""Business days: weekdays that are not bank holidays. Pure logic, no I/O.

C# comparison: an immutable value object (a `record`) with a few query methods.
"""

from dataclasses import dataclass
from datetime import date, timedelta

_SATURDAY = 5  # date.weekday(): Monday = 0 ... Sunday = 6
_ONE_DAY = timedelta(days=1)


class HolidayDataUnavailableError(Exception):
    """The bank holiday data does not cover the requested date, so a business day is unknown.

    Guessing would produce a wrong regulatory deadline, so we refuse instead.
    """

    def __init__(self, day: date, first_year: int, last_year: int) -> None:
        super().__init__(
            f"No bank holiday data for {day.isoformat()} "
            f"(data covers {first_year}-{last_year}). Refresh the bank holiday file."
        )
        self.day = day


@dataclass(frozen=True)
class BusinessCalendar:
    bank_holidays: frozenset[date]
    first_year: int
    last_year: int

    def is_business_day(self, day: date) -> bool:
        self._ensure_covered(day)
        return day.weekday() < _SATURDAY and day not in self.bank_holidays

    def add_business_days(self, start: date, count: int) -> date:
        """The `count`-th business day after `start`. `start` itself never counts."""
        day = start
        found = 0
        while found < count:
            day += _ONE_DAY
            if self.is_business_day(day):
                found += 1
        return day

    def business_days_between(self, start: date, end: date) -> int:
        """Business days after `start`, up to and including `end`. 0 when `end` <= `start`."""
        count = 0
        day = start
        while day < end:
            day += _ONE_DAY
            if self.is_business_day(day):
                count += 1
        return count

    def _ensure_covered(self, day: date) -> None:
        if not self.first_year <= day.year <= self.last_year:
            raise HolidayDataUnavailableError(day, self.first_year, self.last_year)
