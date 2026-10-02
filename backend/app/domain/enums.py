"""Domain enumerations. Values are what gets stored in the database and returned by the API.

StrEnum members compare equal to their string value: CaseStatus.NEW == "new".
"""

from enum import StrEnum


class UserRole(StrEnum):
    HANDLER = "handler"
    TEAM_LEAD = "team_lead"


class CaseStatus(StrEnum):
    NEW = "new"
    ANALYSING = "analysing"
    AWAITING_REVIEW = "awaiting_review"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class Category(StrEnum):
    FEES_AND_CHARGES = "fees_and_charges"
    SERVICE_QUALITY = "service_quality"
    ACCOUNT_ADMINISTRATION = "account_administration"
    PAYMENTS_AND_TRANSFERS = "payments_and_transfers"
    LENDING_AND_AFFORDABILITY = "lending_and_affordability"
    FRAUD_AND_SCAMS = "fraud_and_scams"
    ADVICE_AND_MIS_SELLING = "advice_and_mis_selling"
    COLLECTIONS_AND_ARREARS = "collections_and_arrears"
    OTHER = "other"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AnalysisStatus(StrEnum):
    COMPLETED = "completed"
    INVALID_OUTPUT = "invalid_output"  # the model answered, but the answer failed validation
    FAILED = "failed"  # no usable attempt: redaction failed, or the job was given up


class IndicatorType(StrEnum):
    PHYSICAL_ILLNESS = "physical_illness"
    MENTAL_HEALTH = "mental_health"
    DISABILITY = "disability"
    BEREAVEMENT = "bereavement"
    RELATIONSHIP_BREAKDOWN = "relationship_breakdown"
    JOB_LOSS = "job_loss"
    FINANCIAL_HARDSHIP = "financial_hardship"
    LOW_CAPABILITY = "low_capability"  # literacy, language, digital skills


class VulnerabilityDriver(StrEnum):
    """The four drivers of vulnerability in FCA FG21/1."""

    HEALTH = "health"
    LIFE_EVENTS = "life_events"
    RESILIENCE = "resilience"
    CAPABILITY = "capability"


class IndicatorSource(StrEnum):
    AI = "ai"
    HANDLER = "handler"


class IndicatorDecision(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ResolutionType(StrEnum):
    SUMMARY_RESOLUTION = "src"
    FINAL_RESPONSE = "final_response"


class BankHolidayRegion(StrEnum):
    """UK bank holidays differ by region. Values match the keys of the gov.uk feed."""

    ENGLAND_AND_WALES = "england-and-wales"
    SCOTLAND = "scotland"
    NORTHERN_IRELAND = "northern-ireland"


class AuditSource(StrEnum):
    SYSTEM = "system"
    ACCEPTED_SUGGESTION = "accepted_suggestion"
    OVERRIDE = "override"
    HANDLER = "handler"
