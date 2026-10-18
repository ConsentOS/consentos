import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    # The draft hash the publisher reviewed, from ``GET .../draft``.
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str | None = Field(default=None, max_length=500)
    # Gives the revision a new consent version, so returning visitors
    # are asked to consent again.
    ask_visitors_again: bool = False


class RevisionSummary(BaseModel):
    id: uuid.UUID
    number: int
    content_hash: str
    consent_version: uuid.UUID
    requires_reconsent: bool
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
    # Changes to what visitors consented to: "categories", "purposes" or
    # "vendors". Non-empty means asking visitors again is recommended.
    reconsent_reasons: list[str]
