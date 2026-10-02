"""Download the gov.uk bank holiday feed and replace the local copy. A manual, offline-safe step.

Run from backend/:  python -m app.reference_data.refresh_bank_holidays

The download is validated with the same model the app uses before anything is written, and the
file is replaced atomically, so a bad or partial download can never break the app.
"""

import json
import os
import tempfile
import urllib.request

from app.domain.enums import BankHolidayRegion
from app.reference_data.bank_holidays import BANK_HOLIDAYS_FILE, parse_feed

FEED_URL = "https://www.gov.uk/bank-holidays.json"  # fixed HTTPS source, never user input
TIMEOUT_SECONDS = 30
MAX_BYTES = 1_000_000  # the real feed is ~20 KB; anything far larger is not the feed


def download_feed() -> bytes:
    request = urllib.request.Request(FEED_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body: bytes = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError(f"Feed is larger than {MAX_BYTES} bytes; refusing to use it")
    return body


def write_atomically(content: str) -> None:
    """Write to a temporary file next to the target, then swap it in with one rename."""
    descriptor, temp_path = tempfile.mkstemp(dir=BANK_HOLIDAYS_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write(content)
        os.replace(temp_path, BANK_HOLIDAYS_FILE)
    except BaseException:
        os.unlink(temp_path)
        raise


def main() -> None:
    raw = download_feed()
    feed = parse_feed(raw)  # raises before writing if the data is not what we expect
    write_atomically(json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n")

    print(f"Updated {BANK_HOLIDAYS_FILE.name}.")
    for region in BankHolidayRegion:
        calendar = feed.calendar_for(region)
        print(f"  {region}: {calendar.first_year}-{calendar.last_year}")


if __name__ == "__main__":
    main()
