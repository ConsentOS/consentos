"""Tests for known cookies database and auto-categorisation engine — CMP-22.

Covers:
  - Classification service logic (unit tests — pure functions)
  - Pattern matching (exact, wildcard, regex)
  - Priority ordering (allow-list → exact → regex → unmatched)
  - Known cookie CRUD endpoints (unit tests with mocked DB)
  - Classification endpoints (unit tests with mocked DB)
  - Schema validation
  - Integration tests against live database
"""

import re
import time
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.schemas.cookie import (
    ClassificationResultResponse,
    ClassifySingleRequest,
    ClassifySiteResponse,
    KnownCookieCreate,
    KnownCookieResponse,
    KnownCookieUpdate,
)
from src.services.classification import (
    ClassificationResult,
    MatchSource,
    _ensure_compiled,
    _match_pattern,
    _match_regex_known,
    _wildcard_match,
    classify_cookie,
    classify_site_cookies,
)

# ── Schema tests ─────────────────────────────────────────────────────


class TestSchemas:
    """Validate known cookie and classification schemas."""

    def test_known_cookie_create(self):
        kc = KnownCookieCreate(
            name_pattern="_ga",
            domain_pattern="*",
            category_id=uuid.uuid4(),
            vendor="Google",
            description="GA cookie",
        )
        assert kc.is_regex is False

    def test_known_cookie_create_regex(self):
        kc = KnownCookieCreate(
            name_pattern="_hj.*",
            domain_pattern=".*",
            category_id=uuid.uuid4(),
            is_regex=True,
        )
        assert kc.is_regex is True

    @pytest.mark.parametrize("field", ["name_pattern", "domain_pattern"])
    def test_known_cookie_create_rejects_nested_quantifier(self, field):
        data = {"name_pattern": "_hj.*", "domain_pattern": ".*", "category_id": uuid.uuid4()}
        data[field] = "(a+)+"
        with pytest.raises(ValidationError, match="must not repeat"):
            KnownCookieCreate(**data, is_regex=True)

    def test_known_cookie_create_rejects_invalid_regex(self):
        with pytest.raises(ValidationError, match="Invalid regular expression"):
            KnownCookieCreate(
                name_pattern="[abc",
                domain_pattern=".*",
                category_id=uuid.uuid4(),
                is_regex=True,
            )

    def test_known_cookie_create_skips_regex_checks_for_globs(self):
        kc = KnownCookieCreate(name_pattern="*_ga", domain_pattern="*", category_id=uuid.uuid4())
        assert kc.name_pattern == "*_ga"

    def test_known_cookie_update_partial(self):
        ku = KnownCookieUpdate(vendor="Updated Vendor")
        dumped = ku.model_dump(exclude_unset=True)
        assert "vendor" in dumped
        assert "category_id" not in dumped

    def test_known_cookie_response(self):
        resp = KnownCookieResponse(
            id=uuid.uuid4(),
            name_pattern="_ga",
            domain_pattern="*",
            category_id=uuid.uuid4(),
            is_regex=False,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert resp.vendor is None

    def test_classification_result_response(self):
        crr = ClassificationResultResponse(
            cookie_name="_ga",
            cookie_domain=".example.com",
            match_source="known_exact",
            matched=True,
        )
        assert crr.matched is True

    def test_classify_single_request(self):
        req = ClassifySingleRequest(cookie_name="_ga", cookie_domain=".example.com")
        assert req.cookie_name == "_ga"

    def test_classify_single_request_validation(self):
        with pytest.raises(ValueError):
            ClassifySingleRequest(cookie_name="", cookie_domain=".example.com")

    def test_classify_site_response(self):
        resp = ClassifySiteResponse(
            site_id="abc",
            total=10,
            matched=7,
            unmatched=3,
            results=[],
        )
        assert resp.matched == 7

    def test_match_source_enum(self):
        assert MatchSource.ALLOW_LIST == "allow_list"
        assert MatchSource.KNOWN_EXACT == "known_exact"
        assert MatchSource.KNOWN_REGEX == "known_regex"
        assert MatchSource.UNMATCHED == "unmatched"


# ── Pattern matching unit tests ──────────────────────────────────────


class TestPatternMatching:
    """Test glob matching and compiled regex known-cookie matching."""

    @staticmethod
    def _regex_matches(pattern: str, value: str) -> bool:
        known = _make_known(pattern, ".*", uuid.uuid4(), is_regex=True)
        return _match_regex_known(value, ".example.com", _ensure_compiled([known])) is known

    def test_exact_match(self):
        assert _match_pattern("_ga", "_ga") is True

    def test_exact_match_case_insensitive(self):
        assert _match_pattern("_GA", "_ga") is True
        assert _match_pattern("_ga", "_GA") is True

    def test_exact_no_match(self):
        assert _match_pattern("_ga", "_gid") is False

    def test_wildcard_star(self):
        assert _match_pattern("*", "_ga") is True
        assert _match_pattern("*", "anything") is True

    def test_wildcard_prefix(self):
        assert _match_pattern("_ga_*", "_ga_ABC123") is True
        assert _match_pattern("_ga_*", "_ga_") is True
        assert _match_pattern("_ga_*", "_gid") is False

    def test_wildcard_suffix(self):
        assert _match_pattern("*.google.com", ".google.com") is True
        assert _match_pattern("*.google.com", "www.google.com") is True
        assert _match_pattern("*.google.com", ".facebook.com") is False

    def test_wildcard_middle(self):
        assert _match_pattern("_ga*id", "_ga_gid") is True  # * matches _g
        assert _match_pattern("_ga*id", "_gaid") is True
        assert _match_pattern("_ga*id", "_ga") is False  # must end in id

    def test_empty_values(self):
        assert _match_pattern("", "_ga") is False
        assert _match_pattern("_ga", "") is False
        assert _match_pattern("", "") is False

    def test_wildcard_edge_cases(self):
        assert _match_pattern("**", "_ga") is True
        assert _match_pattern("_ga**", "_ga") is True
        assert _match_pattern("*_ga*", "x_gax") is True
        assert _match_pattern("a*b*c", "abc") is True
        assert _match_pattern("a*b*c", "acb") is False
        assert _match_pattern("a*a", "a") is False

    def test_wildcard_matches_previous_regex_behaviour(self):
        alphabet = "ab*"
        values = ["", "a", "b", "ab", "ba", "aab", "abab", "bbba", "aaaa"]

        def old_match(pattern: str, value: str) -> bool:
            regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
            return bool(re.match(regex, value))

        patterns = [""]
        for _ in range(4):
            patterns += [p + ch for p in patterns for ch in alphabet]
        for pattern in {p for p in patterns if "*" in p}:
            for value in values:
                expected = old_match(pattern, value)
                assert _wildcard_match(pattern, value) is expected, (pattern, value)

    def test_wildcard_with_many_stars_stays_fast(self):
        pattern = "*a" * 20 + "*b"
        value = "a" * 4096
        started = time.perf_counter()
        assert _match_pattern(pattern, value) is False
        assert time.perf_counter() - started < 1.0

    def test_regex_match(self):
        assert self._regex_matches(r"_hj.*", "_hjSession_12345") is True
        assert self._regex_matches(r"_hj.*", "_ga") is False

    def test_regex_case_insensitive(self):
        assert self._regex_matches(r"_hj.*", "_HJSession") is True

    def test_regex_anchored(self):
        # re.match anchors at start by default
        assert self._regex_matches(r"_pk_id.*", "_pk_id.abc.123") is True
        assert self._regex_matches(r"_pk_id.*", "x_pk_id") is False

    def test_regex_invalid_pattern(self):
        assert self._regex_matches(r"[invalid", "test") is False

    def test_regex_full_domain_match(self):
        assert self._regex_matches(r".*", ".example.com") is True

    def test_wildcard_dynamic_id_suffix(self):
        """Cookies with dynamic IDs should match wildcard prefix patterns."""
        assert _match_pattern("_hjSessionUser_*", "_hjSessionUser_1150536") is True
        assert _match_pattern("_hjSession_*", "_hjSession_9876543") is True
        assert _match_pattern("ri--*", "ri--zC77O2yRxuIvW5fjRAq0RdzNYaF-x") is True
        assert _match_pattern("intercom-id-*", "intercom-id-abc123def") is True
        assert _match_pattern("amp_*", "amp_ff29a3") is True
        assert _match_pattern("mp_*", "mp_abc123_mixpanel") is True

    def test_wildcard_does_not_overmatch(self):
        """Wildcard patterns should not match unrelated cookies."""
        assert _match_pattern("_hjSessionUser_*", "_hjSession_123") is False
        assert _match_pattern("ri--*", "ri-single-dash") is False
        assert _match_pattern("intercom-id-*", "intercom-session-xyz") is False


# ── Classification engine unit tests ─────────────────────────────────


def _make_category(slug: str, cat_id: uuid.UUID | None = None):
    """Create a mock CookieCategory."""
    cat = MagicMock()
    cat.id = cat_id or uuid.uuid4()
    cat.slug = slug
    return cat


def _make_known(
    name_pattern: str,
    domain_pattern: str,
    category_id: uuid.UUID,
    vendor: str | None = None,
    description: str | None = None,
    is_regex: bool = False,
):
    """Create a mock KnownCookie."""
    known = MagicMock()
    known.name_pattern = name_pattern
    known.domain_pattern = domain_pattern
    known.category_id = category_id
    known.vendor = vendor
    known.description = description
    known.is_regex = is_regex
    return known


def _make_allow_entry(
    name_pattern: str,
    domain_pattern: str,
    category_id: uuid.UUID,
    description: str | None = None,
):
    """Create a mock CookieAllowListEntry."""
    entry = MagicMock()
    entry.name_pattern = name_pattern
    entry.domain_pattern = domain_pattern
    entry.category_id = category_id
    entry.description = description
    return entry


class TestClassifyCookie:
    """Test the classify_cookie pure function."""

    def setup_method(self):
        self.analytics_cat = _make_category("analytics")
        self.marketing_cat = _make_category("marketing")
        self.necessary_cat = _make_category("necessary")
        self.category_map = {
            self.analytics_cat.id: self.analytics_cat,
            self.marketing_cat.id: self.marketing_cat,
            self.necessary_cat.id: self.necessary_cat,
        }

    def test_exact_known_match(self):
        known = _make_known("_ga", "*", self.analytics_cat.id, vendor="Google")
        result = classify_cookie("_ga", ".example.com", [], [known], [], self.category_map)
        assert result.matched is True
        assert result.match_source == MatchSource.KNOWN_EXACT
        assert result.category_slug == "analytics"
        assert result.vendor == "Google"

    def test_regex_known_match(self):
        known = _make_known(
            r"_hj.*",
            r".*",
            self.analytics_cat.id,
            vendor="Hotjar",
            is_regex=True,
        )
        result = classify_cookie(
            "_hjSession_123",
            ".example.com",
            [],
            [],
            [known],
            self.category_map,
        )
        assert result.matched is True
        assert result.match_source == MatchSource.KNOWN_REGEX
        assert result.vendor == "Hotjar"

    def test_allow_list_match(self):
        entry = _make_allow_entry(
            "_custom_cookie",
            "*",
            self.necessary_cat.id,
            description="Site-specific override",
        )
        result = classify_cookie(
            "_custom_cookie",
            ".example.com",
            [entry],
            [],
            [],
            self.category_map,
        )
        assert result.matched is True
        assert result.match_source == MatchSource.ALLOW_LIST
        assert result.category_slug == "necessary"

    def test_allow_list_takes_priority_over_known(self):
        """Allow-list should override known cookies database."""
        allow_entry = _make_allow_entry(
            "_ga",
            "*",
            self.necessary_cat.id,
            description="Overridden to necessary",
        )
        known = _make_known("_ga", "*", self.analytics_cat.id, vendor="Google")
        result = classify_cookie(
            "_ga",
            ".example.com",
            [allow_entry],
            [known],
            [],
            self.category_map,
        )
        assert result.match_source == MatchSource.ALLOW_LIST
        assert result.category_slug == "necessary"

    def test_exact_takes_priority_over_regex(self):
        """Exact match should be preferred over regex match."""
        exact = _make_known("_ga", "*", self.analytics_cat.id, vendor="Google")
        regex = _make_known(
            r"_g.*",
            r".*",
            self.marketing_cat.id,
            vendor="Other",
            is_regex=True,
        )
        result = classify_cookie(
            "_ga",
            ".example.com",
            [],
            [exact],
            [regex],
            self.category_map,
        )
        assert result.match_source == MatchSource.KNOWN_EXACT
        assert result.category_slug == "analytics"

    def test_unmatched(self):
        result = classify_cookie(
            "obscure_cookie",
            ".unknown.com",
            [],
            [],
            [],
            self.category_map,
        )
        assert result.matched is False
        assert result.match_source == MatchSource.UNMATCHED
        assert result.category_id is None

    def test_domain_must_match(self):
        """Cookie should not match if domain pattern doesn't match."""
        known = _make_known("_ga", "*.google.com", self.analytics_cat.id)
        result = classify_cookie(
            "_ga",
            ".example.com",
            [],
            [known],
            [],
            self.category_map,
        )
        assert result.matched is False

    def test_name_must_match(self):
        """Cookie should not match if name pattern doesn't match."""
        known = _make_known("_gid", "*", self.analytics_cat.id)
        result = classify_cookie(
            "_ga",
            ".example.com",
            [],
            [known],
            [],
            self.category_map,
        )
        assert result.matched is False

    def test_wildcard_domain_match(self):
        known = _make_known(
            "fr",
            "*.facebook.com",
            self.marketing_cat.id,
            vendor="Meta",
        )
        result = classify_cookie(
            "fr",
            ".facebook.com",
            [],
            [known],
            [],
            self.category_map,
        )
        assert result.matched is True
        assert result.vendor == "Meta"

    def test_invalid_stored_regex_is_skipped(self, caplog):
        bad = _make_known(r"(a+)+$", ".*", self.marketing_cat.id, is_regex=True)
        broken = _make_known("[abc", ".*", self.marketing_cat.id, is_regex=True)
        good = _make_known(r"_hj.*", ".*", self.analytics_cat.id, is_regex=True)

        with caplog.at_level("WARNING", logger="src.services.classification"):
            result = classify_cookie(
                "_hjSession", ".example.com", [], [], [bad, broken, good], self.category_map
            )

        assert result.match_source == MatchSource.KNOWN_REGEX
        assert result.category_id == self.analytics_cat.id
        assert caplog.text.count("Skipping known cookie") == 2

    def test_precompiled_regex_known(self):
        known = _make_known(r"_pk_id.*", ".*", self.analytics_cat.id, is_regex=True)
        compiled = _ensure_compiled([known])
        result = classify_cookie(
            "_pk_id.1.abc", ".example.com", [], [], compiled, self.category_map
        )
        assert result.match_source == MatchSource.KNOWN_REGEX

    def test_classification_result_fields(self):
        result = ClassificationResult(
            cookie_name="_ga",
            cookie_domain=".example.com",
        )
        assert result.category_id is None
        assert result.match_source == MatchSource.UNMATCHED
        assert result.matched is False


class TestClassifySiteCookies:
    """Run the DB-backed entry point against a mocked session."""

    @staticmethod
    def _result(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    @pytest.mark.asyncio
    async def test_invalid_stored_regex_skipped(self, caplog):
        analytics = _make_category("analytics")
        good = _make_known(r"_hj.*", ".*", analytics.id, vendor="Hotjar", is_regex=True)
        bad = _make_known(r"(a+)+", ".*", analytics.id, is_regex=True)
        cookie = MagicMock()
        cookie.name = "_hjSession_1"
        cookie.domain = ".example.com"
        cookie.category_id = None
        cookie.vendor = None
        cookie.description = None

        db = AsyncMock()
        db.execute.side_effect = [
            self._result([]),
            self._result([bad, good]),
            self._result([analytics]),
            self._result([cookie]),
        ]

        with caplog.at_level("WARNING", logger="src.services.classification"):
            results = await classify_site_cookies(db, uuid.uuid4())

        assert [r.match_source for r in results] == [MatchSource.KNOWN_REGEX]
        assert cookie.category_id == analytics.id
        assert cookie.vendor == "Hotjar"
        assert "Skipping known cookie" in caplog.text


# ── Router unit tests (mocked service) ──────────────────────────────


def _mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result
    return db


async def _client(app, db):
    """Create an async test client with mocked DB and auth."""
    from src.db import get_db
    from src.services.dependencies import get_current_user, require_role, require_superuser

    user = MagicMock()
    user.organisation_id = uuid.uuid4()
    user.role = "owner"

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_superuser] = lambda: user

    def _override_require_role(*_roles):
        return lambda: user

    app.dependency_overrides[require_role] = _override_require_role

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestKnownCookieRoutes:
    """Test known cookie CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_known_cookies(self, app):
        db = _mock_db()
        async with await _client(app, db) as client:
            resp = await client.get("/api/v1/cookies/known")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_create_known_cookie(self, app):
        db = _mock_db()
        # Mock category validation
        cat_result = MagicMock()
        cat_result.scalar_one_or_none.return_value = MagicMock()
        # Mock the created known cookie
        known_mock = MagicMock()
        known_mock.id = uuid.uuid4()
        known_mock.name_pattern = "_ga"
        known_mock.domain_pattern = "*"
        known_mock.category_id = uuid.uuid4()
        known_mock.vendor = "Google"
        known_mock.description = "GA cookie"
        known_mock.is_regex = False
        known_mock.created_at = datetime.now()
        known_mock.updated_at = datetime.now()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Category validation
                return cat_result
            return MagicMock()

        db.execute = mock_execute
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        db.add = MagicMock()

        with patch(
            "src.routers.cookies.KnownCookie",
            return_value=known_mock,
        ):
            async with await _client(app, db) as client:
                resp = await client.post(
                    "/api/v1/cookies/known",
                    json={
                        "name_pattern": "_ga",
                        "domain_pattern": "*",
                        "category_id": str(uuid.uuid4()),
                        "vendor": "Google",
                    },
                )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_get_known_cookie_not_found(self, app):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        async with await _client(app, db) as client:
            resp = await client.get(f"/api/v1/cookies/known/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestClassificationRoutes:
    """Test classification endpoint responses."""

    @pytest.mark.asyncio
    async def test_classify_preview(self, app):
        db = _mock_db()
        mock_result = ClassificationResult(
            cookie_name="_ga",
            cookie_domain=".example.com",
            category_id=uuid.uuid4(),
            category_slug="analytics",
            vendor="Google",
            match_source=MatchSource.KNOWN_EXACT,
            matched=True,
        )
        with patch(
            "src.routers.cookies.classify_single_cookie",
            return_value=mock_result,
        ):
            async with await _client(app, db) as client:
                resp = await client.post(
                    f"/api/v1/cookies/sites/{uuid.uuid4()}/classify/preview",
                    json={
                        "cookie_name": "_ga",
                        "cookie_domain": ".example.com",
                    },
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is True
        assert data["match_source"] == "known_exact"


# ── Integration tests ────────────────────────────────────────────────


try:
    from tests.conftest import create_test_site, requires_db
except ImportError:
    from conftest import create_test_site, requires_db


@requires_db
class TestClassificationIntegration:
    """Integration tests against a live database."""

    async def _get_category_id(self, client: AsyncClient, headers: dict, slug: str) -> str:
        """Get a category ID by slug."""
        resp = await client.get("/api/v1/cookies/categories", headers=headers)
        assert resp.status_code == 200
        for cat in resp.json():
            if cat["slug"] == slug:
                return cat["id"]
        pytest.fail(f"Category '{slug}' not found")

    async def _create_known_cookie(
        self,
        client: AsyncClient,
        headers: dict,
        name_pattern: str,
        domain_pattern: str,
        category_slug: str,
        *,
        vendor: str | None = None,
        is_regex: bool = False,
    ) -> str:
        """Create a known cookie and return its ID."""
        cat_id = await self._get_category_id(client, headers, category_slug)
        resp = await client.post(
            "/api/v1/cookies/known",
            headers=headers,
            json={
                "name_pattern": name_pattern,
                "domain_pattern": domain_pattern,
                "category_id": cat_id,
                "vendor": vendor,
                "is_regex": is_regex,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def _create_cookie(
        self,
        client: AsyncClient,
        headers: dict,
        site_id: str,
        name: str,
        domain: str,
    ) -> str:
        """Create a pending cookie on a site and return its ID."""
        resp = await client.post(
            f"/api/v1/cookies/sites/{site_id}",
            headers=headers,
            json={"name": name, "domain": domain},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def test_known_cookies_crud(self, db_client, superuser_headers):
        """Test full CRUD lifecycle for known cookies."""
        cat_id = await self._get_category_id(db_client, superuser_headers, "analytics")
        # Create
        resp = await db_client.post(
            "/api/v1/cookies/known",
            headers=superuser_headers,
            json={
                "name_pattern": f"_test_{uuid.uuid4().hex[:6]}",
                "domain_pattern": "*",
                "category_id": cat_id,
                "vendor": "TestVendor",
                "description": "Test cookie",
            },
        )
        assert resp.status_code == 201
        known_id = resp.json()["id"]

        # Read
        resp = await db_client.get(
            f"/api/v1/cookies/known/{known_id}",
            headers=superuser_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["vendor"] == "TestVendor"

        # Update
        resp = await db_client.patch(
            f"/api/v1/cookies/known/{known_id}",
            headers=superuser_headers,
            json={"vendor": "UpdatedVendor"},
        )
        assert resp.status_code == 200
        assert resp.json()["vendor"] == "UpdatedVendor"

        # List (with search)
        resp = await db_client.get(
            "/api/v1/cookies/known",
            headers=superuser_headers,
            params={"vendor": "UpdatedVendor"},
        )
        assert resp.status_code == 200
        assert any(k["id"] == known_id for k in resp.json())

        # Delete
        resp = await db_client.delete(
            f"/api/v1/cookies/known/{known_id}",
            headers=superuser_headers,
        )
        assert resp.status_code == 204

        # Verify deleted
        resp = await db_client.get(
            f"/api/v1/cookies/known/{known_id}",
            headers=superuser_headers,
        )
        assert resp.status_code == 404

    async def test_classify_exact_match(self, db_client, auth_headers, superuser_headers):
        """Test classification with exact known cookie match."""
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="classify-exact")
        # Create a known cookie pattern
        pattern_name = f"_test_exact_{uuid.uuid4().hex[:6]}"
        await self._create_known_cookie(
            db_client,
            superuser_headers,
            pattern_name,
            "*",
            "analytics",
            vendor="TestVendor",
        )
        # Create a pending cookie on the site
        await self._create_cookie(
            db_client,
            auth_headers,
            site_id,
            pattern_name,
            ".example.com",
        )
        # Classify
        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/classify",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["matched"] >= 1
        matched = [r for r in data["results"] if r["matched"]]
        assert any(r["cookie_name"] == pattern_name for r in matched)

    async def test_classify_regex_match(self, db_client, auth_headers, superuser_headers):
        """Test classification with regex known cookie match."""
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="classify-regex")
        prefix = f"_rx_{uuid.uuid4().hex[:4]}"
        # Create regex pattern
        await self._create_known_cookie(
            db_client,
            superuser_headers,
            f"{prefix}.*",
            ".*",
            "analytics",
            vendor="RegexVendor",
            is_regex=True,
        )
        # Create a cookie that should match the regex
        await self._create_cookie(
            db_client,
            auth_headers,
            site_id,
            f"{prefix}_session_123",
            ".example.com",
        )
        # Classify
        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/classify",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] >= 1
        matched = [r for r in data["results"] if r["matched"]]
        assert any(r["match_source"] == "known_regex" for r in matched)

    async def test_classify_unmatched(self, db_client, auth_headers):
        """Cookies without known patterns should remain unmatched."""
        site_id = await create_test_site(
            db_client, auth_headers, domain_prefix="classify-unmatched"
        )
        unique_name = f"_unknown_{uuid.uuid4().hex[:8]}"
        await self._create_cookie(
            db_client,
            auth_headers,
            site_id,
            unique_name,
            ".obscure-domain.com",
        )
        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/classify",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["unmatched"] >= 1

    async def test_classify_preview(self, db_client, auth_headers):
        """Test preview classification without saving."""
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="classify-preview")
        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/classify/preview",
            headers=auth_headers,
            json={
                "cookie_name": "_unknown_cookie",
                "cookie_domain": ".test.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is False
        assert data["match_source"] == "unmatched"

    async def test_classify_allow_list_priority(self, db_client, auth_headers, superuser_headers):
        """Allow-list entries should take priority over known cookies."""
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="classify-allow")
        cookie_name = f"_priority_{uuid.uuid4().hex[:6]}"

        # Add to known cookies as marketing
        await self._create_known_cookie(
            db_client,
            superuser_headers,
            cookie_name,
            "*",
            "marketing",
        )

        # Add to allow-list as necessary (should take priority)
        necessary_id = await self._get_category_id(db_client, auth_headers, "necessary")
        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/allow-list",
            headers=auth_headers,
            json={
                "name_pattern": cookie_name,
                "domain_pattern": "*",
                "category_id": necessary_id,
            },
        )
        assert resp.status_code == 201

        # Create cookie and classify
        await self._create_cookie(
            db_client,
            auth_headers,
            site_id,
            cookie_name,
            ".example.com",
        )
        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/classify",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        matched = [r for r in data["results"] if r["cookie_name"] == cookie_name]
        assert len(matched) == 1
        assert matched[0]["match_source"] == "allow_list"
        assert matched[0]["category_id"] == necessary_id

    async def test_known_cookies_not_found(self, db_client, auth_headers):
        resp = await db_client.get(
            f"/api/v1/cookies/known/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_known_cookies_invalid_category(self, db_client, superuser_headers):
        resp = await db_client.post(
            "/api/v1/cookies/known",
            headers=superuser_headers,
            json={
                "name_pattern": "_test",
                "domain_pattern": "*",
                "category_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 400

    async def test_known_cookies_auth_required(self, db_client):
        """Known cookie endpoints require authentication."""
        resp = await db_client.get("/api/v1/cookies/known")
        assert resp.status_code == 401

    async def test_classify_empty_site(self, db_client, auth_headers):
        """Classifying a site with no cookies should return empty results."""
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="classify-empty")
        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/classify",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["matched"] == 0

    async def test_list_known_cookies_search(self, db_client, auth_headers, superuser_headers):
        """Test searching known cookies by name pattern."""
        unique = uuid.uuid4().hex[:6]
        await self._create_known_cookie(
            db_client,
            superuser_headers,
            f"_search_{unique}",
            "*",
            "analytics",
        )
        resp = await db_client.get(
            "/api/v1/cookies/known",
            headers=auth_headers,
            params={"search": f"_search_{unique}"},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        assert all(f"_search_{unique}" in r["name_pattern"] for r in results)

    async def test_known_cookie_writes_require_platform_admin(
        self, db_client, auth_headers, superuser_headers
    ):
        """Organisation owners can read the shared list but not change it."""
        cat_id = await self._get_category_id(db_client, auth_headers, "analytics")
        payload = {
            "name_pattern": f"_owner_{uuid.uuid4().hex[:6]}",
            "domain_pattern": "*",
            "category_id": cat_id,
        }
        resp = await db_client.post("/api/v1/cookies/known", headers=auth_headers, json=payload)
        assert resp.status_code == 403

        known_id = await self._create_known_cookie(
            db_client, superuser_headers, payload["name_pattern"], "*", "analytics"
        )
        url = f"/api/v1/cookies/known/{known_id}"

        assert (await db_client.get(url, headers=auth_headers)).status_code == 200
        resp = await db_client.patch(url, headers=auth_headers, json={"vendor": "X"})
        assert resp.status_code == 403
        assert (await db_client.delete(url, headers=auth_headers)).status_code == 403
        assert (await db_client.delete(url, headers=superuser_headers)).status_code == 204

    @pytest.mark.parametrize("pattern", [r"(a+)+", r"(a*)*", r"(a|aa)+", r"[abc"])
    async def test_create_rejects_unsupported_regex(self, db_client, superuser_headers, pattern):
        cat_id = await self._get_category_id(db_client, superuser_headers, "analytics")
        resp = await db_client.post(
            "/api/v1/cookies/known",
            headers=superuser_headers,
            json={
                "name_pattern": pattern,
                "domain_pattern": ".*",
                "category_id": cat_id,
                "is_regex": True,
            },
        )
        assert resp.status_code == 422

    async def test_update_to_regex_validates_stored_patterns(self, db_client, superuser_headers):
        known_id = await self._create_known_cookie(
            db_client,
            superuser_headers,
            f"*_glob_{uuid.uuid4().hex[:6]}",
            "*",
            "analytics",
        )
        resp = await db_client.patch(
            f"/api/v1/cookies/known/{known_id}",
            headers=superuser_headers,
            json={"is_regex": True},
        )
        assert resp.status_code == 422

    async def test_classify_skips_stored_invalid_pattern(
        self, db_client, auth_headers, superuser_headers, _test_engine
    ):
        """A bad regex already in the database must not break classification."""
        from sqlalchemy.ext.asyncio import AsyncSession

        from src.models.cookie import KnownCookie

        site_id = await create_test_site(db_client, auth_headers, domain_prefix="classify-bad")
        prefix = f"_ok_{uuid.uuid4().hex[:4]}"
        cat_id = await self._get_category_id(db_client, auth_headers, "analytics")
        async with AsyncSession(_test_engine) as session:
            session.add_all(
                [
                    KnownCookie(
                        name_pattern=r"(a+)+$",
                        domain_pattern=f"bad-{prefix}",
                        category_id=uuid.UUID(cat_id),
                        is_regex=True,
                    ),
                    KnownCookie(
                        name_pattern="[unterminated",
                        domain_pattern=f"bad-{prefix}",
                        category_id=uuid.UUID(cat_id),
                        is_regex=True,
                    ),
                ]
            )
            await session.commit()

        await self._create_known_cookie(
            db_client, superuser_headers, f"{prefix}.*", ".*", "analytics", is_regex=True
        )
        await self._create_cookie(
            db_client, auth_headers, site_id, f"{prefix}_session", ".example.com"
        )

        resp = await db_client.post(
            f"/api/v1/cookies/sites/{site_id}/classify",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        matched = [r for r in resp.json()["results"] if r["matched"]]
        assert [r["match_source"] for r in matched] == ["known_regex"]
