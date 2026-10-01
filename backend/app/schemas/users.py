import uuid

from pydantic import BaseModel, ConfigDict

from app.domain.enums import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
