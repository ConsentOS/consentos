"""Integration tests for the draft, publish and live revision lifecycle."""

import uuid
from unittest.mock import patch

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


async def _publish(client, headers, site_id, content_hash, note=None, ask_again=False):
    return await client.post(
        f"/api/v1/config/sites/{site_id}/publish",
        headers=headers,
        json={
            "expected_content_hash": content_hash,
            "note": note,
            "ask_visitors_again": ask_again,
        },
    )


async def _publish_draft(client, headers, site_id, note=None, ask_again=False) -> dict:
    draft = await _draft(client, headers, site_id)
    resp = await _publish(client, headers, site_id, draft["content_hash"], note, ask_again)
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

    async def test_site_shows_whether_it_is_published(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        site = (await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)).json()
        assert site["live_revision_id"] is None

        published = await _publish_draft(db_client, auth_headers, site_id)

        site = (await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)).json()
        assert site["live_revision_id"] == published["id"]

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
class TestReconsent:
    async def test_asking_again_changes_the_consent_version(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        before = (await _banner(db_client, site_id)).json()["id"]

        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")
        published = await _publish_draft(db_client, auth_headers, site_id, ask_again=True)

        after = (await _banner(db_client, site_id)).json()["id"]
        assert after != before
        assert after == published["consent_version"]
        assert published["requires_reconsent"] is True

    async def test_category_change_is_flagged(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        assert (await _draft(db_client, auth_headers, site_id))["reconsent_reasons"] == []

        await _edit(db_client, auth_headers, site_id, enabled_categories=["necessary"])

        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["reconsent_reasons"] == ["categories"]

    async def test_first_publish_suggests_nothing(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        assert (await _draft(db_client, auth_headers, site_id))["reconsent_reasons"] == []


@requires_db
class TestHistory:
    async def test_lists_revisions_newest_first(self, db_client, auth_headers, test_user):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id, note="Launch")
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")
        second = await _publish_draft(db_client, auth_headers, site_id, ask_again=True)

        resp = await db_client.get(
            f"/api/v1/config/sites/{site_id}/revisions", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        newest, oldest = body["items"]
        assert (newest["id"], newest["number"], newest["is_live"]) == (second["id"], 2, True)
        assert newest["requires_reconsent"] is True
        assert (oldest["id"], oldest["is_live"], oldest["note"]) == (first["id"], False, "Launch")
        assert oldest["published_by_name"] == test_user.full_name
        assert oldest["rolled_back_from_id"] is None

    async def test_pages(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")
        await _publish_draft(db_client, auth_headers, site_id)

        resp = await db_client.get(
            f"/api/v1/config/sites/{site_id}/revisions",
            params={"limit": 1, "offset": 1},
            headers=auth_headers,
        )
        body = resp.json()
        assert body["total"] == 2
        assert [item["number"] for item in body["items"]] == [1]

    async def test_revision_detail(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        published = await _publish_draft(db_client, auth_headers, site_id)

        resp = await db_client.get(
            f"/api/v1/config/sites/{site_id}/revisions/{published['id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_live"] is True
        assert body["snapshot"]["config"]["blocking_mode"] == "opt_in"
        assert body["sources"][0]["kind"] == "organisation_config"

    async def test_revision_of_another_site_is_not_found(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        other_site = await create_test_site(db_client, auth_headers)
        published = await _publish_draft(db_client, auth_headers, other_site)

        resp = await db_client.get(
            f"/api/v1/config/sites/{site_id}/revisions/{published['id']}", headers=auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    async def test_revisions_cannot_be_changed(self, db_client, auth_headers, method):
        site_id = await create_test_site(db_client, auth_headers)
        published = await _publish_draft(db_client, auth_headers, site_id)

        resp = await db_client.request(
            method,
            f"/api/v1/config/sites/{site_id}/revisions/{published['id']}",
            headers=auth_headers,
            json={"note": "edited"},
        )
        assert resp.status_code == 405


async def _rollback(client, headers, site_id, revision_id, ask_again=False):
    return await client.post(
        f"/api/v1/config/sites/{site_id}/revisions/{revision_id}/rollback",
        headers=headers,
        json={"ask_visitors_again": ask_again},
    )


async def _translate(client, headers, site_id, locale, strings):
    base = f"/api/v1/sites/{site_id}/translations"
    resp = await client.put(f"{base}/{locale}", headers=headers, json={"strings": strings})
    if resp.status_code == 404:
        resp = await client.post(
            f"{base}/", headers=headers, json={"locale": locale, "strings": strings}
        )
    assert resp.status_code in (200, 201), resp.text


@requires_db
class TestRollback:
    async def test_restores_what_the_revision_served(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _translate(db_client, auth_headers, site_id, "fr", {"title": "Avant"})
        first = await _publish_draft(db_client, auth_headers, site_id)
        served_first = (
            await db_client.get(f"/api/v1/config/sites/{site_id}/geo-resolved?locale=fr")
        ).json()

        await _edit(db_client, auth_headers, site_id, privacy_policy_url="https://x.test/v2")
        await _translate(db_client, auth_headers, site_id, "fr", {"title": "Après"})
        await _publish_draft(db_client, auth_headers, site_id)

        resp = await _rollback(db_client, auth_headers, site_id, first["id"])

        assert resp.status_code == 200, resp.text
        restored = resp.json()
        assert restored["number"] == 3
        assert restored["note"] == "Rollback to v1"
        served_now = (
            await db_client.get(f"/api/v1/config/sites/{site_id}/geo-resolved?locale=fr")
        ).json()
        assert served_now == served_first

        history = (
            await db_client.get(f"/api/v1/config/sites/{site_id}/revisions", headers=auth_headers)
        ).json()["items"]
        assert history[0]["is_live"] is True
        assert history[0]["rolled_back_from_id"] == first["id"]
        assert history[0]["rolled_back_from_number"] == 1

    async def test_leaves_the_draft_alone(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/v2")
        await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/unpublished")

        await _rollback(db_client, auth_headers, site_id, first["id"])

        config = (
            await db_client.get(f"/api/v1/sites/{site_id}/config", headers=auth_headers)
        ).json()
        assert config["terms_url"] == "https://x.test/unpublished"
        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["has_unpublished_changes"] is True
        assert draft["live_revision"]["number"] == 3

    async def test_keeps_or_changes_the_consent_version(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/v2")
        second = await _publish_draft(db_client, auth_headers, site_id)

        kept = (await _rollback(db_client, auth_headers, site_id, first["id"])).json()
        asked = (
            await _rollback(db_client, auth_headers, site_id, second["id"], ask_again=True)
        ).json()

        assert kept["consent_version"] == first["consent_version"]
        assert asked["consent_version"] != first["consent_version"]
        assert asked["requires_reconsent"] is True

    async def test_suggests_asking_again_when_categories_differ(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, enabled_categories=["necessary"])
        second = await _publish_draft(db_client, auth_headers, site_id)

        detail = (
            await db_client.get(
                f"/api/v1/config/sites/{site_id}/revisions/{first['id']}", headers=auth_headers
            )
        ).json()
        live_detail = (
            await db_client.get(
                f"/api/v1/config/sites/{site_id}/revisions/{second['id']}", headers=auth_headers
            )
        ).json()
        assert detail["rollback_reconsent_reasons"] == ["categories"]
        assert live_detail["rollback_reconsent_reasons"] == []

    async def test_live_revision_is_refused(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        resp = await _rollback(db_client, auth_headers, site_id, first["id"])
        assert resp.status_code == 409
        assert resp.json()["detail"] == "That revision is already live"

    async def test_another_sites_revision_is_not_found(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        other_site = await create_test_site(db_client, auth_headers)
        other = await _publish_draft(db_client, auth_headers, other_site)
        resp = await _rollback(db_client, auth_headers, site_id, other["id"])
        assert resp.status_code == 404

    async def test_other_org_cannot_roll_back(self, db_client, auth_headers, other_org_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        resp = await _rollback(db_client, other_org_headers, site_id, first["id"])
        assert resp.status_code == 404


@requires_db
class TestPublishAttempts:
    async def test_success_is_recorded(self, db_client, auth_headers, test_user):
        site_id = await create_test_site(db_client, auth_headers)
        assert (await _draft(db_client, auth_headers, site_id))["last_attempt"] is None

        await _publish_draft(db_client, auth_headers, site_id)

        attempt = (await _draft(db_client, auth_headers, site_id))["last_attempt"]
        assert attempt["action"] == "publish"
        assert attempt["status"] == "succeeded"
        assert attempt["revision_number"] == 1
        assert attempt["attempted_by_name"] == test_user.full_name
        assert attempt["error_message"] is None

    async def test_refusal_is_recorded_and_changes_nothing(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")

        resp = await _publish(db_client, auth_headers, site_id, "0" * 64)

        assert resp.status_code == 409
        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["live_revision"]["id"] == first["id"]
        assert draft["has_unpublished_changes"] is True
        attempt = draft["last_attempt"]
        assert (attempt["status"], attempt["error_code"]) == ("failed", "stale_draft")
        assert attempt["error_message"] == resp.json()["detail"]
        assert attempt["revision_number"] is None

    async def test_rollback_refusal_is_recorded(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)

        await _rollback(db_client, auth_headers, site_id, first["id"])

        attempt = (await _draft(db_client, auth_headers, site_id))["last_attempt"]
        assert (attempt["action"], attempt["error_code"]) == ("rollback", "already_live")

    async def test_unexpected_error_is_recorded(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")
        draft = await _draft(db_client, auth_headers, site_id)

        with (
            patch(
                "src.services.config_publishing._next_revision_number",
                side_effect=RuntimeError("database went away"),
            ),
            pytest.raises(RuntimeError),
        ):
            await _publish(db_client, auth_headers, site_id, draft["content_hash"])

        after = await _draft(db_client, auth_headers, site_id)
        assert after["live_revision"]["id"] == first["id"]
        attempt = after["last_attempt"]
        assert (attempt["status"], attempt["error_code"]) == ("failed", "publish_failed")
        assert attempt["error_message"] == "The publish failed. Nothing was changed."


async def _widget(client, site_id) -> dict:
    resp = await client.get(f"/api/v1/config/sites/{site_id}/cookies")
    assert resp.status_code == 200, resp.text
    return {cat["slug"]: [c["name"] for c in cat["cookies"]] for cat in resp.json()["categories"]}


async def _category_id(client, headers, slug) -> str:
    resp = await client.get("/api/v1/cookies/categories", headers=headers)
    return next(cat["id"] for cat in resp.json() if cat["slug"] == slug)


@requires_db
class TestVersionedCookieRules:
    async def test_classification_reaches_visitors_only_on_publish(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        analytics = await _category_id(db_client, auth_headers, "analytics")
        cookies = {}
        for name in ("_ga", "_rejected", "_pending"):
            resp = await db_client.post(
                f"/api/v1/cookies/sites/{site_id}",
                headers=auth_headers,
                json={"name": name, "domain": ".x.test"},
            )
            cookies[name] = resp.json()["id"]

        async def review(name, **body):
            resp = await db_client.patch(
                f"/api/v1/cookies/sites/{site_id}/{cookies[name]}", headers=auth_headers, json=body
            )
            assert resp.status_code == 200, resp.text

        await review("_rejected", review_status="rejected")
        first = await _publish_draft(db_client, auth_headers, site_id)
        assert (await _widget(db_client, site_id))["uncategorised"] == ["_ga", "_pending"]

        await review("_ga", category_id=analytics, review_status="approved")
        assert (await _widget(db_client, site_id))["uncategorised"] == ["_ga", "_pending"]
        assert (await _draft(db_client, auth_headers, site_id))["has_unpublished_changes"] is True

        await _publish_draft(db_client, auth_headers, site_id)
        published = await _widget(db_client, site_id)
        assert published["analytics"] == ["_ga"]
        assert published["uncategorised"] == ["_pending"]

        await _rollback(db_client, auth_headers, site_id, first["id"])
        assert (await _widget(db_client, site_id))["uncategorised"] == ["_ga", "_pending"]

    async def test_new_discoveries_show_in_review_straight_away(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        await db_client.post(
            f"/api/v1/cookies/sites/{site_id}",
            headers=auth_headers,
            json={"name": "_new", "domain": ".x.test"},
        )

        listed = await db_client.get(f"/api/v1/cookies/sites/{site_id}", headers=auth_headers)
        assert [c["name"] for c in listed.json()] == ["_new"]
        assert "uncategorised" not in await _widget(db_client, site_id)

    async def test_unpublished_site_has_no_widget(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        resp = await db_client.get(f"/api/v1/config/sites/{site_id}/cookies")
        assert resp.status_code == 404


async def _diff(client, headers, site_id, **params) -> dict:
    resp = await client.get(f"/api/v1/config/sites/{site_id}/diff", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


@requires_db
class TestDiff:
    async def test_draft_against_live(self, db_client, auth_headers, _test_engine, test_org):
        site_id = await create_test_site(db_client, auth_headers)
        live = await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")
        async with AsyncSession(_test_engine) as session:
            org_config = (
                await session.execute(
                    select(OrgConfig).where(OrgConfig.organisation_id == test_org.id)
                )
            ).scalar_one_or_none()
            if org_config is None:
                org_config = OrgConfig(organisation_id=test_org.id)
                session.add(org_config)
            org_config.privacy_policy_url = f"https://org/{uuid.uuid4().hex}"
            await session.commit()

        diff = await _diff(db_client, auth_headers, site_id)

        assert diff["from"]["revision_id"] == live["id"]
        assert diff["to"]["revision_id"] is None
        assert (
            diff["to"]["content_hash"]
            == (await _draft(db_client, auth_headers, site_id))["content_hash"]
        )
        changes = {c["key"]: c for c in diff["changes"]}
        assert changes["terms_url"]["source"] == "site"
        assert changes["terms_url"]["after"] == "https://x.test/t"
        assert changes["privacy_policy_url"]["source"] == "organisation"
        assert changes["privacy_policy_url"]["area"] == "settings"

    async def test_nothing_published_yet(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        diff = await _diff(db_client, auth_headers, site_id)
        assert diff["from"] is None
        assert diff["changes"]
        assert diff["reconsent_reasons"] == []

    async def test_two_revisions(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        first = await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, enabled_categories=["necessary"])
        second = await _publish_draft(db_client, auth_headers, site_id)

        diff = await _diff(
            db_client,
            auth_headers,
            site_id,
            from_revision=first["id"],
            to_revision=second["id"],
        )

        assert (diff["from"]["number"], diff["to"]["number"]) == (1, 2)
        assert [c["key"] for c in diff["changes"]] == ["enabled_categories"]
        assert diff["changes"][0]["area"] == "categories"
        assert diff["reconsent_reasons"] == ["categories"]

    async def test_another_sites_revision_is_not_found(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        other_site = await create_test_site(db_client, auth_headers)
        other = await _publish_draft(db_client, auth_headers, other_site)
        resp = await db_client.get(
            f"/api/v1/config/sites/{site_id}/diff",
            headers=auth_headers,
            params={"from_revision": other["id"]},
        )
        assert resp.status_code == 404


async def _discard(client, headers, site_id):
    return await client.post(f"/api/v1/config/sites/{site_id}/discard", headers=headers)


@requires_db
class TestDiscard:
    async def test_restores_the_sites_own_values(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        analytics = await _category_id(db_client, auth_headers, "analytics")
        marketing = await _category_id(db_client, auth_headers, "marketing")
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/published")
        await _translate(db_client, auth_headers, site_id, "fr", {"title": "Publié"})
        cookie = (
            await db_client.post(
                f"/api/v1/cookies/sites/{site_id}",
                headers=auth_headers,
                json={"name": "_ga", "domain": ".x.test", "category_id": analytics},
            )
        ).json()
        await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/allow-list",
            headers=auth_headers,
            json={"name_pattern": "_ga", "domain_pattern": "*", "category_id": analytics},
        )
        await _publish_draft(db_client, auth_headers, site_id)

        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/draft")
        await _translate(db_client, auth_headers, site_id, "fr", {"title": "Brouillon"})
        await _translate(db_client, auth_headers, site_id, "de", {"title": "Entwurf"})
        await db_client.patch(
            f"/api/v1/cookies/sites/{site_id}/{cookie['id']}",
            headers=auth_headers,
            json={"category_id": marketing, "review_status": "rejected"},
        )
        await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/allow-list",
            headers=auth_headers,
            json={"name_pattern": "_fbp", "domain_pattern": "*", "category_id": marketing},
        )
        assert (await _draft(db_client, auth_headers, site_id))["has_unpublished_changes"]

        resp = await _discard(db_client, auth_headers, site_id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["has_unpublished_changes"] is False
        assert (await _diff(db_client, auth_headers, site_id))["changes"] == []
        config = (
            await db_client.get(f"/api/v1/sites/{site_id}/config", headers=auth_headers)
        ).json()
        assert config["terms_url"] == "https://x.test/published"
        translations = (
            await db_client.get(f"/api/v1/sites/{site_id}/translations/", headers=auth_headers)
        ).json()
        assert {t["locale"]: t["strings"] for t in translations} == {"fr": {"title": "Publié"}}
        restored = (
            await db_client.get(f"/api/v1/cookies/sites/{site_id}", headers=auth_headers)
        ).json()[0]
        assert (restored["category_id"], restored["review_status"]) == (analytics, "pending")
        allow_list = (
            await db_client.get(f"/api/v1/cookies/sites/{site_id}/allow-list", headers=auth_headers)
        ).json()
        assert [e["name_pattern"] for e in allow_list] == ["_ga"]

    async def test_inherited_changes_remain(self, db_client, auth_headers, _test_engine, test_org):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/draft")
        async with AsyncSession(_test_engine) as session:
            org_config = (
                await session.execute(
                    select(OrgConfig).where(OrgConfig.organisation_id == test_org.id)
                )
            ).scalar_one_or_none()
            if org_config is None:
                org_config = OrgConfig(organisation_id=test_org.id)
                session.add(org_config)
            org_config.privacy_policy_url = f"https://org/{uuid.uuid4().hex}"
            await session.commit()

        status = (await _discard(db_client, auth_headers, site_id)).json()

        assert status["has_unpublished_changes"] is True
        changes = (await _diff(db_client, auth_headers, site_id))["changes"]
        assert [(c["key"], c["source"]) for c in changes] == [
            ("privacy_policy_url", "organisation")
        ]

    async def test_needs_a_live_revision(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        resp = await _discard(db_client, auth_headers, site_id)
        assert resp.status_code == 409
        assert resp.json()["detail"].startswith("Nothing has been published yet")

    async def test_other_org_cannot_discard(self, db_client, auth_headers, other_org_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await _publish_draft(db_client, auth_headers, site_id)
        assert (await _discard(db_client, other_org_headers, site_id)).status_code == 404


async def _group_with_sites(client, headers, count) -> tuple[str, list[str]]:
    group = (
        await client.post(
            "/api/v1/site-groups/", headers=headers, json={"name": f"G {uuid.uuid4().hex[:6]}"}
        )
    ).json()
    site_ids = []
    for _ in range(count):
        site_id = await create_test_site(client, headers)
        resp = await client.patch(
            f"/api/v1/sites/{site_id}", headers=headers, json={"site_group_id": group["id"]}
        )
        assert resp.status_code == 200, resp.text
        site_ids.append(site_id)
    return group["id"], site_ids


async def _set_group_config(client, headers, group_id, **fields):
    resp = await client.put(f"/api/v1/site-groups/{group_id}/config", headers=headers, json=fields)
    assert resp.status_code == 200, resp.text


async def _affected(client, headers, group_id) -> list[dict]:
    resp = await client.get(
        "/api/v1/config/affected-sites", headers=headers, params={"site_group_id": group_id}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@requires_db
class TestBulkPublish:
    async def test_lists_published_sites_with_changes(self, db_client, auth_headers):
        group_id, (changed, unpublished) = await _group_with_sites(db_client, auth_headers, 2)
        await _publish_draft(db_client, auth_headers, changed)
        assert await _affected(db_client, auth_headers, group_id) == []

        await _set_group_config(db_client, auth_headers, group_id, terms_url="https://g/t")

        [site] = await _affected(db_client, auth_headers, group_id)
        assert site["site_id"] == changed
        assert site["live_number"] == 1
        assert [s["kind"] for s in site["changed_sources"]] == ["site_group_config"]
        assert (
            site["content_hash"] == (await _draft(db_client, auth_headers, changed))["content_hash"]
        )
        assert unpublished not in [
            s["site_id"] for s in await _affected(db_client, auth_headers, group_id)
        ]

    async def test_publishes_each_site_and_carries_on_past_failures(
        self, db_client, auth_headers, other_org_headers
    ):
        group_id, site_ids = await _group_with_sites(db_client, auth_headers, 3)
        for site_id in site_ids:
            await _publish_draft(db_client, auth_headers, site_id)
        await _set_group_config(db_client, auth_headers, group_id, terms_url="https://g/t")
        affected = await _affected(db_client, auth_headers, group_id)
        # One site changes again after the list was reviewed.
        await _edit(db_client, auth_headers, site_ids[1], privacy_policy_url="https://late")
        foreign = await create_test_site(db_client, other_org_headers)

        resp = await db_client.post(
            "/api/v1/config/bulk-publish",
            headers=auth_headers,
            json={
                "sites": [
                    {"site_id": s["site_id"], "expected_content_hash": s["content_hash"]}
                    for s in affected
                ]
                + [{"site_id": foreign, "expected_content_hash": "0" * 64}],
                "note": "New group terms",
            },
        )

        assert resp.status_code == 200, resp.text
        results = {r["site_id"]: r for r in resp.json()["results"]}
        assert results[site_ids[0]]["status"] == "succeeded"
        assert results[site_ids[0]]["revision_number"] == 2
        assert results[site_ids[2]]["status"] == "succeeded"
        assert results[site_ids[1]]["status"] == "failed"
        assert "changed since you reviewed it" in results[site_ids[1]]["error_message"]
        assert results[foreign] == {
            "site_id": foreign,
            "status": "failed",
            "revision_number": None,
            "error_message": "Site not found",
        }

        published = (await _banner(db_client, site_ids[0])).json()
        assert published["terms_url"] == "https://g/t"
        assert (await _banner(db_client, site_ids[1])).json()["terms_url"] is None
        history = (
            await db_client.get(
                f"/api/v1/config/sites/{site_ids[0]}/revisions", headers=auth_headers
            )
        ).json()["items"]
        assert history[0]["note"] == "New group terms"
        failed_attempt = (await _draft(db_client, auth_headers, site_ids[1]))["last_attempt"]
        assert (failed_attempt["action"], failed_attempt["status"]) == ("bulk_publish", "failed")
        assert (await _affected(db_client, auth_headers, group_id))[0]["site_id"] == site_ids[1]

    async def test_other_orgs_group_is_not_found(self, db_client, auth_headers, other_org_headers):
        group_id, _ = await _group_with_sites(db_client, auth_headers, 1)
        resp = await db_client.get(
            "/api/v1/config/affected-sites",
            headers=other_org_headers,
            params={"site_group_id": group_id},
        )
        assert resp.status_code == 404


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
        resp = await db_client.get(
            f"/api/v1/config/sites/{site_id}/revisions", headers=other_org_headers
        )
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
