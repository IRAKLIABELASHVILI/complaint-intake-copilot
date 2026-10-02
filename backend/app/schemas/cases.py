"""API request and response models.

C# comparison: these are DTOs with validation attributes. Pydantic validates on the way in
(422 with field errors on failure) and serialises on the way out. They also generate the
OpenAPI schema, which milestone 6 turns into a typed TypeScript client.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.enums import (
    AuditSource,
    CaseStatus,
    Category,
    IndicatorDecision,
    IndicatorSource,
    IndicatorType,
    Priority,
    ResolutionType,
    VulnerabilityDriver,
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


class CategoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category


class PriorityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Priority


class IndicatorDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal[IndicatorDecision.CONFIRMED, IndicatorDecision.REJECTED]


class IndicatorCreate(BaseModel):
    """A vulnerability indicator the AI missed. The quote must be in the complaint."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    indicator_type: IndicatorType
    evidence_quote: str = Field(min_length=3, max_length=500)


class SuggestionRead(BaseModel):
    """What the AI suggested. The case's final_* fields hold what a person decided."""

    model_config = ConfigDict(from_attributes=True)

    suggested_category: Category | None
    summary: str | None
    suggested_priority: Priority | None
    provider: str
    model: str
    created_at: datetime


class IndicatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    indicator_type: IndicatorType
    driver: VulnerabilityDriver
    evidence_quote: str
    source: IndicatorSource
    decision: IndicatorDecision
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None


class DeadlineProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    deadline_at: datetime
    business_days_remaining: int = Field(description="0 = due today; negative = days overdue")
    is_overdue: bool


class DeadlineTrackingRead(BaseModel):
    """Calculated on every read, because it depends on today's date (US-4.6, US-4.7)."""

    model_config = ConfigDict(from_attributes=True)

    src: DeadlineProgressRead | None = Field(description="Null once the case is resolved")
    final_response: DeadlineProgressRead | None = Field(
        description="Null once the case is resolved"
    )
    resolved_in_time: bool | None = Field(description="Null while the case is open")


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
    deadline_tracking: DeadlineTrackingRead | None = None
    suggestion: SuggestionRead | None = Field(
        default=None, description="Null until the analysis completes (US-2.4)"
    )
    review_reason: str | None = Field(
        default=None, description="Why the case needs a person, when its status says so"
    )
    vulnerability_indicators: list[IndicatorRead] = Field(default_factory=list)


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
    deadline_tracking: DeadlineTrackingRead | None = None


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
