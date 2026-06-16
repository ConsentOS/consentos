"""Tests for the update-check service and endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.settings import Settings
from src.services import update_check


def _settings(**overrides) -> Settings:
    base = {
        "app_version": "0.2.0",
        "update_check_repo": "ConsentOS/consentos",
    }
    base.update(overrides)
    return Settings(**base)


# ── is_newer ─────────────────────────────────────────────────────────


class TestIsNewer:
    def test_higher_latest_is_newer(self):
        assert update_check.is_newer("0.2.0", "0.3.0") is True
        assert update_check.is_newer("0.2.0", "1.0.0") is True
        assert update_check.is_newer("0.2.0", "0.2.1") is True

    def test_same_or_lower_is_not_newer(self):
        assert update_check.is_newer("0.2.0", "0.2.0") is False
        assert update_check.is_newer("0.3.0", "0.2.0") is False

    def test_ignores_v_prefix(self):
        assert update_check.is_newer("0.2.0", "v0.3.0") is True
        assert update_check.is_newer("v0.2.0", "0.2.0") is False

    def test_dev_sentinel_never_newer_than_real_release_the_other_way(self):
        # A real release is always newer than the dev sentinel.
        assert update_check.is_newer("0.0.0-dev", "0.2.0") is True

    def test_unparseable_versions_are_not_newer(self):
        assert update_check.is_newer("0.2.0", "nightly") is False
        assert update_check.is_newer("garbage", "0.3.0") is False


# ── fetch_latest_version ─────────────────────────────────────────────


def _mock_httpx(status_code: int, json_body: dict | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {}
    client = AsyncMock()
    client.get.return_value = response
    ctx = AsyncMock()
    ctx.__aenter__.return_value = client
    return ctx


class TestFetchLatestVersion:
    @pytest.mark.asyncio
    async def test_returns_tag_without_v_prefix(self):
        with patch(
            "src.services.update_check.httpx.AsyncClient",
            return_value=_mock_httpx(200, {"tag_name": "v0.3.0"}),
        ):
            assert await update_check.fetch_latest_version(_settings()) == "0.3.0"

    @pytest.mark.asyncio
    async def test_non_200_returns_none(self):
        with patch(
            "src.services.update_check.httpx.AsyncClient",
            return_value=_mock_httpx(403, {}),
        ):
            assert await update_check.fetch_latest_version(_settings()) is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        with patch(
            "src.services.update_check.httpx.AsyncClient",
            side_effect=RuntimeError("boom"),
        ):
            assert await update_check.fetch_latest_version(_settings()) is None

    @pytest.mark.asyncio
    async def test_missing_tag_returns_none(self):
        with patch(
            "src.services.update_check.httpx.AsyncClient",
            return_value=_mock_httpx(200, {"name": "no tag here"}),
        ):
            assert await update_check.fetch_latest_version(_settings()) is None


# ── get_version_info ─────────────────────────────────────────────────


class TestGetVersionInfo:
    @pytest.mark.asyncio
    async def test_no_cached_version_reports_no_update(self):
        with patch(
            "src.services.update_check.get_cached_latest_version",
            new_callable=AsyncMock,
            return_value=None,
        ):
            info = await update_check.get_version_info(_settings())
        assert info["latest"] is None
        assert info["update_available"] is False

    @pytest.mark.asyncio
    async def test_newer_cached_version_flags_update(self):
        with patch(
            "src.services.update_check.get_cached_latest_version",
            new_callable=AsyncMock,
            return_value="0.3.0",
        ):
            info = await update_check.get_version_info(_settings())
        assert info == {"current": "0.2.0", "latest": "0.3.0", "update_available": True}

    @pytest.mark.asyncio
    async def test_same_cached_version_no_update(self):
        with patch(
            "src.services.update_check.get_cached_latest_version",
            new_callable=AsyncMock,
            return_value="0.2.0",
        ):
            info = await update_check.get_version_info(_settings())
        assert info["update_available"] is False

    @pytest.mark.asyncio
    async def test_prefixed_app_version_is_normalised(self):
        with patch(
            "src.services.update_check.get_cached_latest_version",
            new_callable=AsyncMock,
            return_value="0.3.0",
        ):
            info = await update_check.get_version_info(_settings(app_version="v0.2.0"))
        assert info["current"] == "0.2.0"


# ── Endpoint ─────────────────────────────────────────────────────────


class TestSystemVersionRoute:
    def test_version_route_registered(self, app):
        assert "/api/v1/system/version" in list(app.openapi()["paths"])

    @pytest.mark.asyncio
    async def test_version_requires_auth(self, client):
        resp = await client.get("/api/v1/system/version")
        assert resp.status_code == 401
