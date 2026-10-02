"""UK bank holidays, loaded from a local copy of https://www.gov.uk/bank-holidays.json (US-4.9).

The app never calls gov.uk at runtime. To update the file, run:
    python -m app.reference_data.refresh_bank_holidays

C# comparison: reading an embedded resource once and caching it as a singleton.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, RootModel, model_validator

from app.domain.business_calendar import BusinessCalendar
from app.domain.enums import BankHolidayRegion

BANK_HOLIDAYS_FILE = Path(__file__).with_name("bank-holidays.json")


class BankHolidayEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    date: date


class BankHolidayDivision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    division: str
    events: list[BankHolidayEvent]


class BankHolidayFeed(RootModel[dict[str, BankHolidayDivision]]):
    """The gov.uk feed format. Validation fails unless every region we support has events."""

    @model_validator(mode="after")
    def every_region_has_events(self) -> "BankHolidayFeed":
        for region in BankHolidayRegion:
            division = self.root.get(region.value)
            if division is None or not division.events:
                raise ValueError(f"Bank holiday feed has no events for region '{region}'")
        return self

    def calendar_for(self, region: BankHolidayRegion) -> BusinessCalendar:
        holidays = frozenset(event.date for event in self.root[region.value].events)
        return BusinessCalendar(
            bank_holidays=holidays,
            first_year=min(holidays).year,
            last_year=max(holidays).year,
        )


def parse_feed(raw_json: str | bytes) -> BankHolidayFeed:
    return BankHolidayFeed.model_validate_json(raw_json)


@lru_cache
def _load_feed() -> BankHolidayFeed:
    return parse_feed(BANK_HOLIDAYS_FILE.read_bytes())


@lru_cache
def calendar_for_region(region: BankHolidayRegion) -> BusinessCalendar:
    """The business calendar for a region. Loaded once per process, then cached."""
    return _load_feed().calendar_for(region)
