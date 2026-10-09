import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrganisationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    contact_email: str | None = None


class OrganisationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_email: str | None = None


class OrganisationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    contact_email: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
