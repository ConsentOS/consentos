"""Integration tests for revision snapshots and the revisions table."""

import uuid

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.extensions.registry import get_registry
from src.models.cookie import Cookie, CookieAllowListEntry, CookieCategory
from src.models.org_config import OrgConfig
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.models.site_config_revision import SiteConfigRevision
from src.models.site_group import SiteGroup
from src.models.site_group_config import SiteGroupConfig
from src.models.translation import Translation
from src.models.user import User
from src.services.config_publishing import publish_draft
from src.services.config_snapshot import (
    SiteNotFoundError,
    build_site_snapshot,
    changed_sources,
)
from tests.conftest import requires_db


async def _make_org(session: AsyncSession):
    from src.models.organisation import Organisation

    org = Organisation(name="Snapshot Org", slug=f"snap-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    return org


# Server defaults give a new site_configs row explicit values for these,
# which would hide the parent layers under test. The ORM leaves ``None``
# out of the INSERT, so they are cleared with an UPDATE instead.
_INHERIT = {"blocking_mode": None, "consent_expiry_days": None}


async def _make_site(session: AsyncSession, org_id, *, group_id=None, **config) -> Site:
    site = Site(
        organisation_id=org_id,
        domain=f"snap-{uuid.uuid4().hex[:8]}.com",
        display_name="Snapshot site",
        site_group_id=group_id,
    )
    session.add(site)
    await session.flush()
    session.add(SiteConfig(site_id=site.id, **config))
    await session.flush()
    await session.execute(
        update(SiteConfig)
        .where(SiteConfig.site_id == site.id)
        .values(**{key: value for key, value in _INHERIT.items() if key not in config})
    )
    return site


async def _category_id(session: AsyncSession, slug: str):
    return (
        await session.execute(select(CookieCategory.id).where(CookieCategory.slug == slug))
    ).scalar_one()


@requires_db
class TestBuildSiteSnapshot:
    async def test_bakes_in_every_layer(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            org = await _make_org(session)
            session.add(OrgConfig(organisation_id=org.id, consent_expiry_days=200))
            group = SiteGroup(organisation_id=org.id, name="Group")
            session.add(group)
            await session.flush()
            session.add(
                SiteGroupConfig(
                    site_group_id=group.id,
                    consent_sharing_enabled=True,
                    regional_modes={"US-CA": "opt_out"},
                )
            )
            site = await _make_site(
                session, org.id, group_id=group.id, privacy_policy_url="https://x.test/p"
            )
            session.add(Translation(site_id=site.id, locale="en-GB", strings={"title": "Hi"}))
            session.add(Translation(site_id=site.id, locale="fr", strings={"title": "Salut"}))
            await session.flush()

            built = await build_site_snapshot(session, site.id)

        config = built.snapshot["config"]
        assert config["consent_expiry_days"] == 200
        assert config["privacy_policy_url"] == "https://x.test/p"
        assert config["regional_modes"] == {"US-CA": "opt_out"}
        assert config["consent_group_id"] == str(group.id)
        assert "id" not in config
        assert "scan_max_pages" not in config
        assert built.snapshot["translations"] == {
            "en-gb": {"title": "Hi"},
            "fr": {"title": "Salut"},
        }
        assert [s["kind"] for s in built.sources] == ["organisation_config", "site_group_config"]
        assert built.site_layer["site_config"]["privacy_policy_url"] == "https://x.test/p"
        assert built.site_layer["site_config"]["blocking_mode"] is None

    async def test_hash_is_stable(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            org = await _make_org(session)
            site = await _make_site(session, org.id)
            first = await build_site_snapshot(session, site.id)
            second = await build_site_snapshot(session, site.id)
        assert first.content_hash == second.content_hash

    async def test_parent_change_changes_hash_and_sources(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            org = await _make_org(session)
            org_config = OrgConfig(organisation_id=org.id, consent_expiry_days=100)
            session.add(org_config)
            site = await _make_site(session, org.id)
            before = await build_site_snapshot(session, site.id)

            org_config.consent_expiry_days = 90
            await session.flush()
            after = await build_site_snapshot(session, site.id)

        assert before.content_hash != after.content_hash
        assert [s["kind"] for s in changed_sources(before.sources, after.sources)] == [
            "organisation_config"
        ]

    async def test_scan_settings_do_not_change_hash(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            org = await _make_org(session)
            site = await _make_site(session, org.id)
            before = await build_site_snapshot(session, site.id)
            await session.execute(
                update(SiteConfig)
                .where(SiteConfig.site_id == site.id)
                .values(scan_schedule_cron="0 3 * * *", scan_max_pages=5)
            )
            after = await build_site_snapshot(session, site.id)
        assert before.content_hash == after.content_hash

    async def test_cookies(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            org = await _make_org(session)
            site = await _make_site(session, org.id)
            analytics = await _category_id(session, "analytics")
            kept = Cookie(
                site_id=site.id,
                name="_ga",
                domain=".snap.test",
                category_id=analytics,
                review_status="approved",
            )
            session.add(kept)
            session.add(
                Cookie(site_id=site.id, name="bad", domain=".snap.test", review_status="rejected")
            )
            session.add(
                CookieAllowListEntry(
                    site_id=site.id,
                    category_id=analytics,
                    name_pattern="_ga",
                    domain_pattern="*",
                )
            )
            await session.flush()
            before = await build_site_snapshot(session, site.id)

            # A rescan only touches last_seen_at, which visitors never see.
            kept.last_seen_at = "2026-10-18T00:00:00Z"
            await session.flush()
            after = await build_site_snapshot(session, site.id)

        assert [c["name"] for c in before.snapshot["cookies"]] == ["_ga"]
        assert before.snapshot["cookies"][0]["category"] == "analytics"
        assert before.snapshot["cookie_count"] == 1
        assert len(before.site_layer["cookies"]) == 2
        assert before.site_layer["allow_list"][0]["name_pattern"] == "_ga"
        assert before.content_hash == after.content_hash

    async def test_records_extension_output(self, _test_engine, _setup_db):
        async def enrich(site_id, db, config):
            config["widget"] = {"site": str(site_id)}

        registry = get_registry()
        registry.config_enrichers.append(enrich)
        try:
            async with AsyncSession(_test_engine, expire_on_commit=False) as session:
                org = await _make_org(session)
                site = await _make_site(session, org.id)
                built = await build_site_snapshot(session, site.id)
        finally:
            registry.config_enrichers.remove(enrich)

        assert built.snapshot["extensions"] == {"widget": {"site": str(site.id)}}
        assert "widget" not in built.snapshot["config"]

    async def test_missing_site(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            with pytest.raises(SiteNotFoundError):
                await build_site_snapshot(session, uuid.uuid4())


@requires_db
class TestRevisionImmutability:
    async def _revision(self, session: AsyncSession, published_by=None) -> SiteConfigRevision:
        org = await _make_org(session)
        site = await _make_site(session, org.id)
        built = await build_site_snapshot(session, site.id)
        revision = SiteConfigRevision(
            site_id=site.id,
            number=1,
            consent_version=uuid.uuid4(),
            snapshot=built.snapshot,
            site_layer=built.site_layer,
            sources=built.sources,
            content_hash=built.content_hash,
            published_by=published_by,
        )
        session.add(revision)
        await session.flush()
        return revision

    async def test_content_cannot_be_changed(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            revision = await self._revision(session)
            with pytest.raises(DBAPIError, match="cannot be changed"):
                await session.execute(
                    update(SiteConfigRevision)
                    .where(SiteConfigRevision.id == revision.id)
                    .values(note="edited")
                )

    async def test_deleting_the_publisher_keeps_the_revision(
        self, _test_engine, _setup_db, test_org
    ):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            user = User(
                email=f"pub-{uuid.uuid4().hex[:8]}@test.com",
                password_hash="x",
                full_name="Publisher",
                role="admin",
                organisation_id=test_org.id,
            )
            session.add(user)
            await session.flush()
            revision = await self._revision(session, published_by=user.id)
            await session.delete(user)
            await session.flush()
            await session.refresh(revision)
        assert revision.published_by is None

    async def test_numbers_are_unique_per_site(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            revision = await self._revision(session)
            session.add(
                SiteConfigRevision(
                    site_id=revision.site_id,
                    number=1,
                    consent_version=uuid.uuid4(),
                    snapshot={},
                    site_layer={},
                    sources=[],
                    content_hash="0" * 64,
                )
            )
            with pytest.raises(DBAPIError):
                await session.flush()


@requires_db
class TestGeoResolvedFixes:
    async def test_serves_consent_group_and_group_regional_modes(
        self, db_client, _test_engine, _setup_db
    ):
        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            org = await _make_org(session)
            group = SiteGroup(organisation_id=org.id, name="Shared")
            session.add(group)
            await session.flush()
            session.add(
                SiteGroupConfig(
                    site_group_id=group.id,
                    consent_sharing_enabled=True,
                    regional_modes={"DEFAULT": "opt_out"},
                )
            )
            site = await _make_site(session, org.id, group_id=group.id)
            built = await build_site_snapshot(session, site.id)
            await publish_draft(
                session, site.id, expected_content_hash=built.content_hash, published_by=None
            )
            await session.commit()

        resp = await db_client.get(
            f"/api/v1/config/sites/{site.id}/geo-resolved",
            headers={"CF-IPCountry": "GB"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["consent_group_id"] == str(group.id)
        assert body["blocking_mode"] == "opt_out"
