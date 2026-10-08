"""Tests for the GeoIP service.

Covers header-based detection, IP lookup, country-to-region mapping,
client IP extraction, and the combined detect_region flow.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.services.geoip as geoip_module
from src.config.settings import Settings
from src.services.geoip import (
    GeoResult,
    _is_private_ip,
    country_to_region,
    detect_region,
    detect_region_from_headers,
    get_client_ip,
    lookup_ip_maxmind,
    lookup_ip_region,
)

# ── country_to_region ────────────────────────────────────────────────


class TestCountryToRegion:
    def test_eu_country_returns_eu(self):
        assert country_to_region("DE") == "EU"
        assert country_to_region("FR") == "EU"
        assert country_to_region("IT") == "EU"
        assert country_to_region("ES") == "EU"

    def test_eu_country_case_insensitive(self):
        assert country_to_region("de") == "EU"
        assert country_to_region("fr") == "EU"

    def test_gb_returns_gb(self):
        assert country_to_region("GB") == "GB"

    def test_br_returns_br(self):
        assert country_to_region("BR") == "BR"

    def test_us_without_state(self):
        assert country_to_region("US") == "US"

    def test_us_with_state(self):
        assert country_to_region("US", "CA") == "US-CA"
        assert country_to_region("US", "ny") == "US-NY"

    def test_non_eu_country_returned_as_is(self):
        assert country_to_region("JP") == "JP"
        assert country_to_region("AU") == "AU"
        assert country_to_region("CA") == "CA"


# ── detect_region_from_headers ───────────────────────────────────────


class TestDetectRegionFromHeaders:
    def _make_request(self, headers: dict[str, str]) -> MagicMock:
        request = MagicMock()
        request.headers = headers
        return request

    def test_cloudflare_header(self):
        request = self._make_request({"cf-ipcountry": "DE"})
        result = detect_region_from_headers(request)
        assert result.country_code == "DE"
        assert result.region == "EU"
        assert result.is_resolved is True

    def test_vercel_header(self):
        request = self._make_request({"x-vercel-ip-country": "GB"})
        result = detect_region_from_headers(request)
        assert result.country_code == "GB"
        assert result.region == "GB"

    def test_appengine_header(self):
        request = self._make_request({"x-appengine-country": "BR"})
        result = detect_region_from_headers(request)
        assert result.country_code == "BR"
        assert result.region == "BR"

    def test_custom_header(self):
        request = self._make_request({"x-country-code": "JP"})
        result = detect_region_from_headers(request)
        assert result.country_code == "JP"
        assert result.region == "JP"

    def test_no_geo_headers(self):
        request = self._make_request({})
        result = detect_region_from_headers(request)
        assert result.country_code is None
        assert result.region is None
        assert result.is_resolved is False

    def test_ignores_xx_value(self):
        request = self._make_request({"cf-ipcountry": "XX"})
        result = detect_region_from_headers(request)
        assert result.is_resolved is False

    def test_header_priority_cloudflare_first(self):
        request = self._make_request(
            {
                "cf-ipcountry": "FR",
                "x-vercel-ip-country": "DE",
            }
        )
        result = detect_region_from_headers(request)
        assert result.country_code == "FR"

    def test_case_normalisation(self):
        request = self._make_request({"cf-ipcountry": "gb"})
        result = detect_region_from_headers(request)
        assert result.country_code == "GB"
        assert result.region == "GB"

    def test_configured_custom_header(self):
        """An operator-configured header is honoured."""
        request = self._make_request({"x-gclb-country": "JP"})
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_country_header = "x-gclb-country"
            result = detect_region_from_headers(request)
        assert result.country_code == "JP"
        assert result.region == "JP"

    def test_configured_custom_header_takes_priority(self):
        """When both a custom and a built-in header are present, the
        custom one wins — that's the operator's explicit choice."""
        request = self._make_request(
            {
                "cf-ipcountry": "FR",
                "x-gclb-country": "JP",
            }
        )
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_country_header = "x-gclb-country"
            result = detect_region_from_headers(request)
        assert result.country_code == "JP"

    def test_configured_header_falls_through_to_builtin(self):
        """If the custom header isn't present, the built-in list still
        applies."""
        request = self._make_request({"cf-ipcountry": "FR"})
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_country_header = "x-gclb-country"
            mock_settings.return_value.geoip_region_header = None
            result = detect_region_from_headers(request)
        assert result.country_code == "FR"
        assert result.region == "EU"

    def test_configured_region_header_pairs_with_country(self):
        """A configured region header is paired with the custom country."""
        request = self._make_request(
            {
                "x-gclb-country": "US",
                "x-gclb-region": "CA",
            }
        )
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_country_header = "x-gclb-country"
            mock_settings.return_value.geoip_region_header = "x-gclb-region"
            result = detect_region_from_headers(request)
        assert result.country_code == "US"
        assert result.region == "US-CA"

    def test_configured_region_header_strips_country_prefix(self):
        """ISO 3166-2 subdivisions may arrive prefixed (``US-CA``)."""
        request = self._make_request(
            {
                "x-gclb-country": "US",
                "x-gclb-region": "US-NY",
            }
        )
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_country_header = "x-gclb-country"
            mock_settings.return_value.geoip_region_header = "x-gclb-region"
            result = detect_region_from_headers(request)
        assert result.region == "US-NY"

    def test_configured_region_header_missing_is_country_only(self):
        """Only country hits region-aware path if the region header is absent."""
        request = self._make_request({"x-gclb-country": "US"})
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_country_header = "x-gclb-country"
            mock_settings.return_value.geoip_region_header = "x-gclb-region"
            result = detect_region_from_headers(request)
        assert result.country_code == "US"
        assert result.region == "US"

    def test_configured_region_header_xx_ignored(self):
        """Region value of ``XX`` is treated as unknown."""
        request = self._make_request(
            {
                "x-gclb-country": "US",
                "x-gclb-region": "XX",
            }
        )
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_country_header = "x-gclb-country"
            mock_settings.return_value.geoip_region_header = "x-gclb-region"
            result = detect_region_from_headers(request)
        assert result.region == "US"


# ── get_client_ip ────────────────────────────────────────────────────


class TestGetClientIp:
    def _make_request(
        self,
        headers: dict[str, str] | None = None,
        client_host: str | None = None,
    ) -> MagicMock:
        request = MagicMock()
        request.headers = headers or {}
        if client_host:
            request.client = MagicMock()
            request.client.host = client_host
        else:
            request.client = None
        return request

    def _trusting(self, value: str):
        settings = Settings(trusted_proxies=value)
        return patch("src.services.client_ip.get_settings", return_value=settings)

    def test_forwarded_for_ignored_by_default(self):
        request = self._make_request({"x-forwarded-for": "1.2.3.4"}, client_host="10.0.0.1")
        with self._trusting(""):
            assert get_client_ip(request) == "10.0.0.1"

    def test_forwarded_for_from_trusted_proxy(self):
        request = self._make_request(
            {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}, client_host="10.0.0.1"
        )
        with self._trusting("10.0.0.0/8"):
            assert get_client_ip(request) == "5.6.7.8"

    def test_forwarded_for_takes_priority_over_real_ip(self):
        request = self._make_request(
            {"x-forwarded-for": "1.1.1.1", "x-real-ip": "2.2.2.2"}, client_host="10.0.0.1"
        )
        with self._trusting("10.0.0.1"):
            assert get_client_ip(request) == "1.1.1.1"

    def test_falls_back_to_client_host(self):
        request = self._make_request(client_host="10.0.0.1")
        with self._trusting(""):
            assert get_client_ip(request) == "10.0.0.1"

    def test_returns_none_when_no_ip(self):
        request = self._make_request()
        with self._trusting(""):
            assert get_client_ip(request) is None


# ── _is_private_ip ───────────────────────────────────────────────────


class TestIsPrivateIp:
    def test_loopback(self):
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("127.0.0.2") is True

    def test_private_ranges(self):
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("192.168.1.1") is True
        assert _is_private_ip("172.16.0.1") is True

    def test_ipv6_loopback(self):
        assert _is_private_ip("::1") is True

    def test_localhost_string(self):
        assert _is_private_ip("localhost") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False


# ── lookup_ip_region ─────────────────────────────────────────────────


class TestLookupIpRegion:
    @pytest.mark.asyncio
    async def test_private_ip_returns_unresolved(self):
        result = await lookup_ip_region("127.0.0.1")
        assert result.is_resolved is False

    @pytest.mark.asyncio
    async def test_private_ip_10_range(self):
        result = await lookup_ip_region("10.0.0.1")
        assert result.is_resolved is False

    @pytest.mark.asyncio
    async def test_successful_lookup(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "countryCode": "DE",
            "region": "BY",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.geoip.httpx.AsyncClient", return_value=mock_client):
            result = await lookup_ip_region("8.8.8.8")

        assert result.country_code == "DE"
        assert result.region == "EU"

    @pytest.mark.asyncio
    async def test_failed_status(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "fail", "message": "invalid query"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.geoip.httpx.AsyncClient", return_value=mock_client):
            result = await lookup_ip_region("8.8.8.8")

        assert result.is_resolved is False

    @pytest.mark.asyncio
    async def test_http_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.geoip.httpx.AsyncClient", return_value=mock_client):
            result = await lookup_ip_region("8.8.8.8")

        assert result.is_resolved is False

    @pytest.mark.asyncio
    async def test_network_exception(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.geoip.httpx.AsyncClient", return_value=mock_client):
            result = await lookup_ip_region("8.8.8.8")

        assert result.is_resolved is False

    @pytest.mark.asyncio
    async def test_us_with_state_lookup(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "countryCode": "US",
            "region": "CA",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.geoip.httpx.AsyncClient", return_value=mock_client):
            result = await lookup_ip_region("8.8.8.8")

        assert result.country_code == "US"
        assert result.region == "US-CA"

    @pytest.mark.asyncio
    async def test_missing_country_code(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.geoip.httpx.AsyncClient", return_value=mock_client):
            result = await lookup_ip_region("8.8.8.8")

        assert result.is_resolved is False


# ── detect_region (combined) ─────────────────────────────────────────


class TestDetectRegion:
    @pytest.mark.asyncio
    async def test_uses_headers_when_available(self):
        request = MagicMock()
        request.headers = {"cf-ipcountry": "FR"}
        request.client = None

        result = await detect_region(request)
        assert result.country_code == "FR"
        assert result.region == "EU"

    @pytest.mark.asyncio
    async def test_falls_back_to_ip_lookup(self):
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "8.8.8.8"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "countryCode": "US",
            "region": "CA",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.geoip.httpx.AsyncClient", return_value=mock_client):
            result = await detect_region(request)

        assert result.country_code == "US"
        assert result.region == "US-CA"

    @pytest.mark.asyncio
    async def test_returns_unresolved_when_no_ip(self):
        request = MagicMock()
        request.headers = {}
        request.client = None

        result = await detect_region(request)
        assert result.is_resolved is False


# ── GeoResult ────────────────────────────────────────────────────────


class TestGeoResult:
    def test_is_resolved_true(self):
        result = GeoResult(country_code="GB", region="GB")
        assert result.is_resolved is True

    def test_is_resolved_false(self):
        result = GeoResult(country_code=None, region=None)
        assert result.is_resolved is False

    def test_frozen_dataclass(self):
        result = GeoResult(country_code="GB", region="GB")
        with pytest.raises(AttributeError):
            result.country_code = "US"  # type: ignore[misc]


# ── MaxMind database lookup ──────────────────────────────────────────


class TestLookupIpMaxmind:
    def setup_method(self):
        # Reset the module-level cache so each test starts clean.
        geoip_module._maxmind_reader = None
        geoip_module._maxmind_initialised = False

    def _mock_reader(self, country_iso: str | None, subdivision_iso: str | None):
        reader = MagicMock()
        response = MagicMock()
        response.country.iso_code = country_iso
        if subdivision_iso is None:
            response.subdivisions = None
        else:
            response.subdivisions.most_specific.iso_code = subdivision_iso
        reader.city.return_value = response
        return reader

    def test_private_ip_returns_unresolved(self):
        result = lookup_ip_maxmind("10.0.0.1")
        assert result.is_resolved is False

    def test_no_db_configured_returns_unresolved(self):
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_maxmind_db_path = None
            result = lookup_ip_maxmind("8.8.8.8")
        assert result.is_resolved is False

    def test_successful_lookup_with_subdivision(self):
        reader = self._mock_reader("US", "CA")
        geoip_module._maxmind_reader = reader
        geoip_module._maxmind_initialised = True

        result = lookup_ip_maxmind("8.8.8.8")
        assert result.country_code == "US"
        assert result.region == "US-CA"
        reader.city.assert_called_once_with("8.8.8.8")

    def test_successful_lookup_without_subdivision(self):
        reader = self._mock_reader("DE", None)
        geoip_module._maxmind_reader = reader
        geoip_module._maxmind_initialised = True

        result = lookup_ip_maxmind("8.8.8.8")
        assert result.country_code == "DE"
        assert result.region == "EU"

    def test_reader_raises_returns_unresolved(self):
        reader = MagicMock()
        reader.city.side_effect = RuntimeError("corrupt db")
        geoip_module._maxmind_reader = reader
        geoip_module._maxmind_initialised = True

        result = lookup_ip_maxmind("8.8.8.8")
        assert result.is_resolved is False

    def test_reader_missing_country_returns_unresolved(self):
        reader = self._mock_reader(None, None)
        geoip_module._maxmind_reader = reader
        geoip_module._maxmind_initialised = True

        result = lookup_ip_maxmind("8.8.8.8")
        assert result.is_resolved is False

    def test_bad_db_path_is_cached_as_failure(self):
        """A missing ``.mmdb`` file should not reopen on every request."""
        with patch("src.services.geoip.get_settings") as mock_settings:
            mock_settings.return_value.geoip_maxmind_db_path = "/nonexistent/geo.mmdb"
            r1 = lookup_ip_maxmind("8.8.8.8")
            r2 = lookup_ip_maxmind("1.1.1.1")
        assert r1.is_resolved is False
        assert r2.is_resolved is False
        assert geoip_module._maxmind_initialised is True
        assert geoip_module._maxmind_reader is None


class TestDetectRegionMaxmind:
    def setup_method(self):
        geoip_module._maxmind_reader = None
        geoip_module._maxmind_initialised = False

    @pytest.mark.asyncio
    async def test_uses_maxmind_before_external_api(self):
        """With MaxMind configured, ip-api.com must not be called."""
        reader = MagicMock()
        response = MagicMock()
        response.country.iso_code = "GB"
        response.subdivisions.most_specific.iso_code = "SCT"
        reader.city.return_value = response
        geoip_module._maxmind_reader = reader
        geoip_module._maxmind_initialised = True

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "8.8.8.8"

        with (
            patch("src.services.geoip.get_settings") as mock_settings,
            patch("src.services.geoip.httpx.AsyncClient") as mock_httpx,
        ):
            mock_settings.return_value.geoip_country_header = None
            mock_settings.return_value.geoip_region_header = None
            mock_settings.return_value.geoip_maxmind_db_path = "/data/GeoLite2-City.mmdb"

            result = await detect_region(request)

        assert result.country_code == "GB"
        assert result.region == "GB-SCT"
        mock_httpx.assert_not_called()
