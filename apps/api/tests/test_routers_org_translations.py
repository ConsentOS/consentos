"""Unit tests for org-translations router — mocked database."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.services.auth import create_access_token

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _auth_headers(role="owner"):
    token = create_access_token(
        user_id=USER_ID, organisation_id=ORG_ID, role=role, email="admin@test.com"
    )
    return {"Authorization": f"Bearer {token}"}


def _mock_org_translation(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", uuid.uuid4())
    t.organisation_id = overrides.get("organisation_id", ORG_ID)
    t.locale = overrides.get("locale", "fr")
    t.strings = overrides.get(
        "strings",
        {"title": "Nous utilisons des cookies", "acceptAll": "Tout accepter"},
    )
    t.created_at = datetime.now(UTC)
    t.updated_at = datetime.now(UTC)
    return t


@pytest.fixture
def mock_app():
    return create_app()


async def _client(app, mock_session):
    from src.db import get_db

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _mock_db_sequence(*results):
    session = AsyncMock()
    mock_results = []
    for r in results:
        result = MagicMock()
        if isinstance(r, list):
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = r
            result.scalars.return_value = scalars_obj
            result.scalar_one_or_none.return_value = r[0] if r else None
        else:
            result.scalar_one_or_none.return_value = r
        mock_results.append(result)
    session.execute = AsyncMock(side_effect=mock_results)

    _added = []

    def _fake_add(obj):
        _added.append(obj)

    session.add = MagicMock(side_effect=_fake_add)

    async def _fake_flush():
        for obj in _added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)

    session.flush = AsyncMock(side_effect=_fake_flush)
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


class TestListOrgTranslations:
    @pytest.mark.asyncio
    async def test_list_org_translations(self, mock_app):
        fr = _mock_org_translation(locale="fr")
        de = _mock_org_translation(locale="de")
        db = _mock_db_sequence([fr, de])
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/org-translations/", headers=_auth_headers())
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_list_org_translations_empty(self, mock_app):
        db = _mock_db_sequence([])
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/org-translations/", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetOrgTranslation:
    @pytest.mark.asyncio
    async def test_get_org_translation(self, mock_app):
        fr = _mock_org_translation(locale="fr")
        db = _mock_db_sequence(fr)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/org-translations/fr", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["locale"] == "fr"

    @pytest.mark.asyncio
    async def test_get_org_translation_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/org-translations/xx", headers=_auth_headers())
        assert resp.status_code == 404


class TestCreateOrgTranslation:
    @pytest.mark.asyncio
    async def test_create_org_translation(self, mock_app):
        db = _mock_db_sequence(None)  # duplicate check
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/org-translations/",
                json={"locale": "de", "strings": {"title": "Wir verwenden Cookies"}},
                headers=_auth_headers(),
            )
        assert resp.status_code == 201
        assert resp.json()["locale"] == "de"

    @pytest.mark.asyncio
    async def test_create_org_translation_conflict(self, mock_app):
        existing = _mock_org_translation(locale="fr")
        db = _mock_db_sequence(existing)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/org-translations/",
                json={"locale": "fr", "strings": {"title": "test"}},
                headers=_auth_headers(),
            )
        assert resp.status_code == 409


class TestUpdateOrgTranslation:
    @pytest.mark.asyncio
    async def test_update_org_translation(self, mock_app):
        fr = _mock_org_translation(locale="fr")
        db = _mock_db_sequence(fr)
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                "/api/v1/org-translations/fr",
                json={"strings": {"title": "Updated title"}},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        assert fr.strings == {"title": "Updated title"}

    @pytest.mark.asyncio
    async def test_update_org_translation_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                "/api/v1/org-translations/xx",
                json={"strings": {"title": "test"}},
                headers=_auth_headers(),
            )
        assert resp.status_code == 404


class TestDeleteOrgTranslation:
    @pytest.mark.asyncio
    async def test_delete_org_translation(self, mock_app):
        fr = _mock_org_translation(locale="fr")
        db = _mock_db_sequence(fr)
        async with await _client(mock_app, db) as client:
            resp = await client.delete("/api/v1/org-translations/fr", headers=_auth_headers())
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_requires_admin(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.delete(
                "/api/v1/org-translations/fr", headers=_auth_headers(role="editor")
            )
        assert resp.status_code == 403
