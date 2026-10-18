import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    # The draft hash the publisher reviewed, from ``GET .../draft``.
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str | None = Field(default=None, max_length=500)


class RevisionSummary(BaseModel):
    id: uuid.UUID
    number: int
    content_hash: str
    note: str | None
    published_by: uuid.UUID | None
    published_at: datetime

    model_config = {"from_attributes": True}


class ChangedSource(BaseModel):
    kind: str
    id: str


class DraftStatusResponse(BaseModel):
    live_revision: RevisionSummary | None
    content_hash: str
    has_unpublished_changes: bool
    # Parent layers that changed since the live revision was published.
    changed_sources: list[ChangedSource]
