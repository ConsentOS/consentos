"""GET /sites/{id}/install: what a site's install snippet needs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.routers.sites import _base_url

try:
    from tests.conftest import create_test_site, requires_db
except ImportError:
    from conftest import create_test_site, requires_db


def _settings(**values):
    return SimpleNamespace(**{"public_api_url": None, "cdn_base_url": None, **values})


@requires_db
class TestSiteInstall:
    async def test_uses_the_configured_public_urls(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, start_scan=False)
        settings = _settings(
            public_api_url="https://api.example.net/", cdn_base_url="https://cdn.example.net/banner"
        )
        with patch("src.routers.sites.get_settings", return_value=settings):
            resp = await db_client.get(f"/api/v1/sites/{site_id}/install", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["api_base"] == "https://api.example.net"
        assert data["cdn_base"] == "https://cdn.example.net/banner"

    async def test_unset_urls_are_null(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, start_scan=False)
        with patch("src.routers.sites.get_settings", return_value=_settings()):
            resp = await db_client.get(f"/api/v1/sites/{site_id}/install", headers=auth_headers)

        assert resp.json()["api_base"] is None
        assert resp.json()["cdn_base"] is None

    async def test_lists_the_sites_domains(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, start_scan=False)
        site = (await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)).json()
        await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"additional_domains": ["shop.example.org"]},
            headers=auth_headers,
        )

        resp = await db_client.get(f"/api/v1/sites/{site_id}/install", headers=auth_headers)

        assert resp.json()["domains"] == [site["domain"], "shop.example.org"]

    async def test_other_organisations_cannot_see_it(
        self, db_client, auth_headers, other_org_headers
    ):
        site_id = await create_test_site(db_client, auth_headers, start_scan=False)
        resp = await db_client.get(f"/api/v1/sites/{site_id}/install", headers=other_org_headers)
        assert resp.status_code == 404


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("https://cdn.example.net/", "https://cdn.example.net"),
        ("https://cdn.example.net/banner//", "https://cdn.example.net/banner"),
    ],
)
def test_base_url_normalisation(value, expected):
    assert _base_url(value) == expected
