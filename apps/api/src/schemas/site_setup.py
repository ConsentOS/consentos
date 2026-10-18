import uuid
from typing import Literal

from pydantic import BaseModel


class SetupStep(BaseModel):
    key: Literal["scan", "review", "banner", "publish", "install", "verify"]
    status: Literal["todo", "in_progress", "done"]
    detail: str


class SiteSetupResponse(BaseModel):
    steps: list[SetupStep]
    done: int
    total: int
    complete: bool
    dismissed: bool


class SiteSetupSummary(BaseModel):
    site_id: uuid.UUID
    done: int
    total: int
    complete: bool
    dismissed: bool
