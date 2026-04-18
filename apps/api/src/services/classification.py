"""Cookie auto-categorisation engine.

Matches discovered cookies against the known_cookies database using exact name
matching, domain matching, and regex patterns. Also checks site-specific
allow-list entries. Returns a classification result with category, vendor, and
confidence level.

Matching priority (highest first):
  1. Site-specific allow-list (exact or pattern match)
  2. Known cookies — exact name + domain match
  3. Known cookies — regex pattern match on name + domain
  4. Unmatched → remains as 'pending'
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cookie import (
    Cookie,
    CookieAllowListEntry,
    CookieCategory,
    KnownCookie,
)


class MatchSource(StrEnum):
    """Where the classification match came from."""

    ALLOW_LIST = "allow_list"
    KNOWN_EXACT = "known_exact"
    KNOWN_REGEX = "known_regex"
    UNMATCHED = "unmatched"


@dataclass
class ClassificationResult:
    """Result of classifying a single cookie."""

    cookie_name: str
    cookie_domain: str
    category_id: uuid.UUID | None = None
    category_slug: str | None = None
    vendor: str | None = None
    description: str | None = None
    match_source: MatchSource = MatchSource.UNMATCHED
    matched: bool = False


async def _load_allow_list(
    db: AsyncSession,
    site_id: uuid.UUID,
) -> list[CookieAllowListEntry]:
    """Load the allow-list entries for a site."""
    result = await db.execute(
        select(CookieAllowListEntry).where(
            CookieAllowListEntry.site_id == site_id,
        )
    )
    return list(result.scalars().all())


async def _load_known_cookies(
    db: AsyncSession,
) -> tuple[list[KnownCookie], list[KnownCookie]]:
    """Load known cookies, split into exact and regex lists."""
    result = await db.execute(select(KnownCookie))
    all_known = list(result.scalars().all())

    exact = [k for k in all_known if not k.is_regex]
    regex = [k for k in all_known if k.is_regex]
    return exact, regex


async def _load_category_map(
    db: AsyncSession,
) -> dict[uuid.UUID, CookieCategory]:
    """Load a mapping of category ID to CookieCategory."""
    result = await db.execute(select(CookieCategory))
    return {cat.id: cat for cat in result.scalars().all()}


def _match_pattern(pattern: str, value: str) -> bool:
    """Check if a value matches a pattern (case-insensitive).

    Patterns support:
      - Exact match (e.g. "_ga")
      - Wildcard with * (e.g. "_ga*", "*.google.com")
      - Regex if it contains regex-specific characters
    """
    if not pattern or not value:
        return False

    pattern_lower = pattern.lower()
    value_lower = value.lower()

    # Simple exact match
    if pattern_lower == value_lower:
        return True

    # Wildcard: convert * to regex .*
    if "*" in pattern_lower:
        regex_pattern = "^" + re.escape(pattern_lower).replace(r"\*", ".*") + "$"
        return bool(re.match(regex_pattern, value_lower))

    return False


def _match_regex(pattern: str, value: str) -> bool:
    """Match a value against a regex pattern (case-insensitive)."""
    try:
        return bool(re.match(pattern, value, re.IGNORECASE))
    except re.error:
        return False


def _match_allow_list(
    cookie_name: str,
    cookie_domain: str,
    allow_list: list[CookieAllowListEntry],
) -> CookieAllowListEntry | None:
    """Check if a cookie matches any allow-list entry."""
    for entry in allow_list:
        name_match = _match_pattern(entry.name_pattern, cookie_name)
        domain_match = _match_pattern(entry.domain_pattern, cookie_domain)
        if name_match and domain_match:
            return entry
    return None


def _match_exact_known(
    cookie_name: str,
    cookie_domain: str,
    exact_known: list[KnownCookie],
) -> KnownCookie | None:
    """Find an exact match in the known cookies database."""
    for known in exact_known:
        name_match = _match_pattern(known.name_pattern, cookie_name)
        domain_match = _match_pattern(known.domain_pattern, cookie_domain)
        if name_match and domain_match:
            return known
    return None


def _match_regex_known(
    cookie_name: str,
    cookie_domain: str,
    regex_known: list[KnownCookie],
) -> KnownCookie | None:
    """Find a regex match in the known cookies database."""
    for known in regex_known:
        name_match = _match_regex(known.name_pattern, cookie_name)
        domain_match = _match_regex(known.domain_pattern, cookie_domain)
        if name_match and domain_match:
            return known
    return None


def classify_cookie(
    cookie_name: str,
    cookie_domain: str,
    allow_list: list[CookieAllowListEntry],
    exact_known: list[KnownCookie],
    regex_known: list[KnownCookie],
    category_map: dict[uuid.UUID, CookieCategory],
) -> ClassificationResult:
    """Classify a single cookie against allow-list and known cookies DB.

    This is a pure function — all data is passed in, no DB calls.
    """
    # 0. ConsentOS's own cookies are always necessary. The banner's
    #    blocker already treats ``_consentos_*`` as exempt; the
    #    classifier must agree so the admin UI shows them in the
    #    right category without requiring a known-cookies DB entry.
    if cookie_name.startswith("_consentos_"):
        necessary = next(
            (cat for cat in category_map.values() if cat.slug == "necessary"),
            None,
        )
        return ClassificationResult(
            cookie_name=cookie_name,
            cookie_domain=cookie_domain,
            category_id=necessary.id if necessary else None,
            category_slug="necessary",
            vendor="ConsentOS",
            description="ConsentOS consent management cookie.",
            match_source=MatchSource.KNOWN_EXACT,
            matched=True,
        )

    # 1. Check allow-list first (site-specific overrides)
    allow_match = _match_allow_list(cookie_name, cookie_domain, allow_list)
    if allow_match:
        cat = category_map.get(allow_match.category_id)
        return ClassificationResult(
            cookie_name=cookie_name,
            cookie_domain=cookie_domain,
            category_id=allow_match.category_id,
            category_slug=cat.slug if cat else None,
            description=allow_match.description,
            match_source=MatchSource.ALLOW_LIST,
            matched=True,
        )

    # 2. Check exact known cookies
    exact_match = _match_exact_known(cookie_name, cookie_domain, exact_known)
    if exact_match:
        cat = category_map.get(exact_match.category_id)
        return ClassificationResult(
            cookie_name=cookie_name,
            cookie_domain=cookie_domain,
            category_id=exact_match.category_id,
            category_slug=cat.slug if cat else None,
            vendor=exact_match.vendor,
            description=exact_match.description,
            match_source=MatchSource.KNOWN_EXACT,
            matched=True,
        )

    # 3. Check regex known cookies
    regex_match = _match_regex_known(cookie_name, cookie_domain, regex_known)
    if regex_match:
        cat = category_map.get(regex_match.category_id)
        return ClassificationResult(
            cookie_name=cookie_name,
            cookie_domain=cookie_domain,
            category_id=regex_match.category_id,
            category_slug=cat.slug if cat else None,
            vendor=regex_match.vendor,
            description=regex_match.description,
            match_source=MatchSource.KNOWN_REGEX,
            matched=True,
        )

    # 4. Unmatched
    return ClassificationResult(
        cookie_name=cookie_name,
        cookie_domain=cookie_domain,
    )


async def classify_site_cookies(
    db: AsyncSession,
    site_id: uuid.UUID,
    *,
    only_pending: bool = True,
) -> list[ClassificationResult]:
    """Classify all cookies for a site against known patterns.

    If only_pending is True, only cookies with review_status='pending'
    and no category are classified.

    Returns a list of results. Also updates matching cookies in the DB.
    """
    # Load lookup data
    allow_list = await _load_allow_list(db, site_id)
    exact_known, regex_known = await _load_known_cookies(db)
    category_map = await _load_category_map(db)

    # Load cookies to classify
    query = select(Cookie).where(Cookie.site_id == site_id)
    if only_pending:
        query = query.where(
            Cookie.review_status == "pending",
            Cookie.category_id.is_(None),
        )
    result = await db.execute(query)
    cookies = list(result.scalars().all())

    results: list[ClassificationResult] = []
    for cookie in cookies:
        cr = classify_cookie(
            cookie.name,
            cookie.domain,
            allow_list,
            exact_known,
            regex_known,
            category_map,
        )
        results.append(cr)

        # Update the cookie if matched
        if cr.matched and cr.category_id:
            cookie.category_id = cr.category_id
            if cr.vendor and not cookie.vendor:
                cookie.vendor = cr.vendor
            if cr.description and not cookie.description:
                cookie.description = cr.description

    await db.flush()
    return results


async def classify_single_cookie(
    db: AsyncSession,
    site_id: uuid.UUID,
    cookie_name: str,
    cookie_domain: str,
) -> ClassificationResult:
    """Classify a single cookie (e.g. for preview/testing)."""
    allow_list = await _load_allow_list(db, site_id)
    exact_known, regex_known = await _load_known_cookies(db)
    category_map = await _load_category_map(db)

    return classify_cookie(
        cookie_name,
        cookie_domain,
        allow_list,
        exact_known,
        regex_known,
        category_map,
    )
