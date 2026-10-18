"""Integration tests for the publishing extension points (neutral fixtures)."""

import logging
import uuid

import pytest
from sqlalchemy import text

from src.extensions.registry import get_registry
from tests.conftest import create_test_site, publish_site, requires_db


@pytest.fixture
def registered():
    """Register hooks for one test and remove them afterwards."""
    added: list[tuple[list, object]] = []

    def register(kind: str, fn):
        hooks = getattr(get_registry(), kind)
        hooks.append(fn)
        added.append((hooks, fn))
        return fn

    yield register
    for hooks, fn in added:
        hooks.remove(fn)


async def _draft(client, headers, site_id) -> dict:
    return (await client.get(f"/api/v1/config/sites/{site_id}/draft", headers=headers)).json()


async def _publish(client, headers, site_id):
    draft = await _draft(client, headers, site_id)
    return await client.post(
        f"/api/v1/config/sites/{site_id}/publish",
        headers=headers,
        json={"expected_content_hash": draft["content_hash"]},
    )


async def _edit(client, headers, site_id, **fields):
    resp = await client.patch(f"/api/v1/sites/{site_id}/config", headers=headers, json=fields)
    assert resp.status_code == 200, resp.text


@requires_db
class TestPrePublishChecks:
    async def test_a_check_can_block_with_a_reason(self, db_client, auth_headers, registered):
        site_id = await create_test_site(db_client, auth_headers)
        live = await publish_site(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")

        async def block(db, site, action, snapshot):
            return "Terms must be reviewed first"

        registered("pre_publish_checks", block)
        resp = await _publish(db_client, auth_headers, site_id)

        assert resp.status_code == 409
        assert resp.json()["detail"] == "Terms must be reviewed first"
        draft = await _draft(db_client, auth_headers, site_id)
        assert draft["live_revision"]["id"] == live["id"]
        attempt = draft["last_attempt"]
        assert (attempt["error_code"], attempt["error_message"]) == (
            "blocked_by_check",
            "Terms must be reviewed first",
        )

    async def test_checks_see_the_action_and_snapshot(self, db_client, auth_headers, registered):
        seen = []

        async def record(db, site, action, snapshot):
            seen.append((action, snapshot["config"].get("terms_url")))
            return None

        site_id = await create_test_site(db_client, auth_headers)
        registered("pre_publish_checks", record)
        first = await publish_site(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/t")
        draft = await _draft(db_client, auth_headers, site_id)
        await db_client.post(
            "/api/v1/config/bulk-publish",
            headers=auth_headers,
            json={"sites": [{"site_id": site_id, "expected_content_hash": draft["content_hash"]}]},
        )
        await db_client.post(
            f"/api/v1/config/sites/{site_id}/revisions/{first['id']}/rollback",
            headers=auth_headers,
            json={},
        )

        assert seen == [
            ("publish", None),
            ("bulk_publish", "https://x.test/t"),
            ("rollback", None),
        ]


@requires_db
class TestPostPublishHooks:
    async def test_called_with_the_new_revision(self, db_client, auth_headers, registered):
        published = []

        async def hook(db, revision):
            published.append(revision.number)

        registered("post_publish_hooks", hook)
        site_id = await create_test_site(db_client, auth_headers)
        await publish_site(db_client, auth_headers, site_id)
        assert published == [1]

    async def test_a_failing_hook_does_not_undo_the_publish(
        self, db_client, auth_headers, registered, caplog
    ):
        async def broken(db, revision):
            # Breaks the transaction it runs in, which must not be the
            # publish's own.
            await db.execute(text("SELECT 1 / 0"))

        registered("post_publish_hooks", broken)
        site_id = await create_test_site(db_client, auth_headers)

        with caplog.at_level(logging.ERROR, logger="src.services.config_publishing"):
            resp = await _publish(db_client, auth_headers, site_id)

        assert resp.status_code == 200, resp.text
        assert "Post-publish hook" in caplog.text
        served = await db_client.get(f"/api/v1/config/sites/{site_id}/geo-resolved")
        assert served.json()["revision_id"] == resp.json()["id"]


@requires_db
class TestConfigSourceProviders:
    async def test_extra_layers_prompt_a_publish_when_they_change(
        self, db_client, auth_headers, registered
    ):
        layer = {"values": {"theme": "light"}}

        async def provide(db, site_id):
            return [{"kind": "example_layer", "id": uuid.UUID(int=7), "values": layer["values"]}]

        registered("config_source_providers", provide)
        site_id = await create_test_site(db_client, auth_headers)
        await publish_site(db_client, auth_headers, site_id)
        assert (await _draft(db_client, auth_headers, site_id))["changed_sources"] == []

        layer["values"] = {"theme": "dark"}

        changed = (await _draft(db_client, auth_headers, site_id))["changed_sources"]
        assert changed == [{"kind": "example_layer", "id": str(uuid.UUID(int=7))}]
