"""Tests for the extension registry and edition detection."""

import pytest
from fastapi import APIRouter, FastAPI

from src.config.edition import edition_name, is_ee
from src.extensions.registry import (
    ExtensionRegistry,
    OpenAPITag,
    discover_extensions,
    get_registry,
)

# -- Edition detection -------------------------------------------------------


class TestEditionDetection:
    """The ``is_ee()`` / ``edition_name()`` helpers should return a
    consistent pair regardless of which edition is installed. Core tests
    don't assume a specific edition — that's checked in each repo's
    own integration tests."""

    def test_edition_name_matches_is_ee(self):
        assert edition_name() == ("ee" if is_ee() else "ce")

    def test_edition_name_is_valid(self):
        assert edition_name() in ("ce", "ee")


# -- Extension registry (unit) ----------------------------------------------


class TestExtensionRegistry:
    def _make_registry(self) -> ExtensionRegistry:
        return ExtensionRegistry()

    def test_empty_registry(self):
        reg = self._make_registry()
        assert reg.routers == []
        assert reg.model_modules == []
        assert reg.startup_hooks == []

    def test_add_router(self):
        reg = self._make_registry()
        router = APIRouter()
        reg.add_router(router, prefix="/api/v1")
        assert len(reg.routers) == 1
        assert reg.routers[0].router is router
        assert reg.routers[0].prefix == "/api/v1"

    def test_add_router_with_tags(self):
        reg = self._make_registry()
        router = APIRouter()
        tag = OpenAPITag(name="billing", description="Billing endpoints")
        reg.add_router(router, tags=[tag])
        assert reg.routers[0].tags == [tag]

    def test_add_model_module(self):
        reg = self._make_registry()
        reg.add_model_module("ee.api.src.models.billing")
        assert reg.model_modules == ["ee.api.src.models.billing"]

    def test_add_startup_hook(self):
        reg = self._make_registry()

        async def hook(app: FastAPI) -> None:
            pass

        reg.add_startup_hook(hook)
        assert len(reg.startup_hooks) == 1

    def test_apply_mounts_routers(self):
        reg = self._make_registry()
        router = APIRouter()

        @router.get("/test")
        async def _test() -> dict[str, str]:
            return {"ok": True}

        reg.add_router(router, prefix="/ext")

        app = FastAPI()
        reg.apply(app)

        # The router should be included in the app routes
        paths = list(app.openapi()["paths"])
        assert "/ext/test" in paths

    def test_apply_adds_openapi_tags(self):
        reg = self._make_registry()
        router = APIRouter()
        tag = OpenAPITag(name="billing", description="Billing endpoints")
        reg.add_router(router, tags=[tag])

        app = FastAPI()
        app.openapi_tags = []
        reg.apply(app)

        assert any(t["name"] == "billing" for t in app.openapi_tags)

    def test_apply_skips_duplicate_tags(self):
        reg = self._make_registry()
        router = APIRouter()
        tag = OpenAPITag(name="billing", description="Billing endpoints")
        reg.add_router(router, tags=[tag])

        app = FastAPI()
        app.openapi_tags = [{"name": "billing", "description": "Existing"}]
        reg.apply(app)

        billing_tags = [t for t in app.openapi_tags if t["name"] == "billing"]
        assert len(billing_tags) == 1
        assert billing_tags[0]["description"] == "Existing"


# -- discover_extensions -----------------------------------------------------


class TestDiscoverExtensions:
    def test_discover_extensions_does_not_raise(self):
        """discover_extensions should not raise regardless of edition."""
        discover_extensions()


# -- Global registry ---------------------------------------------------------


class TestGlobalRegistry:
    def test_get_registry_returns_singleton(self):
        assert get_registry() is get_registry()


# -- Health endpoint with edition field --------------------------------------


@pytest.mark.asyncio
async def test_health_reports_edition(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["edition"] in ("ce", "ee")
