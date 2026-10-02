"""The bank holiday file (US-4.9): validated on load, so bad data fails loudly, not silently."""

import json

import pytest
from pydantic import ValidationError

from app.domain.enums import BankHolidayRegion
from app.reference_data.bank_holidays import BANK_HOLIDAYS_FILE, calendar_for_region, parse_feed


def _feed(divisions: dict[str, list[dict[str, str]]]) -> str:
    return json.dumps(
        {name: {"division": name, "events": events} for name, events in divisions.items()}
    )


def _event(day: str) -> dict[str, str]:
    return {"title": "Holiday", "date": day, "notes": "", "bunting": "true"}


ALL_REGIONS = {region.value: [_event("2026-12-25")] for region in BankHolidayRegion}


def test_the_bundled_file_loads_for_every_region() -> None:
    for region in BankHolidayRegion:
        calendar = calendar_for_region(region)
        assert calendar.bank_holidays
        assert calendar.first_year <= 2026 <= calendar.last_year


def test_the_bundled_file_matches_the_gov_uk_format() -> None:
    raw = json.loads(BANK_HOLIDAYS_FILE.read_text(encoding="utf-8"))

    assert set(raw) == {region.value for region in BankHolidayRegion}


def test_coverage_is_the_range_of_years_in_the_data() -> None:
    scotland = [_event("2025-01-01"), _event("2027-12-27")]
    feed = parse_feed(_feed(ALL_REGIONS | {"scotland": scotland}))

    calendar = feed.calendar_for(BankHolidayRegion.SCOTLAND)

    assert (calendar.first_year, calendar.last_year) == (2025, 2027)


def test_a_feed_missing_a_region_is_rejected() -> None:
    incomplete = {k: v for k, v in ALL_REGIONS.items() if k != "northern-ireland"}

    with pytest.raises(ValidationError, match="northern-ireland"):
        parse_feed(_feed(incomplete))


def test_a_region_with_no_events_is_rejected() -> None:
    with pytest.raises(ValidationError, match="scotland"):
        parse_feed(_feed(ALL_REGIONS | {"scotland": []}))


def test_an_invalid_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_feed(_feed(ALL_REGIONS | {"scotland": [_event("2026-02-30")]}))
