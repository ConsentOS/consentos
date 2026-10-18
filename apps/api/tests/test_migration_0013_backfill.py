"""Tests for the v1 backfill in migration 0013.

Each test runs inside a transaction that is rolled back, so the backfill
only ever sees the sites the test creates.
"""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cookie import Cookie, CookieAllowListEntry, CookieCategory
from src.models.org_config import OrgConfig
from src.models.organisation import Organisation
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.models.site_config_revision import SiteConfigRevision
from src.models.site_group import SiteGroup
from src.models.site_group_config import SiteGroupConfig
from src.models.translation import Translation
from src.services.config_publishing import get_draft_status
from src.services.config_snapshot import build_site_snapshot
from tests.conftest import requires_db

_MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "0013_site_config_revisions.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0013", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


@pytest_asyncio.fixture(loop_scope="session")
async def session(_test_engine, _setup_db):
    async with _test_engine.connect() as conn:
        transaction = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()


async def _site(db: AsyncSession, org: Organisation, *, group=None, config=True, **site) -> Site:
    created = Site(
        organisation_id=org.id,
        domain=f"mig-{uuid.uuid4().hex[:8]}.com",
        display_name="Migrated",
        site_group_id=group.id if group else None,
        **site,
    )
    db.add(created)
    await db.flush()
    if config:
        db.add(SiteConfig(site_id=created.id, privacy_policy_url="https://mig.test/privacy"))
        await db.flush()
    return created


async def _backfill(db: AsyncSession) -> None:
    conn = await db.connection()
    await conn.run_sync(migration.backfill_initial_revisions)


async def _live(db: AsyncSession, site: Site) -> SiteConfigRevision | None:
    return (
        await db.execute(
            select(SiteConfigRevision)
            .join(Site, Site.live_revision_id == SiteConfigRevision.id)
            .where(Site.id == site.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


@requires_db
class TestBackfill:
    async def test_matches_the_app_snapshot_and_keeps_consent(self, session):
        db = session
        org = Organisation(name="Migration Org", slug=f"mig-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        db.add(OrgConfig(organisation_id=org.id, consent_expiry_days=180, terms_url="https://t"))
        group = SiteGroup(organisation_id=org.id, name="Brands")
        db.add(group)
        await db.flush()
        db.add(
            SiteGroupConfig(
                site_group_id=group.id,
                consent_sharing_enabled=True,
                regional_modes={"US-CA": "opt_out", "DEFAULT": "opt_in"},
                enabled_categories=["analytics", "necessary"],
            )
        )
        site = await _site(db, org, group=group)
        analytics = (
            await db.execute(select(CookieCategory.id).where(CookieCategory.slug == "analytics"))
        ).scalar_one()
        db.add_all(
            [
                Translation(site_id=site.id, locale="en-GB", strings={"title": "Cookies"}),
                Translation(site_id=site.id, locale="de", strings={"title": "Kekse"}),
                Cookie(
                    site_id=site.id,
                    name="_ga",
                    domain=".mig.test",
                    category_id=analytics,
                    review_status="approved",
                ),
                Cookie(site_id=site.id, name="x", domain=".mig.test", review_status="rejected"),
                CookieAllowListEntry(
                    site_id=site.id, category_id=analytics, name_pattern="_ga", domain_pattern="*"
                ),
            ]
        )
        await db.flush()
        config_id = (
            await db.execute(select(SiteConfig.id).where(SiteConfig.site_id == site.id))
        ).scalar_one()

        await _backfill(db)

        revision = await _live(db, site)
        expected = await build_site_snapshot(db, site.id)
        assert revision.number == 1
        assert revision.note == "Initial revision"
        assert revision.requires_reconsent is False
        assert revision.published_by is None
        assert revision.consent_version == config_id
        assert revision.snapshot == expected.snapshot
        assert revision.site_layer == expected.site_layer
        assert revision.sources == expected.sources
        assert revision.content_hash == expected.content_hash
        assert (await get_draft_status(db, site.id)).has_unpublished_changes is False

    async def test_site_without_parents(self, session):
        db = session
        org = Organisation(name="Bare Org", slug=f"bare-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        site = await _site(db, org)

        await _backfill(db)

        revision = await _live(db, site)
        assert revision.content_hash == (await build_site_snapshot(db, site.id)).content_hash

    async def test_which_sites_get_v1(self, session):
        db = session
        org = Organisation(name="Mixed Org", slug=f"mixed-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        inactive = await _site(db, org, is_active=False)
        deleted = await _site(db, org, deleted_at=datetime.now(UTC))
        no_config = await _site(db, org, config=False)

        await _backfill(db)

        assert await _live(db, inactive) is not None
        assert await _live(db, deleted) is None
        assert await _live(db, no_config) is None

    async def test_leaves_published_sites_alone(self, session):
        db = session
        org = Organisation(name="Again Org", slug=f"again-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        site = await _site(db, org)
        await _backfill(db)
        first = await _live(db, site)

        await _backfill(db)

        count = (
            await db.execute(
                select(SiteConfigRevision.id).where(SiteConfigRevision.site_id == site.id)
            )
        ).all()
        assert len(count) == 1
        assert (await _live(db, site)).id == first.id
