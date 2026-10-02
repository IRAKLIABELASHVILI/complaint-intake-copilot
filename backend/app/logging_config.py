"""Structured JSON logging with a correlation id on every line.

The correlation id lives in a ContextVar. C# comparison: AsyncLocal<T> / Activity.Current.
Each request (and later each worker message) sets it once, and every log line picks it up
without passing it through every function.
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# What a correlation id may look like when it comes from outside (a header or a message).
CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_.]{1,64}$")

# Extra fields that may be passed with logger.info("...", extra={...}) and should be emitted.
_ALLOWED_EXTRA_FIELDS = (
    "tenant_id",
    "case_id",
    "user_id",
    "status_code",
    "path",
    "method",
    "message_id",
    "attempt",
    "outcome",
    "error_type",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }
        for field in _ALLOWED_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # pika logs every connection step at INFO; our own code logs what matters.
    logging.getLogger("pika").setLevel(logging.WARNING)
