"""Unit tests for consent router — mocked database."""

import logging
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.config.settings import Settings
from src.main import create_app
from src.services.pseudonymisation import pseudonymise


def _mock_consent_record(**overrides):
    """Build a mock ConsentRecord ORM object."""
    record = MagicMock()
    record.id = overrides.get("id", uuid.uuid4())
    record.site_id = overrides.get("site_id", uuid.uuid4())
    record.visitor_id = overrides.get("visitor_id", "visitor-123")
    record.ip_hash = "abc123"
    record.user_agent_hash = "def456"
    record.action = overrides.get("action", "accept_all")
    record.categories_accepted = overrides.get("categories_accepted", ["necessary"])
    record.categories_rejected = overrides.get("categories_rejected", [])
    record.tc_string = overrides.get("tc_string")
    record.gcm_state = overrides.get("gcm_state")
    record.gpp_string = overrides.get("gpp_string")
    record.gpc_detected = overrides.get("gpc_detected")
    record.gpc_honoured = overrides.get("gpc_honoured")
    record.page_url = overrides.get("page_url")
    record.country_code = overrides.get("country_code")
    record.region_code = overrides.get("region_code")
    record.consented_at = overrides.get("consented_at", datetime.now(UTC))
    return record


def _mock_site(domain="example.com", additional_domains=None):
    """Build a mock Site ORM object."""
    site = MagicMock()
    site.id = uuid.uuid4()
    site.domain = domain
    site.additional_domains = additional_domains
    return site


def _consent_body(**overrides):
    body = {
        "site_id": str(uuid.uuid4()),
        "visitor_id": "visitor-123",
        "action": "accept_all",
        "categories_accepted": ["necessary"],
        "categories_rejected": [],
    }
    body.update(overrides)
    return body


def _mock_db(scalar_one_or_none=None):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    session.execute.return_value = result

    _added_objects = []

    def _fake_add(obj):
        _added_objects.append(obj)

    session.add = MagicMock(side_effect=_fake_add)

    async def _fake_flush():
        """Simulate DB flush — populate server-side defaults."""
        for obj in _added_objects:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if hasattr(obj, "consented_at") and getattr(obj, "consented_at", None) is None:
                obj.consented_at = datetime.now(UTC)
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)

    session.flush = AsyncMock(side_effect=_fake_flush)
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_app():
    return create_app()


