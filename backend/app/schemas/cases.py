"""API request and response models.

C# comparison: these are DTOs with validation attributes. Pydantic validates on the way in
(422 with field errors on failure) and serialises on the way out. They also generate the
OpenAPI schema, which milestone 6 turns into a typed TypeScript client.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.domain.enums import (
    AuditSource,
    CaseStatus,
    Category,
    DeadlineKind,
    DeadlineRisk,
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
            raise ValueError("cannot be in the future")  # the field name is reported alongside
        return value


class CaseAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to_user_id: uuid.UUID | None
    only_if_unassigned: bool = False


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
    assigned_to_display_name: str | None = None
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
    assigned_to_display_name: str | None = None
    src_deadline_at: datetime | None
    final_response_deadline_at: datetime | None
    deadline_tracking: DeadlineTrackingRead | None = None
    open_vulnerability_flags: int = Field(
        default=0, description="Indicators not rejected: pending or confirmed"
    )


class CaseFilters(BaseModel):
    assigned_to_user_id: uuid.UUID | None = None
    unassigned: bool = False

    """Query string filters of the case list. Each one narrows the list; they combine with AND.

    The dashboard (US-5.4) links every number to the list with the matching filters.
    """

    status: CaseStatus | None = None
    open_only: bool = Field(
        default=False, alias="open", description="Only cases that are not resolved"
    )
    deadline: DeadlineKind | None = Field(
        default=None, description="Which deadline `deadline_risk` applies to"
    )
    deadline_risk: DeadlineRisk | None = Field(
        default=None,
        description="at_risk: 2 business days or fewer left; overdue: past the deadline. "
        "Only open cases match.",
    )
    final_category: Category | None = Field(default=None, description="Decided by a person")
    suggested_category: Category | None = Field(
        default=None, description="Suggested by the AI, on cases no person has categorised yet"
    )
    uncategorised: bool = Field(
        default=False, description="Cases with no decided and no suggested category yet"
    )
    vulnerability: IndicatorType | None = Field(
        default=None, description="Cases with a confirmed indicator of this type"
    )

    @model_validator(mode="after")
    def deadline_needs_both_parts(self) -> "CaseFilters":
        if (self.deadline is None) != (self.deadline_risk is None):
            raise ValueError("deadline and deadline_risk must be given together")
        return self


class CaseListQuery(CaseFilters):
    """The whole query string of `GET /cases`. FastAPI expands a model into separate query
    parameters only when it is the endpoint's one query parameter, so paging lives here too."""

    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


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


class CaseResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_type: ResolutionType
    note: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def require_note(self) -> "CaseResolve":
        self.note = self.note.strip()
        if not self.note:
            raise ValueError("A resolution note is required")
        return self
