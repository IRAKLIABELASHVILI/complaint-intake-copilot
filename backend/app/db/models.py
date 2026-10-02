"""Database models (milestone 2: tenants, users, cases, audit events).

Analyses, vulnerability indicators and processed_messages arrive with milestones 4 and 5,
each with its own Alembic migration.

C# comparison: these are EF Core entity classes. `Mapped[str | None]` = nullable column.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, str_enum, utc_now
from app.domain.enums import (
    AuditSource,
    BankHolidayRegion,
    CaseStatus,
    Category,
    Priority,
    ResolutionType,
    UserRole,
)


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    bank_holiday_region: Mapped[BankHolidayRegion] = mapped_column(
        str_enum(BankHolidayRegion), default=BankHolidayRegion.ENGLAND_AND_WALES
    )


class User(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole))
    # SHA-256 of the user's API token. The token itself is never stored.
    api_token_hash: Mapped[str] = mapped_column(String(64), unique=True)


class Case(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_message_id", name="uq_cases_tenant_message"),
        Index("ix_cases_tenant_status", "tenant_id", "status"),
        Index("ix_cases_tenant_received_at", "tenant_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255))

    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    sender_email: Mapped[str] = mapped_column(String(320))
    sender_name: Mapped[str | None] = mapped_column(String(200))
    received_at: Mapped[datetime]

    status: Mapped[CaseStatus] = mapped_column(str_enum(CaseStatus), default=CaseStatus.NEW)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    # Set once at intake by the deadline engine (app/domain/deadlines.py), stored for indexing.
    src_deadline_at: Mapped[datetime | None]
    final_response_deadline_at: Mapped[datetime | None]

    # Null until a person decides (milestone 5). Suggestions live on the analysis, not here.
    final_category: Mapped[Category | None] = mapped_column(str_enum(Category))
    final_priority: Mapped[Priority | None] = mapped_column(str_enum(Priority))

    resolved_at: Mapped[datetime | None]
    resolution_type: Mapped[ResolutionType | None] = mapped_column(str_enum(ResolutionType))

    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class AuditEvent(TenantScopedMixin, TimestampMixin, Base):
    """Append-only. There is deliberately no update or delete path anywhere in the code."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    field: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[Any | None] = mapped_column(JSON(none_as_null=True))
    new_value: Mapped[Any | None] = mapped_column(JSON(none_as_null=True))
    source: Mapped[AuditSource] = mapped_column(str_enum(AuditSource))
    correlation_id: Mapped[str | None] = mapped_column(String(64))

    # The relationship tells SQLAlchemy to INSERT the case before its audit events.
    case: Mapped[Case] = relationship()
