"""Pydantic schemas for the per-site consent analytics dashboard.

The dashboard summarises consent decisions into three headline buckets
that map onto the :class:`~src.schemas.consent.ConsentAction` enum:

* **accept**  → ``accept_all``  (every category granted)
* **partial** → ``custom``      (some categories granted)
* **decline** → ``reject_all``  (only strictly-necessary granted)

``withdraw`` events are tracked separately and excluded from rate
calculations, since a withdrawal is not an initial consent decision.
"""

import uuid
from datetime import date

from pydantic import BaseModel


class ActionBreakdown(BaseModel):
    """Raw counts of each consent action over the requested window."""

    accept_all: int = 0
    reject_all: int = 0
    custom: int = 0
    withdraw: int = 0


class CategoryRate(BaseModel):
    """Acceptance vs rejection counts for a single cookie category."""

    category: str
    accepted: int
    rejected: int
    rate: float


class ConsentRatesResponse(BaseModel):
    """Headline consent breakdown for a site over a date window."""

    site_id: uuid.UUID
    total_records: int
    consent_rate: float
    action_breakdown: ActionBreakdown
    category_rates: list[CategoryRate]
    from_date: date
    to_date: date


class TrendPoint(BaseModel):
    """A single period in the consent-trend time series."""

    period: date
    total: int
    accept_all: int
    reject_all: int
    custom: int
    consent_rate: float


class ConsentTrendsResponse(BaseModel):
    """Consent decisions bucketed over time for charting."""

    site_id: uuid.UUID
    granularity: str
    data: list[TrendPoint]
    from_date: date
    to_date: date
