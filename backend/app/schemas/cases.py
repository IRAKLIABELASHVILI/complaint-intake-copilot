"""API request and response models.

C# comparison: these are DTOs with validation attributes. Pydantic validates on the way in
(422 with field errors on failure) and serialises on the way out. They also generate the
OpenAPI schema, which milestone 6 turns into a typed TypeScript client.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.enums import (
    AuditSource,
    CaseStatus,
    Category,
    Priority,
    ResolutionType,
)

# Allow a little clock difference between the mail server and us.
_MAX_CLOCK_SKEW = timedelta(minutes=5)


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=50_000)
    sender_email: EmailStr
    sender_name: str | None = Field(default=None, max_length=200)
    received_at: AwareDatetime | None = Field(
        default=None, description="When the complaint was received. Defaults to now."
    )
    external_message_id: str | None = Field(
        default=None,
        max_length=255,
        description="Email Message-ID. Submitting the same id twice returns the existing case.",
    )

    @field_validator("received_at")
    @classmethod
    def received_at_not_in_future(cls, value: datetime | None) -> datetime | None:
        if value is not None and value > datetime.now(UTC) + _MAX_CLOCK_SKEW:
            raise ValueError("received_at cannot be in the future")
        return value


class CaseAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to_user_id: uuid.UUID | None


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    external_message_id: str | None
    subject: str
    body: str
    sender_email: str
    sender_name: str | None
    received_at: datetime
    status: CaseStatus
    assigned_to_user_id: uuid.UUID | None
    src_deadline_at: datetime | None
    final_response_deadline_at: datetime | None
    final_category: Category | None
    final_priority: Priority | None
    resolved_at: datetime | None
    resolution_type: ResolutionType | None
    created_at: datetime
    updated_at: datetime


class CaseSummary(BaseModel):
    """Lighter shape for lists: no body."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    subject: str
    sender_email: str
    received_at: datetime
    status: CaseStatus
    assigned_to_user_id: uuid.UUID | None
    src_deadline_at: datetime | None
    final_response_deadline_at: datetime | None


class CaseList(BaseModel):
    items: list[CaseSummary]
    total: int
    limit: int
    offset: int


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    field: str | None
    old_value: Any | None
    new_value: Any | None
    source: AuditSource
    actor_user_id: uuid.UUID | None
    correlation_id: str | None
    created_at: datetime
