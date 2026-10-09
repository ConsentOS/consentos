"""Tests for organisation and user CRUD endpoints and schemas."""

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.organisation import OrganisationCreate, OrganisationResponse, OrganisationUpdate
from src.schemas.user import UserCreate, UserResponse, UserRole, UserUpdate


class TestOrganisationSchemas:
    def test_create_valid(self):
        org = OrganisationCreate(name="Acme Corp", slug="acme-corp")
        assert org.name == "Acme Corp"
        assert org.slug == "acme-corp"

    def test_create_invalid_slug(self):
        with pytest.raises(ValidationError):
            OrganisationCreate(name="Acme", slug="INVALID SLUG!")

    def test_create_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            OrganisationCreate(name="", slug="valid-slug")

    def test_update_partial(self):
        update = OrganisationUpdate(name="New Name")
        data = update.model_dump(exclude_unset=True)
        assert data == {"name": "New Name"}
        assert "contact_email" not in data

    def test_response_from_attributes(self):
        now = "2026-01-01T00:00:00Z"
        resp = OrganisationResponse(
            id=uuid.uuid4(),
            name="Test",
            slug="test",
            contact_email=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.name == "Test"


class TestUserSchemas:
    def test_create_valid(self):
        user = UserCreate(
            email="test@example.com",
            password="securepass123",
            full_name="Test User",
        )
        assert user.role == UserRole.VIEWER

    def test_create_short_password_rejected(self):
        with pytest.raises(ValidationError):
            UserCreate(email="a@b.com", password="short", full_name="Test")

    def test_create_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            UserCreate(email="not-an-email", password="securepass123", full_name="Test")

    def test_create_with_role(self):
        user = UserCreate(
            email="admin@example.com",
            password="securepass123",
            full_name="Admin",
            role=UserRole.ADMIN,
        )
        assert user.role == UserRole.ADMIN

    def test_update_partial(self):
        update = UserUpdate(role=UserRole.EDITOR)
        data = update.model_dump(exclude_unset=True)
        assert data == {"role": "editor"}

    def test_response_from_attributes(self):
        now = "2026-01-01T00:00:00Z"
        resp = UserResponse(
            id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            email="a@b.com",
            full_name="Test",
            role="viewer",
            created_at=now,
            updated_at=now,
        )
        assert resp.role == "viewer"


class TestUserRole:
    def test_role_values(self):
        assert UserRole.OWNER == "owner"
        assert UserRole.ADMIN == "admin"
        assert UserRole.EDITOR == "editor"
        assert UserRole.VIEWER == "viewer"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="a@b.com",
                password="securepass123",
                full_name="Test",
                role="superadmin",
            )


@pytest.mark.asyncio
class TestRoutesRegistered:
    async def test_org_routes(self, client):
        response = await client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/api/v1/organisations/" in paths
        assert "/api/v1/organisations/me" in paths

    async def test_user_routes(self, client):
        response = await client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/api/v1/users/" in paths
        assert "/api/v1/users/{user_id}" in paths

    async def test_org_endpoints_require_auth(self, client):
        response = await client.get("/api/v1/organisations/me")
        assert response.status_code == 401

    async def test_user_endpoints_require_auth(self, client):
        response = await client.get("/api/v1/users/")
        assert response.status_code == 401

    async def test_create_org_rejects_invalid_body(self, client, monkeypatch):
        """Create org endpoint validates the request body schema.

        We need to enable the bootstrap token first so the request
        reaches the body-validation stage (the token guard otherwise
        fires before Pydantic validation and we'd see 403 instead).
        """
        from src.config.settings import get_settings

        monkeypatch.setattr(get_settings(), "admin_bootstrap_token", "test-token")
        response = await client.post(
            "/api/v1/organisations/",
            json={"name": "", "slug": "INVALID SLUG!"},
            headers={"X-Admin-Bootstrap-Token": "test-token"},
        )
        assert response.status_code == 422
