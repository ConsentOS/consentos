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


class RollbackRequest(BaseModel):
    # Gives the new revision a new consent version, so returning visitors
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


class RevisionListItem(RevisionSummary):
    is_live: bool
    published_by_name: str | None
    rolled_back_from_id: uuid.UUID | None
    rolled_back_from_number: int | None


class RevisionList(BaseModel):
    items: list[RevisionListItem]
    total: int


class RevisionDetail(RevisionListItem):
    snapshot: dict
    sources: list[dict]
    # What rolling back to this revision would change that visitors
    # consented to, compared with the live revision. Non-empty means
    # asking visitors again is recommended.
    rollback_reconsent_reasons: list[str]


class ChangedSource(BaseModel):
    kind: str
    id: str


class LastAttempt(BaseModel):
    action: str
    status: str
    error_code: str | None
    error_message: str | None
    attempted_at: datetime
    attempted_by_name: str | None
    # The revision a successful attempt made live.
    revision_number: int | None


class DraftStatusResponse(BaseModel):
    live_revision: RevisionSummary | None
    content_hash: str
    has_unpublished_changes: bool
    # Parent layers that changed since the live revision was published.
    changed_sources: list[ChangedSource]
    # Changes to what visitors consented to: "categories", "purposes" or
    # "vendors". Non-empty means asking visitors again is recommended.
    reconsent_reasons: list[str]
    last_attempt: LastAttempt | None
