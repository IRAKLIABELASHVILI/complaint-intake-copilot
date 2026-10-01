"""SQLAlchemy declarative base and shared column types.

C# comparison: Base is like your DbContext's model configuration (OnModelCreating conventions).
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import DateTime, Dialect, Enum, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that is always timezone-aware UTC in Python.

    - Refuses naive datetimes on write (a naive datetime is a bug waiting to happen with deadlines).
    - PostgreSQL stores `timestamptz`. SQLite (used for fast local tests) has no timezone support,
      so we store UTC without the offset and re-attach UTC on read.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use an aware datetime in UTC")
        value = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def str_enum(enum_class: type[StrEnum]) -> Enum:
    """Store a StrEnum as a plain VARCHAR holding its value (not a native PostgreSQL ENUM type).

    Native enums need a migration for every new value; a string column does not.
    """
    return Enum(
        enum_class,
        native_enum=False,
        create_constraint=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: UtcDateTime}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utc_now, server_default=func.now())


class TenantScopedMixin:
    """Every tenant-owned table gets this column. Repositories filter on it (repositories.py)."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
