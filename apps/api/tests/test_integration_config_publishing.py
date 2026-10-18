"""Integration tests for the draft, publish and live revision lifecycle."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.org_config import OrgConfig
from src.models.site_config_revision import SiteConfigRevision
from src.services.config_publishing import (
    DraftOutOfDateError,
    NothingToPublishError,
    get_draft_status,
    get_live_revision,
    publish_draft,
)
from src.services.config_snapshot import SiteNotFoundError
from tests.conftest import create_test_site, requires_db


async def _draft(client, headers, site_id) -> dict:
    resp = await client.get(f"/api/v1/config/sites/{site_id}/draft", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _publish(client, headers, site_id, content_hash, note=None):
    return await client.post(
        f"/api/v1/config/sites/{site_id}/publish",
        headers=headers,
        json={"expected_content_hash": content_hash, "note": note},
    )


async def _publish_draft(client, headers, site_id, note=None) -> dict:
    draft = await _draft(client, headers, site_id)
    resp = await _publish(client, headers, site_id, draft["content_hash"], note)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _banner(client, site_id):
    return await client.get(f"/api/v1/config/sites/{site_id}/geo-resolved")


async def _edit(client, headers, site_id, **fields):
    resp = await client.patch(f"/api/v1/sites/{site_id}/config", headers=headers, json=fields)
    assert resp.status_code == 200, resp.text


@requires_db
class TestNotYetPublished:
    async def test_banner_gets_no_config(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        assert (await _banner(db_client, site_id)).status_code == 404

    async def test_draft_reports_unpublished_changes(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["live_revision"] is None
        assert draft["has_unpublished_changes"] is True
        assert len(draft["content_hash"]) == 64


@requires_db
class TestPublishLifecycle:
    async def test_edits_only_reach_the_banner_once_published(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id, note="Launch")
        assert first["number"] == 1
        assert first["note"] == "Launch"

        before = (await _banner(db_client, site_id)).json()
        await _edit(db_client, auth_headers, site_id, privacy_policy_url="https://x.test/new")

        assert (await _banner(db_client, site_id)).json() == before
        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["has_unpublished_changes"] is True
        assert draft["live_revision"]["id"] == first["id"]

        second = await _publish_draft(db_client, auth_headers, site_id)
        after = (await _banner(db_client, site_id)).json()

        assert second["number"] == 2
        assert after["privacy_policy_url"] == "https://x.test/new"
        # An ordinary publish keeps the consent version, so returning
        # visitors aren't asked again.
        assert after["id"] == before["id"]
        assert (await _draft(db_client, auth_headers, site_id))["has_unpublished_changes"] is False

    async def test_out_of_date_draft_is_refused(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        reviewed = await _draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/terms")
        reviewed_hash = (await _draft(db_client, auth_headers, site_id))["content_hash"]

        # Someone else saves after the publisher reviewed the draft.
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/other")
        resp = await _publish(db_client, auth_headers, site_id, reviewed_hash)

        assert resp.status_code == 409
        assert "changed since you reviewed it" in resp.json()["detail"]
        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["live_revision"]["id"] == reviewed["live_revision"]["id"]

    async def test_nothing_to_publish(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        draft = await _draft(db_client, auth_headers, site_id)
        resp = await _publish(db_client, auth_headers, site_id, draft["content_hash"])
        assert resp.status_code == 409
        assert resp.json()["detail"] == "There are no unpublished changes"

    async def test_parent_change_shows_as_unpublished(
        self, db_client, auth_headers, _test_engine, test_org
    ):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)

        async with AsyncSession(_test_engine) as session:
            org_config = (
                await session.execute(
                    select(OrgConfig).where(OrgConfig.organisation_id == test_org.id)
                )
            ).scalar_one_or_none()
            if org_config is None:
                session.add(OrgConfig(organisation_id=test_org.id, terms_url="https://org/t"))
            else:
                org_config.terms_url = f"https://org/{uuid.uuid4().hex}"
            await session.commit()

        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["has_unpublished_changes"] is True
        assert [s["kind"] for s in draft["changed_sources"]] == ["organisation_config"]

    async def test_publisher_is_recorded(self, db_client, auth_headers, test_user, _test_engine):
        site_id = await create_test_site(db_client, auth_headers)
        published = await _publish_draft(db_client, auth_headers, site_id)
        assert published["published_by"] == str(test_user.id)
        async with AsyncSession(_test_engine) as session:
            revision = await session.get(SiteConfigRevision, uuid.UUID(published["id"]))
        assert revision.snapshot["config"]["privacy_policy_url"] is None


@requires_db
class TestOrgScoping:
    async def test_other_org_cannot_see_or_publish(
        self, db_client, auth_headers, other_org_headers
    ):
        site_id = await create_test_site(db_client, auth_headers)
        draft = await _draft(db_client, auth_headers, site_id)

        resp = await db_client.get(
            f"/api/v1/config/sites/{site_id}/draft", headers=other_org_headers
        )
        assert resp.status_code == 404
        resp = await _publish(db_client, other_org_headers, site_id, draft["content_hash"])
        assert resp.status_code == 404


@requires_db
class TestPublishService:
    async def test_missing_site(self, _test_engine, _setup_db):
        async with AsyncSession(_test_engine) as session:
            with pytest.raises(SiteNotFoundError):
                await publish_draft(
                    session, uuid.uuid4(), expected_content_hash="0" * 64, published_by=None
                )

    async def test_unpublished_then_published(self, db_client, auth_headers, _test_engine):
        site_id = uuid.UUID(await create_test_site(db_client, auth_headers))
        async with AsyncSession(_test_engine) as session:
            status = await get_draft_status(session, site_id)
            assert status.live_revision is None

            with pytest.raises(DraftOutOfDateError):
                await publish_draft(
                    session, site_id, expected_content_hash="0" * 64, published_by=None
                )

            revision = await publish_draft(
                session, site_id, expected_content_hash=status.content_hash, published_by=None
            )
            assert (await get_live_revision(session, site_id)).id == revision.id

            with pytest.raises(NothingToPublishError):
                await publish_draft(
                    session, site_id, expected_content_hash=status.content_hash, published_by=None
                )
