"""The setup checklist: each step worked out from the site's data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from src.services.site_setup import LatestScan, SetupFacts, build_steps, summarise

try:
    from tests.conftest import create_test_site, publish_site, requires_db
except ImportError:
    from conftest import create_test_site, publish_site, requires_db


async def _new_site(client, headers) -> dict:
    with patch("src.tasks.scanner.run_scan.delay"):
        site_id = await create_test_site(client, headers, domain_prefix="setup")
    return (await client.get(f"/api/v1/sites/{site_id}", headers=headers)).json()


async def _setup(client, headers, site_id: str) -> dict:
    resp = await client.get(f"/api/v1/sites/{site_id}/setup", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _statuses(setup: dict) -> dict[str, str]:
    return {step["key"]: step["status"] for step in setup["steps"]}


async def _finish_scan(engine, site_id: str, cookies: dict[str, str]) -> None:
    """Complete the site's scan, having found ``cookies`` (name: review status)."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.cookie import Cookie
    from src.models.scan import ScanJob

    async with AsyncSession(engine) as session:
        await session.execute(
            update(ScanJob)
            .where(ScanJob.site_id == uuid.UUID(site_id))
            .values(status="completed", completed_at=datetime.now(UTC))
        )
        for name, review_status in cookies.items():
            session.add(
                Cookie(
                    site_id=uuid.UUID(site_id),
                    name=name,
                    domain="example.com",
                    review_status=review_status,
                )
            )
        await session.commit()


