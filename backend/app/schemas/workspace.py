import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cases import CaseFilters


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(min_length=1, max_length=4000)


class HandoffCreate(NoteCreate):
    assigned_to_user_id: uuid.UUID


class ViewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    filters: CaseFilters


class ViewRead(ViewCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class DraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    body: str
    provider: str
    created_at: datetime
    approved_at: datetime | None
    approved_by_user_id: uuid.UUID | None
    version: int


class DraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=8000)
    version: int = Field(ge=1)
    approve: bool = False


class DeadlineNotice(BaseModel):
    case_id: uuid.UUID
    reference: str
    subject: str
    deadline: str
    deadline_at: datetime
    overdue: bool
