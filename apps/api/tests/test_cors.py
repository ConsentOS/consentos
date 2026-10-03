"""Tests for the dynamic CORS origin validation service."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.cors import (
    extract_domain_from_origin,
    get_allowed_domains,
    get_allowed_domains_cached,
    invalidate_allowed_domains_cache,
    is_origin_allowed,
)


class TestExtractDomainFromOrigin:
    def test_https_origin(self):
        assert extract_domain_from_origin("https://example.com") == "example.com"

    def test_http_origin(self):
        assert extract_domain_from_origin("http://example.com") == "example.com"

    def test_origin_with_port(self):
        assert extract_domain_from_origin("https://example.com:443") == "example.com"

    def test_origin_with_subdomain(self):
        assert extract_domain_from_origin("https://www.example.com") == "www.example.com"

    def test_localhost(self):
        assert extract_domain_from_origin("http://localhost:5173") == "localhost"

    def test_empty_string(self):
        assert extract_domain_from_origin("") is None

    def test_invalid_url(self):
        # urlparse is lenient, but hostname may be None for really bad input
        result = extract_domain_from_origin("not-a-url")
        # urlparse("not-a-url") sets hostname to None
        assert result is None


class TestIsOriginAllowed:
    def test_static_origin_exact_match(self):
        assert (
            is_origin_allowed(
                "http://localhost:5173",
                ["http://localhost:5173"],
                set(),
            )
            is True
        )

    def test_static_origin_no_match(self):
        assert (
            is_origin_allowed(
                "https://evil.com",
                ["http://localhost:5173"],
                set(),
            )
            is False
        )

    def test_wildcard_allows_everything(self):
        assert (
            is_origin_allowed(
                "https://anything.com",
                ["*"],
                set(),
            )
            is True
        )

    def test_registered_domain_match(self):
        assert (
            is_origin_allowed(
                "https://example.com",
                [],
                {"example.com", "other.com"},
            )
            is True
        )

    def test_registered_domain_case_insensitive(self):
        assert (
            is_origin_allowed(
                "https://Example.COM",
                [],
                {"example.com"},
            )
            is True
        )

    def test_registered_domain_no_match(self):
        assert (
            is_origin_allowed(
                "https://evil.com",
                [],
                {"example.com"},
            )
            is False
        )

    def test_static_takes_priority(self):
        assert (
            is_origin_allowed(
                "http://localhost:5173",
                ["http://localhost:5173"],
                {"example.com"},
            )
            is True
        )

    def test_origin_with_port_matches_domain(self):
        assert (
            is_origin_allowed(
                "https://example.com:8443",
                [],
                {"example.com"},
            )
            is True
        )

    def test_subdomain_matches_if_registered(self):
        # www.example.com only matches if explicitly registered
        assert (
            is_origin_allowed(
                "https://www.example.com",
                [],
                {"example.com"},
            )
            is False
        )

    def test_subdomain_matches_when_registered(self):
        assert (
            is_origin_allowed(
                "https://www.example.com",
                [],
                {"www.example.com"},
            )
            is True
        )

    def test_empty_origin(self):
        assert (
            is_origin_allowed(
                "",
                [],
                {"example.com"},
            )
            is False
        )

    def test_empty_lists(self):
        assert (
            is_origin_allowed(
                "https://example.com",
                [],
                set(),
            )
            is False
        )


class TestGetAllowedDomains:
    @pytest.mark.asyncio
    async def test_returns_primary_domains(self):
        row1 = MagicMock()
        row1.domain = "example.com"
        row1.additional_domains = None

        row2 = MagicMock()
        row2.domain = "other.com"
        row2.additional_domains = None

        mock_result = MagicMock()
        mock_result.all.return_value = [row1, row2]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        domains = await get_allowed_domains(db)
        assert "example.com" in domains
        assert "other.com" in domains

    @pytest.mark.asyncio
    async def test_includes_additional_domains(self):
        row = MagicMock()
        row.domain = "example.com"
        row.additional_domains = ["www.example.com", "app.example.com"]

        mock_result = MagicMock()
        mock_result.all.return_value = [row]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        domains = await get_allowed_domains(db)
        assert "example.com" in domains
        assert "www.example.com" in domains
        assert "app.example.com" in domains

    @pytest.mark.asyncio
    async def test_lowercases_domains(self):
        row = MagicMock()
        row.domain = "Example.COM"
        row.additional_domains = ["WWW.Example.COM"]

        mock_result = MagicMock()
        mock_result.all.return_value = [row]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        domains = await get_allowed_domains(db)
        assert "example.com" in domains
        assert "www.example.com" in domains

    @pytest.mark.asyncio
    async def test_empty_result(self):
        mock_result = MagicMock()
        mock_result.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        domains = await get_allowed_domains(db)
        assert domains == set()


class _FakeRedis:
    """Minimal async Redis stand-in: get / set / delete on an in-memory dict."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class TestAllowedDomainsCache:
    """The Redis-backed cache that powers the dynamic CORS middleware."""

    def setup_method(self) -> None:
        import src.services.cors as cors_module

        cors_module._redis = None

    @pytest.mark.asyncio
    async def test_cache_hit_skips_database(self, monkeypatch):
        fake = _FakeRedis()
        fake.store["cmp:cors:allowed_domains"] = json.dumps(["example.com"])
        monkeypatch.setattr("src.services.cors._get_redis", lambda: fake)

        async def fake_fetch() -> set[str]:
            raise AssertionError("database must not be read on a cache hit")

        monkeypatch.setattr("src.services.cors._fetch_allowed_domains", fake_fetch)

        result = await get_allowed_domains_cached(ttl=60)
        assert result == {"example.com"}

    @pytest.mark.asyncio
    async def test_cache_miss_reads_db_and_writes_back(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("src.services.cors._get_redis", lambda: fake)

        async def fake_fetch() -> set[str]:
            return {"example.com", "other.com"}

        monkeypatch.setattr("src.services.cors._fetch_allowed_domains", fake_fetch)

        result = await get_allowed_domains_cached(ttl=60)
        assert result == {"example.com", "other.com"}
        stored = fake.store.get("cmp:cors:allowed_domains")
        assert stored is not None
        assert set(json.loads(stored)) == {"example.com", "other.com"}

    @pytest.mark.asyncio
    async def test_invalidate_deletes_cache_key(self, monkeypatch):
        fake = _FakeRedis()
        fake.store["cmp:cors:allowed_domains"] = json.dumps(["example.com"])
        monkeypatch.setattr("src.services.cors._get_redis", lambda: fake)

        await invalidate_allowed_domains_cache()
        assert "cmp:cors:allowed_domains" not in fake.store

    @pytest.mark.asyncio
    async def test_falls_back_to_db_when_redis_unavailable(self, monkeypatch):
        monkeypatch.setattr("src.services.cors._get_redis", lambda: None)

        async def fake_fetch() -> set[str]:
            return {"example.com"}

        monkeypatch.setattr("src.services.cors._fetch_allowed_domains", fake_fetch)

        result = await get_allowed_domains_cached(ttl=60)
        assert result == {"example.com"}

    @pytest.mark.asyncio
    async def test_returns_empty_set_when_db_fails_on_miss(self, monkeypatch):
        # Empty fake Redis → cache miss → database failure must not raise.
        monkeypatch.setattr("src.services.cors._get_redis", lambda: _FakeRedis())

        async def fake_fetch() -> set[str]:
            raise RuntimeError("db down")

        monkeypatch.setattr("src.services.cors._fetch_allowed_domains", fake_fetch)

        result = await get_allowed_domains_cached(ttl=60)
        assert result == set()