@requires_db
class TestSiteSetup:
    async def test_a_new_site_starts_with_its_scan_running(self, db_client, auth_headers):
        site = await _new_site(db_client, auth_headers)

        setup = await _setup(db_client, auth_headers, site["id"])

        assert [s["key"] for s in setup["steps"]] == [
            "scan",
            "review",
            "banner",
            "publish",
            "install",
            "verify",
        ]
        assert _statuses(setup) == {
            "scan": "in_progress",
            "review": "todo",
            "banner": "todo",
            "publish": "todo",
            "install": "todo",
            "verify": "todo",
        }
        assert (setup["done"], setup["total"], setup["complete"]) == (0, 6, False)

    async def test_review_counts_cookies_still_needing_a_category(
        self, db_client, auth_headers, _test_engine
    ):
        site = await _new_site(db_client, auth_headers)
        await _finish_scan(_test_engine, site["id"], {"_ga": "pending", "session": "approved"})

        setup = await _setup(db_client, auth_headers, site["id"])

        steps = {s["key"]: s for s in setup["steps"]}
        assert steps["scan"]["status"] == "done"
        assert steps["scan"]["detail"] == "Found 2 cookies."
        assert steps["review"]["status"] == "todo"
        assert steps["review"]["detail"] == "1 of 2 cookies still need a category."

    async def test_review_is_done_when_nothing_is_pending(
        self, db_client, auth_headers, _test_engine
    ):
        site = await _new_site(db_client, auth_headers)
        await _finish_scan(_test_engine, site["id"], {"_ga": "approved", "ads": "rejected"})

        assert _statuses(await _setup(db_client, auth_headers, site["id"]))["review"] == "done"

    async def test_editing_the_banner_completes_its_step(self, db_client, auth_headers):
        site = await _new_site(db_client, auth_headers)
        resp = await db_client.patch(
            f"/api/v1/sites/{site['id']}/config",
            json={"banner_config": {"position": "bottom"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

        assert _statuses(await _setup(db_client, auth_headers, site["id"]))["banner"] == "done"

    async def test_other_config_edits_do_not_complete_the_banner_step(
        self, db_client, auth_headers
    ):
        site = await _new_site(db_client, auth_headers)
        await db_client.patch(
            f"/api/v1/sites/{site['id']}/config",
            json={"scan_schedule_cron": "0 3 * * *"},
            headers=auth_headers,
        )

        assert _statuses(await _setup(db_client, auth_headers, site["id"]))["banner"] == "todo"

    async def test_confirming_the_banner_completes_its_step(self, db_client, auth_headers):
        site = await _new_site(db_client, auth_headers)
        resp = await db_client.post(
            f"/api/v1/sites/{site['id']}/setup/banner-confirmed", headers=auth_headers
        )
        assert resp.status_code == 200
        assert _statuses(resp.json())["banner"] == "done"

    async def test_steps_can_be_done_out_of_order(self, db_client, auth_headers):
        site = await _new_site(db_client, auth_headers)
        await publish_site(db_client, auth_headers, site["id"])

        setup = await _setup(db_client, auth_headers, site["id"])
        statuses = _statuses(setup)
        assert statuses["publish"] == "done"
        assert statuses["scan"] == "in_progress"
        assert next(s for s in setup["steps"] if s["key"] == "publish")["detail"] == "v1 is live."

    async def test_seeing_the_banner_after_publishing_completes_install_and_verify(
        self, db_client, auth_headers
    ):
        site = await _new_site(db_client, auth_headers)
        await publish_site(db_client, auth_headers, site["id"])
        await db_client.get(
            f"/api/v1/config/sites/{site['id']}/geo-resolved",
            headers={"origin": f"https://{site['domain']}"},
        )

        statuses = _statuses(await _setup(db_client, auth_headers, site["id"]))
        assert statuses["install"] == "done"
        assert statuses["verify"] == "done"

    async def test_dismissing_is_refused_until_complete(self, db_client, auth_headers):
        site = await _new_site(db_client, auth_headers)
        resp = await db_client.post(
            f"/api/v1/sites/{site['id']}/setup/dismiss", headers=auth_headers
        )
        assert resp.status_code == 409

    async def test_a_complete_checklist_can_be_dismissed_and_stays_dismissed(
        self, db_client, auth_headers, _test_engine
    ):
        site = await _new_site(db_client, auth_headers)
        await _finish_scan(_test_engine, site["id"], {})
        await publish_site(db_client, auth_headers, site["id"])
        await db_client.get(
            f"/api/v1/config/sites/{site['id']}/geo-resolved",
            headers={"origin": f"https://{site['domain']}"},
        )
        assert (await _setup(db_client, auth_headers, site["id"]))["complete"] is True

        resp = await db_client.post(
            f"/api/v1/sites/{site['id']}/setup/dismiss", headers=auth_headers
        )
        assert resp.status_code == 200
        assert (await _setup(db_client, auth_headers, site["id"]))["dismissed"] is True

    async def test_the_summary_shows_each_sites_progress(
        self, db_client, auth_headers, _test_engine
    ):
        started = await _new_site(db_client, auth_headers)
        further = await _new_site(db_client, auth_headers)
        await _finish_scan(_test_engine, further["id"], {})
        await publish_site(db_client, auth_headers, further["id"])

        resp = await db_client.get("/api/v1/sites/setup-summary", headers=auth_headers)
        assert resp.status_code == 200
        done = {row["site_id"]: row["done"] for row in resp.json()}
        assert done[started["id"]] == 0
        # Scan, review (nothing found), banner (published) and publish.
        assert done[further["id"]] == 4

    async def test_other_organisations_cannot_see_it(
        self, db_client, auth_headers, other_org_headers
    ):
        site = await _new_site(db_client, auth_headers)
        resp = await db_client.get(f"/api/v1/sites/{site['id']}/setup", headers=other_org_headers)
        assert resp.status_code == 404


# ── Steps from facts ─────────────────────────────────────────────────

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def _facts(**overrides) -> SetupFacts:
    values = {
        "latest_scan": None,
        "has_completed_scan": False,
        "cookies_total": 0,
        "cookies_pending": 0,
        "banner_confirmed": False,
        "live_number": None,
        "published_at": None,
        "installation": None,
        "dismissed": False,
    }
    return SetupFacts(**{**values, **overrides})


def _installation(**values):
    defaults = {"last_seen_at": None, "last_check_at": None, "last_check": None}
    return SimpleNamespace(**{**defaults, **values})


def _step(facts: SetupFacts, key: str) -> dict:
    return next(s for s in build_steps(facts) if s["key"] == key)


class TestBuildSteps:
    def test_scan_progress(self):
        scan = LatestScan(
            status="running", pages_scanned=3, pages_total=12, cookies_found=1, error_message=None
        )
        step = _step(_facts(latest_scan=scan), "scan")
        assert step == {
            "key": "scan",
            "status": "in_progress",
            "detail": "Scanned 3 of 12 pages, 1 cookie found so far.",
        }

    def test_a_failed_scan_asks_to_start_again(self):
        scan = LatestScan(
            status="failed", pages_scanned=0, pages_total=50, cookies_found=0, error_message="x"
        )
        step = _step(_facts(latest_scan=scan), "scan")
        assert step["status"] == "todo"
        assert "Start it again" in step["detail"]

    def test_a_rescan_does_not_undo_a_finished_scan_step(self):
        scan = LatestScan(
            status="failed", pages_scanned=0, pages_total=50, cookies_found=0, error_message="x"
        )
        assert _step(_facts(latest_scan=scan, has_completed_scan=True), "scan")["status"] == "done"

    def test_verify_needs_the_banner_seen_after_publishing(self):
        published = NOW - timedelta(hours=1)
        before = _installation(last_seen_at=published - timedelta(minutes=5))
        after = _installation(last_seen_at=published + timedelta(minutes=5))

        assert _step(_facts(published_at=published, installation=before), "verify")["status"] == (
            "todo"
        )
        assert _step(_facts(published_at=published, installation=after), "verify")["status"] == (
            "done"
        )

    def test_a_passing_check_verifies(self):
        installation = _installation(last_check_at=NOW, last_check={"ok": True})
        facts = _facts(installation=installation)
        assert _step(facts, "verify")["status"] == "done"
        assert _step(facts, "install")["status"] == "done"

    def test_a_problem_blocks_verify(self):
        installation = _installation(
            last_seen_at=NOW - timedelta(hours=1), last_check_at=NOW, last_check={"ok": False}
        )
        step = _step(
            _facts(installation=installation, published_at=NOW - timedelta(days=1)), "verify"
        )
        assert step == {
            "key": "verify",
            "status": "todo",
            "detail": "The last check found a problem.",
        }

    def test_a_scan_that_found_nothing_leaves_nothing_to_review(self):
        step = _step(_facts(has_completed_scan=True), "review")
        assert step == {"key": "review", "status": "done", "detail": "No cookies to review."}

    def test_summary_counts_done_steps(self):
        summary = summarise(_facts(banner_confirmed=True, live_number=2, published_at=NOW))
        assert (summary["done"], summary["complete"]) == (2, False)
