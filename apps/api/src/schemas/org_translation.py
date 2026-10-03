import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrgTranslationCreate(BaseModel):
    locale: str = Field(min_length=2, max_length=10)
    strings: dict[str, str]


class OrgTranslationUpdate(BaseModel):
    strings: dict[str, str]


class OrgTranslationResponse(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    locale: str
    strings: dict[str, str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
