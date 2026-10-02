"""How long to wait before retrying a failed job. A pure function, so the schedule is testable."""

from datetime import timedelta

MAX_ATTEMPTS = 5
BASE_DELAY = timedelta(seconds=2)
MAX_DELAY = timedelta(minutes=5)


def retry_delay(failed_attempt: int) -> timedelta | None:
    """Delay before the next try after attempt number `failed_attempt` (1-based) failed.

    Exponential backoff: 2s, 4s, 8s, 16s. None once all attempts are used: dead-letter it.
    """
    if failed_attempt >= MAX_ATTEMPTS:
        return None
    return min(BASE_DELAY * int(2 ** (failed_attempt - 1)), MAX_DELAY)
