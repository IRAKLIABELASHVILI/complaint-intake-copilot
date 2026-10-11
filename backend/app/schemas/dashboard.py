"""The team lead dashboard (US-5). Every number counts open cases of the user's tenant only."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Category, IndicatorType, VulnerabilityDriver


class DeadlineCountsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at_risk: int = Field(description="Not missed yet, with at_risk_business_days or fewer left")
    overdue: int = Field(description="Past the deadline")


class CategoryCountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: Category
    decided: int = Field(description="Cases a person put in this category")
    suggested: int = Field(description="Cases only the AI put in this category, not decided yet")


class VulnerabilityCountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    indicator_type: IndicatorType
    driver: VulnerabilityDriver
    cases: int = Field(description="Open cases with at least one confirmed indicator of the type")


class AssigneeCountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: uuid.UUID | None
    display_name: str
    open_cases: int


class DashboardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignments: list[AssigneeCountRead]
    generated_at: datetime
    open_cases: int
    at_risk_business_days: int
    summary_resolution: DeadlineCountsRead = Field(
        description="The SRC deadline (DISP 1.5). Missing it is not a breach: the case then "
        "needs a final response instead."
    )
    final_response: DeadlineCountsRead = Field(
        description="The 8-week final response deadline (DISP 1.6). Overdue = a breach."
    )
    categories: list[CategoryCountRead] = Field(description="Every category, in a fixed order")
    uncategorised: int = Field(description="Open cases with no decided or suggested category")
    vulnerabilities: list[VulnerabilityCountRead] = Field(
        description="Every indicator type, confirmed indicators only"
    )
