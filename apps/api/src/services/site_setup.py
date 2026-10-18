"""The setup checklist that guides a new site to a working banner.

Each step's state is worked out from the site's data, so it stays right
however the owner gets there and in whatever order. The one exception is
"Set up your banner", which records when the owner confirms or edits the
banner, since nothing else shows they have looked at it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cookie import Cookie
from src.models.scan import ScanJob
from src.models.site import Site
from src.models.site_config_revision import SiteConfigRevision
from src.models.site_installation import SiteInstallation
from src.services.installation import installation_state

StepKey = Literal["scan", "review", "banner", "publish", "install", "verify"]
StepStatus = Literal["todo", "in_progress", "done"]

STEP_ORDER: tuple[StepKey, ...] = ("scan", "review", "banner", "publish", "install", "verify")


@dataclass
class LatestScan:
    status: str
    pages_scanned: int
    pages_total: int | None
    cookies_found: int
    error_message: str | None


@dataclass
class SetupFacts:
    """What the checklist needs to know about one site."""

    latest_scan: LatestScan | None
    has_completed_scan: bool
    cookies_total: int
    cookies_pending: int
    banner_confirmed: bool
    live_number: int | None
    published_at: datetime | None
    installation: SiteInstallation | None
    dismissed: bool


def _step(key: StepKey, status: StepStatus, detail: str) -> dict:
    return {"key": key, "status": status, "detail": detail}


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _scan_step(facts: SetupFacts) -> dict:
    scan = facts.latest_scan
    if scan is not None and scan.status in ("pending", "running"):
        if scan.status == "running" and scan.pages_scanned and scan.pages_total:
            detail = (
                f"Scanned {scan.pages_scanned} of {scan.pages_total} pages, "
                f"{_plural(scan.cookies_found, 'cookie')} found so far."
            )
        else:
            detail = "Scanning your site for cookies."
        return _step("scan", "in_progress", detail)
    if facts.has_completed_scan:
        return _step("scan", "done", f"Found {_plural(facts.cookies_total, 'cookie')}.")
    if scan is not None and scan.status == "failed":
        return _step("scan", "todo", "The last scan didn't finish. Start it again.")
    return _step("scan", "todo", "Scan your site to find the cookies it sets.")


def _review_step(facts: SetupFacts) -> dict:
    if not facts.has_completed_scan and facts.cookies_total == 0:
        return _step("review", "todo", "Waiting for the first scan to finish.")
    if facts.cookies_total == 0:
        return _step("review", "done", "No cookies to review.")
    if facts.cookies_pending == 0:
        return _step("review", "done", f"All {_plural(facts.cookies_total, 'cookie')} reviewed.")
    return _step(
        "review",
        "todo",
        f"{facts.cookies_pending} of {_plural(facts.cookies_total, 'cookie')} still need "
        "a category.",
    )


def _verify_step(facts: SetupFacts) -> dict:
    installation = facts.installation
    state = installation_state(installation)
    if state == "problem":
        return _step("verify", "todo", "The last check found a problem.")
    check_ok = bool(installation and installation.last_check and installation.last_check.get("ok"))
    # Seeing the banner since the live version was published shows visitors
    # are getting it, which is what this step confirms.
    seen_live = bool(
        installation
        and installation.last_seen_at
        and facts.published_at
        and installation.last_seen_at >= facts.published_at
    )
    if check_ok or seen_live:
        return _step("verify", "done", "Your banner is working.")
    return _step("verify", "todo", "Check your site to confirm the banner is working.")


def build_steps(facts: SetupFacts) -> list[dict]:
    """The checklist's steps, in order, each with its status."""
    installation = facts.installation
    seen = bool(installation and installation.last_seen_at)
    check_ok = bool(installation and installation.last_check and installation.last_check.get("ok"))
    banner_done = facts.banner_confirmed or facts.live_number is not None
    return [
        _scan_step(facts),
        _review_step(facts),
        _step(
            "banner",
            "done" if banner_done else "todo",
            "Your banner is set up." if banner_done else "Check how your banner looks and reads.",
        ),
        _step(
            "publish",
            "done" if facts.live_number is not None else "todo",
            f"v{facts.live_number} is live."
            if facts.live_number is not None
            else "Preview your banner and publish it.",
        ),
        _step(
            "install",
            "done" if seen or check_ok else "todo",
            "The banner is on your site."
            if seen or check_ok
            else "Add the snippet to your site's pages.",
        ),
        _verify_step(facts),
    ]


def summarise(facts: SetupFacts) -> dict:
    steps = build_steps(facts)
    done = sum(1 for s in steps if s["status"] == "done")
    return {
        "steps": steps,
        "done": done,
        "total": len(steps),
        "complete": done == len(steps),
        "dismissed": facts.dismissed,
    }


async def load_setup_facts(db: AsyncSession, sites: list[Site]) -> dict[uuid.UUID, SetupFacts]:
    """Gather the checklist's facts for several sites in a fixed number of queries."""
    site_ids = [s.id for s in sites]
    if not site_ids:
        return {}

    latest_rows = await db.execute(
        select(
            ScanJob.site_id,
            ScanJob.status,
            ScanJob.pages_scanned,
            ScanJob.pages_total,
            ScanJob.cookies_found,
            ScanJob.error_message,
        )
        .where(ScanJob.site_id.in_(site_ids))
        .distinct(ScanJob.site_id)
        .order_by(ScanJob.site_id, ScanJob.created_at.desc())
    )
    latest = {
        row.site_id: LatestScan(
            status=row.status,
            pages_scanned=row.pages_scanned,
            pages_total=row.pages_total,
            cookies_found=row.cookies_found,
            error_message=row.error_message,
        )
        for row in latest_rows
    }

    completed_rows = await db.execute(
        select(ScanJob.site_id)
        .where(ScanJob.site_id.in_(site_ids), ScanJob.status == "completed")
        .group_by(ScanJob.site_id)
    )
    completed = {row.site_id for row in completed_rows}

    cookie_rows = await db.execute(
        select(
            Cookie.site_id,
            func.count().label("total"),
            func.sum(case((Cookie.review_status == "pending", 1), else_=0)).label("pending"),
        )
        .where(Cookie.site_id.in_(site_ids))
        .group_by(Cookie.site_id)
    )
    cookies = {row.site_id: (row.total, int(row.pending or 0)) for row in cookie_rows}

    live_ids = [s.live_revision_id for s in sites if s.live_revision_id]
    revisions: dict[uuid.UUID, tuple[int, datetime]] = {}
    if live_ids:
        revision_rows = await db.execute(
            select(
                SiteConfigRevision.id,
                SiteConfigRevision.number,
                SiteConfigRevision.published_at,
            ).where(SiteConfigRevision.id.in_(live_ids))
        )
        revisions = {row.id: (row.number, row.published_at) for row in revision_rows}

    installation_rows = await db.execute(
        select(SiteInstallation).where(SiteInstallation.site_id.in_(site_ids))
    )
    installations = {i.site_id: i for i in installation_rows.scalars()}

    facts: dict[uuid.UUID, SetupFacts] = {}
    for site in sites:
        total, pending = cookies.get(site.id, (0, 0))
        number, published_at = revisions.get(site.live_revision_id, (None, None))
        facts[site.id] = SetupFacts(
            latest_scan=latest.get(site.id),
            has_completed_scan=site.id in completed,
            cookies_total=total,
            cookies_pending=pending,
            banner_confirmed=site.banner_confirmed_at is not None,
            live_number=number,
            published_at=published_at,
            installation=installations.get(site.id),
            dismissed=site.setup_dismissed_at is not None,
        )
    return facts
