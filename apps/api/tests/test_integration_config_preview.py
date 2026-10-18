"""Integration tests for draft preview links."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from jose import jwt

from src.config.settings import get_settings
from tests.conftest import create_test_site, publish_site, requires_db


async def _preview_link(client, headers, site_id) -> dict:
    resp = await client.post(f"/api/v1/config/sites/{site_id}/preview", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _banner(client, site_id, token=None):
    params = {"preview": token} if token else {}
    return await client.get(f"/api/v1/config/sites/{site_id}/geo-resolved", params=params)


async def _edit(client, headers, site_id, **fields):
    resp = await client.patch(f"/api/v1/sites/{site_id}/config", headers=headers, json=fields)
    assert resp.status_code == 200, resp.text


def _token(**claims) -> str:
    settings = get_settings()
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@requires_db
class TestPreviewLinks:
    async def test_link_opens_the_site_with_a_token(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        domain = (await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)).json()[
            "domain"
        ]

        link = await _preview_link(db_client, auth_headers, site_id)

        url = urlparse(link["url"])
        assert (url.scheme, url.netloc) == ("https", domain)
        assert parse_qs(url.query)["consentos_preview"] == [link["token"]]
        expires_at = datetime.fromisoformat(link["expires_at"])
        assert timedelta(minutes=25) < expires_at - datetime.now(UTC) <= timedelta(minutes=30)

    async def test_holder_sees_the_draft_and_visitors_see_live(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await publish_site(db_client, auth_headers, site_id)
        await _edit(db_client, auth_headers, site_id, terms_url="https://x.test/draft")
        token = (await _preview_link(db_client, auth_headers, site_id))["token"]

        previewed = await _banner(db_client, site_id, token)
        live = await _banner(db_client, site_id)

        assert previewed.json()["preview"] is True
        assert previewed.json()["terms_url"] == "https://x.test/draft"
        assert previewed.json()["revision_id"] is None
        assert previewed.headers["cache-control"] == "no-store"
        assert "preview" not in live.json()
        assert live.json()["terms_url"] is None

    async def test_works_before_the_first_publish(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        token = (await _preview_link(db_client, auth_headers, site_id))["token"]
        assert (await _banner(db_client, site_id, token)).json()["preview"] is True
        assert (await _banner(db_client, site_id)).status_code == 404


@requires_db
class TestInvalidPreviewTokens:
    async def _site(self, client, headers) -> str:
        site_id = await create_test_site(client, headers)
        await publish_site(client, headers, site_id)
        return site_id

    async def test_expired(self, db_client, auth_headers):
        site_id = await self._site(db_client, auth_headers)
        token = _token(
            type="config_preview",
            site_id=site_id,
            exp=datetime.now(UTC) - timedelta(minutes=1),
        )
        assert "preview" not in (await _banner(db_client, site_id, token)).json()

    async def test_tampered(self, db_client, auth_headers):
        site_id = await self._site(db_client, auth_headers)
        token = (await _preview_link(db_client, auth_headers, site_id))["token"]
        header, payload, signature = token.split(".")
        tampered = f"{header}.{payload}.{signature[::-1]}"
        assert "preview" not in (await _banner(db_client, site_id, tampered)).json()

    async def test_for_another_site(self, db_client, auth_headers):
        site_id = await self._site(db_client, auth_headers)
        other = await create_test_site(db_client, auth_headers)
        token = (await _preview_link(db_client, auth_headers, other))["token"]
        assert "preview" not in (await _banner(db_client, site_id, token)).json()

    async def test_sign_in_token_is_not_a_preview_token(self, db_client, auth_headers, auth_token):
        site_id = await self._site(db_client, auth_headers)
        assert "preview" not in (await _banner(db_client, site_id, auth_token)).json()

    async def test_preview_token_is_not_a_sign_in_token(self, db_client, auth_headers):
        site_id = await self._site(db_client, auth_headers)
        token = (await _preview_link(db_client, auth_headers, site_id))["token"]
        resp = await db_client.get(
            f"/api/v1/sites/{site_id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401
