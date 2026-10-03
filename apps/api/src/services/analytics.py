"""Aggregation logic for the per-site consent analytics dashboard.

Queries are deliberately set-based (``GROUP BY`` in the database rather
than loading rows into Python) so they scale with the partitioned
``consent_records`` table and lean on the
``ix_consent_records_site_consented_at`` composite index.
"""

import json
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, and_, case, cast, func, literal, not_, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.consent import ConsentRecord
from src.models.cookie import CookieCategory
from src.schemas.analytics import (
    ActionBreakdown,
    CategoryRate,
    ConsentRatesResponse,
    ConsentTrendsResponse,
    TrendPoint,
)

# Granularities accepted by ``date_trunc`` for the trend endpoint.
VALID_GRANULARITIES = ("day", "week", "month")

# Fallback essential category when the taxonomy table is empty.
_DEFAULT_ESSENTIAL = "necessary"


def rate(granted: int, decisions: int) -> float:
    """Share of consent *decisions* that granted at least one non-essential
    category. Returns a value in [0, 1] rounded to four decimals; zero
    decisions yields 0.0.
    """
    if decisions <= 0:
        return 0.0
    return round(granted / decisions, 4)


def merge_category_rates(
    accepted: dict[str, int],
    rejected: dict[str, int],
) -> list[CategoryRate]:
    """Combine per-category accept/reject tallies into sorted rates."""
    rates: list[CategoryRate] = []
    for category in sorted(set(accepted) | set(rejected)):
        acc = accepted.get(category, 0)
        rej = rejected.get(category, 0)
        denom = acc + rej
        rates.append(
            CategoryRate(
                category=category,
                accepted=acc,
                rejected=rej,
                rate=round(acc / denom, 4) if denom else 0.0,
            )
        )
    return rates


def _window(days: int) -> tuple[datetime, date, date]:
    """Return (start_datetime, from_date, to_date) for a trailing window."""
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    return start, start.date(), now.date()


async def _essential_slugs(db: AsyncSession) -> list[str]:
    """Cookie category slugs flagged as strictly necessary."""
    rows = (
        await db.execute(select(CookieCategory.slug).where(CookieCategory.is_essential.is_(True)))
    ).all()
    return [row[0] for row in rows] or [_DEFAULT_ESSENTIAL]


def _granted_clause(essentials: list[str]):
    """SQL predicate: a real decision that granted a non-essential category.

    ``categories_accepted <@ essentials`` is true when the visitor accepted
    *only* essential categories (or nothing), so its negation marks records
    that granted something beyond strictly necessary. Withdrawals are
    excluded — a revocation is not an initial decision.
    """
    essentials_json = cast(literal(json.dumps(essentials)), JSONB)
    return and_(
        ConsentRecord.action != "withdraw",
        not_(ConsentRecord.categories_accepted.op("<@")(essentials_json)),
    )


async def _action_counts(
    db: AsyncSession,
    site_id: uuid.UUID,
    start: datetime,
) -> dict[str, int]:
    """Count consent records grouped by action within the window."""
    rows = (
        await db.execute(
            select(ConsentRecord.action, func.count())
            .where(
                ConsentRecord.site_id == site_id,
                ConsentRecord.consented_at >= start,
            )
            .group_by(ConsentRecord.action)
        )
    ).all()
    return {action: count for action, count in rows}


async def _category_rates(
    db: AsyncSession,
    site_id: uuid.UUID,
    start: datetime,
) -> list[CategoryRate]:
    """Tally per-category acceptance vs rejection by unnesting JSONB arrays.

    Withdrawals are excluded: a revocation auto-populates ``categories_rejected``
    with every category, which would otherwise inflate rejection counts.
    """

    async def _tally(column) -> dict[str, int]:
        # LATERAL unnest so the set-returning function can reference the
        # row's JSONB column; consent_records must precede it in FROM.
        element = func.jsonb_array_elements_text(column).table_valued("value").lateral()
        rows = (
            await db.execute(
                select(element.c.value, func.count())
                .select_from(ConsentRecord)
                .join(element, true())
                .where(
                    ConsentRecord.site_id == site_id,
                    ConsentRecord.consented_at >= start,
                    ConsentRecord.action != "withdraw",
                )
                .group_by(element.c.value)
            )
        ).all()
        return {category: count for category, count in rows}

    accepted = await _tally(ConsentRecord.categories_accepted)
    rejected = await _tally(ConsentRecord.categories_rejected)
    return merge_category_rates(accepted, rejected)


async def compute_consent_rates(
    db: AsyncSession,
    site_id: uuid.UUID,
    days: int,
) -> ConsentRatesResponse:
    """Headline accept / partial / decline breakdown for a site."""
    start, from_date, to_date = _window(days)
    counts = await _action_counts(db, site_id, start)
    breakdown = ActionBreakdown(
        accept_all=counts.get("accept_all", 0),
        reject_all=counts.get("reject_all", 0),
        custom=counts.get("custom", 0),
        withdraw=counts.get("withdraw", 0),
    )
    decisions = breakdown.accept_all + breakdown.reject_all + breakdown.custom

    essentials = await _essential_slugs(db)
    granted = (
        await db.scalar(
            select(func.count())
            .select_from(ConsentRecord)
            .where(
                ConsentRecord.site_id == site_id,
                ConsentRecord.consented_at >= start,
                _granted_clause(essentials),
            )
        )
    ) or 0

    category_rates = await _category_rates(db, site_id, start)
    return ConsentRatesResponse(
        site_id=site_id,
        total_records=sum(counts.values()),
        consent_rate=rate(granted, decisions),
        action_breakdown=breakdown,
        category_rates=category_rates,
        from_date=from_date,
        to_date=to_date,
    )


async def compute_consent_trends(
    db: AsyncSession,
    site_id: uuid.UUID,
    days: int,
    granularity: str,
) -> ConsentTrendsResponse:
    """Consent decisions bucketed into a ``granularity`` time series."""
    start, from_date, to_date = _window(days)
    essentials = await _essential_slugs(db)
    granted_int = case((_granted_clause(essentials), 1), else_=0)
    # Truncate in UTC so day/week/month buckets are independent of the
    # database session timezone.
    period = cast(
        func.date_trunc(granularity, func.timezone("UTC", ConsentRecord.consented_at)),
        Date,
    ).label("period")
    rows = (
        await db.execute(
            select(period, ConsentRecord.action, func.count(), func.sum(granted_int))
            .where(
                ConsentRecord.site_id == site_id,
                ConsentRecord.consented_at >= start,
            )
            .group_by(period, ConsentRecord.action)
            .order_by(period)
        )
    ).all()

    counts_by_period: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    granted_by_period: dict[date, int] = defaultdict(int)
    for bucket_date, action, count, granted_sum in rows:
        counts_by_period[bucket_date][action] += count
        granted_by_period[bucket_date] += int(granted_sum or 0)

    data: list[TrendPoint] = []
    for bucket_date in sorted(counts_by_period):
        counts = counts_by_period[bucket_date]
        accept_all = counts.get("accept_all", 0)
        reject_all = counts.get("reject_all", 0)
        custom = counts.get("custom", 0)
        data.append(
            TrendPoint(
                period=bucket_date,
                total=sum(counts.values()),
                accept_all=accept_all,
                reject_all=reject_all,
                custom=custom,
                consent_rate=rate(granted_by_period[bucket_date], accept_all + reject_all + custom),
            )
        )

    return ConsentTrendsResponse(
        site_id=site_id,
        granularity=granularity,
        data=data,
        from_date=from_date,
        to_date=to_date,
    )