async def _client(app, mock_session):
    from src.db import get_db
    from src.services.dependencies import get_current_user, require_role

    user = MagicMock()
    user.organisation_id = uuid.uuid4()
    user.role = "owner"

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_current_user] = lambda: user

    def _override_require_role(*_roles):
        return lambda: user

    app.dependency_overrides[require_role] = _override_require_role

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestRecordConsent:
    @pytest.mark.asyncio
    async def test_record_consent_success(self, mock_app):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/consent/",
                json={
                    "site_id": str(uuid.uuid4()),
                    "visitor_id": "visitor-123",
                    "action": "accept_all",
                    "categories_accepted": ["necessary", "analytics"],
                    "categories_rejected": [],
                },
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("trusted", "expected_ip"),
        [("", "127.0.0.1"), ("127.0.0.1", "1.2.3.4")],
    )
    async def test_record_consent_ip_hash_uses_resolved_client_ip(
        self, mock_app, trusted, expected_ip
    ):
        db = _mock_db(scalar_one_or_none=_mock_site())
        settings = Settings(trusted_proxies=trusted)
        with patch("src.services.client_ip.get_settings", return_value=settings):
            async with await _client(mock_app, db) as client:
                resp = await client.post(
                    "/api/v1/consent/",
                    headers={"x-forwarded-for": "1.2.3.4"},
                    json={
                        "site_id": str(uuid.uuid4()),
                        "visitor_id": "visitor-123",
                        "action": "accept_all",
                        "categories_accepted": ["necessary"],
                        "categories_rejected": [],
                    },
                )
        assert resp.status_code == 201
        record = db.add.call_args.args[0]
        assert record.ip_hash == pseudonymise(expected_ip)

    @pytest.mark.asyncio
    async def test_record_consent_reject_all(self, mock_app):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/consent/",
                json={
                    "site_id": str(uuid.uuid4()),
                    "visitor_id": "visitor-456",
                    "action": "reject_all",
                    "categories_accepted": ["necessary"],
                    "categories_rejected": ["analytics", "marketing"],
                },
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_record_consent_custom(self, mock_app):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/consent/",
                json={
                    "site_id": str(uuid.uuid4()),
                    "visitor_id": "visitor-789",
                    "action": "custom",
                    "categories_accepted": ["necessary", "analytics"],
                    "categories_rejected": ["marketing"],
                },
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_record_consent_invalid_action(self, mock_app):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/consent/",
                json={
                    "site_id": str(uuid.uuid4()),
                    "visitor_id": "visitor-000",
                    "action": "invalid_action",
                    "categories_accepted": ["necessary"],
                    "categories_rejected": [],
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_record_consent_empty_visitor_id(self, mock_app):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/consent/",
                json={
                    "site_id": str(uuid.uuid4()),
                    "visitor_id": "",
                    "action": "accept_all",
                    "categories_accepted": ["necessary"],
                    "categories_rejected": [],
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_record_consent_with_optional_fields(self, mock_app):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/consent/",
                json={
                    "site_id": str(uuid.uuid4()),
                    "visitor_id": "visitor-opt",
                    "action": "accept_all",
                    "categories_accepted": ["necessary"],
                    "categories_rejected": [],
                    "tc_string": "CPXxRAAAA",
                    "gcm_state": {"analytics_storage": "granted"},
                    "page_url": "https://example.com",
                    "country_code": "GB",
                    "region_code": "ENG",
                },
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_record_consent_unknown_site_returns_404(self, mock_app):
        db = _mock_db(scalar_one_or_none=None)
        async with await _client(mock_app, db) as client:
            resp = await client.post("/api/v1/consent/", json=_consent_body())
        assert resp.status_code == 404
        db.add.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "headers",
        [
            {"origin": "https://other.test"},
            {"origin": "https://example.com.other.test"},
            {"origin": "null", "referer": "https://other.test/page"},
            {"referer": "https://other.test/page"},
        ],
    )
    async def test_record_consent_mismatched_origin_returns_403(self, mock_app, headers):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post("/api/v1/consent/", headers=headers, json=_consent_body())
        assert resp.status_code == 403
        db.add.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "headers",
        [
            {"origin": "https://example.com"},
            {"origin": "https://shop.example.com:8443"},
            {"origin": "https://www.example.com"},
            {"origin": "https://example.org"},
            {"referer": "https://blog.example.org/post?id=1"},
            {"origin": "https://example.com", "referer": "https://other.test/"},
            {"origin": "null"},
            {"origin": "null", "referer": "https://example.com/page"},
        ],
    )
    async def test_record_consent_matching_origin_accepted(self, mock_app, headers):
        db = _mock_db(scalar_one_or_none=_mock_site(additional_domains=["example.org"]))
        async with await _client(mock_app, db) as client:
            resp = await client.post("/api/v1/consent/", headers=headers, json=_consent_body())
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_record_consent_origin_preferred_over_referer(self, mock_app):
        db = _mock_db(scalar_one_or_none=_mock_site())
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/consent/",
                headers={"origin": "https://other.test", "referer": "https://example.com/"},
                json=_consent_body(),
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_record_consent_rejection_logged(self, mock_app, caplog):
        site = _mock_site()
        db = _mock_db(scalar_one_or_none=site)
        with caplog.at_level(logging.WARNING, logger="src.services.site_domains"):
            async with await _client(mock_app, db) as client:
                resp = await client.post(
                    "/api/v1/consent/",
                    headers={"origin": "https://other.test"},
                    json=_consent_body(visitor_id="visitor-secret"),
                )
        assert resp.status_code == 403
        [record] = [r for r in caplog.records if r.name == "src.services.site_domains"]
        assert record.levelno == logging.WARNING
        message = record.getMessage()
        assert str(site.id) in message
        assert "other.test" in message
        assert "visitor-secret" not in message
        assert "127.0.0.1" not in message


class TestGetConsent:
    @pytest.mark.asyncio
    async def test_get_consent_found(self, mock_app):
        record = _mock_consent_record()
        db = _mock_db(scalar_one_or_none=record)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/consent/{record.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_consent_not_found(self, mock_app):
        db = _mock_db(scalar_one_or_none=None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/consent/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestVerifyConsent:
    @pytest.mark.asyncio
    async def test_verify_consent_valid(self, mock_app):
        record = _mock_consent_record()
        db = _mock_db(scalar_one_or_none=record)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/consent/verify/{record.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_verify_consent_not_found(self, mock_app):
        db = _mock_db(scalar_one_or_none=None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/consent/verify/{uuid.uuid4()}")
        assert resp.status_code == 404
