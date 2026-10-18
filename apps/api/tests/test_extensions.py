"""Tests for the extension registry, discovery and edition label."""

from unittest.mock import MagicMock

import pytest
from celery.schedules import crontab
from fastapi import APIRouter, FastAPI

from src.config.edition import edition_name
from src.extensions import registry as registry_module
from src.extensions.registry import (
    ENTRY_POINT_GROUP,
    ExtensionRegistry,
    OpenAPITag,
    discover_extensions,
    get_registry,
)

# -- Edition label ------------------------------------------------------------


class TestEditionLabel:
    def test_defaults_to_core_label(self):
        assert ExtensionRegistry().edition == registry_module.DEFAULT_EDITION

    def test_edition_name_reads_the_registry(self, monkeypatch):
        reg = ExtensionRegistry(edition="example")
        monkeypatch.setattr(registry_module, "_registry", reg)
        assert edition_name() == "example"

    def test_register_edition_sets_the_label(self, monkeypatch):
        reg = ExtensionRegistry()
        monkeypatch.setattr(registry_module, "_registry", reg)
        registry_module.register_edition("example")
        assert reg.edition == "example"


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
        tag = OpenAPITag(name="widgets", description="Widget endpoints")
        reg.add_router(router, tags=[tag])
        assert reg.routers[0].tags == [tag]

    def test_add_model_module(self):
        reg = self._make_registry()
        reg.add_model_module("example_ext.models.widgets")
        assert reg.model_modules == ["example_ext.models.widgets"]

    def test_add_startup_hook(self):
        reg = self._make_registry()

        async def hook(app: FastAPI) -> None:
            pass

        reg.add_startup_hook(hook)
        assert len(reg.startup_hooks) == 1

    def test_add_task_module_ignores_duplicates(self):
        reg = self._make_registry()
        reg.add_task_module("example_ext.tasks")
        reg.add_task_module("example_ext.tasks")
        assert reg.task_modules == ["example_ext.tasks"]

    def test_add_periodic_task(self):
        reg = self._make_registry()
        schedule = crontab(hour="3", minute="0")
        reg.add_periodic_task("nightly", "example_ext.tasks.nightly", schedule)
        assert reg.periodic_tasks == {
            "nightly": {"task": "example_ext.tasks.nightly", "schedule": schedule}
        }

    def test_add_periodic_task_rejects_duplicate_names(self):
        reg = self._make_registry()
        reg.add_periodic_task("nightly", "a", crontab())
        with pytest.raises(RuntimeError):
            reg.add_periodic_task("nightly", "b", crontab())

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
        tag = OpenAPITag(name="widgets", description="Widget endpoints")
        reg.add_router(router, tags=[tag])

        app = FastAPI()
        app.openapi_tags = []
        reg.apply(app)

        assert any(t["name"] == "widgets" for t in app.openapi_tags)

    def test_apply_skips_duplicate_tags(self):
        reg = self._make_registry()
        router = APIRouter()
        tag = OpenAPITag(name="widgets", description="Widget endpoints")
        reg.add_router(router, tags=[tag])

        app = FastAPI()
        app.openapi_tags = [{"name": "widgets", "description": "Existing"}]
        reg.apply(app)

        widget_tags = [t for t in app.openapi_tags if t["name"] == "widgets"]
        assert len(widget_tags) == 1
        assert widget_tags[0]["description"] == "Existing"


# -- discover_extensions -----------------------------------------------------


def _entry_point(name: str, register) -> MagicMock:
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = register
    return ep


class TestDiscoverExtensions:
    @pytest.fixture(autouse=True)
    def fresh_discovery(self, monkeypatch):
        monkeypatch.setattr(registry_module, "_discovered", False)

    def test_calls_each_registered_extension(self, monkeypatch):
        first, second = MagicMock(), MagicMock()
        seen_groups = []

        def fake_entry_points(group):
            seen_groups.append(group)
            return [_entry_point("first", first), _entry_point("second", second)]

        monkeypatch.setattr(registry_module, "entry_points", fake_entry_points)
        discover_extensions()

        assert seen_groups == [ENTRY_POINT_GROUP]
        first.assert_called_once_with()
        second.assert_called_once_with()

    def test_runs_only_once_per_process(self, monkeypatch):
        register = MagicMock()
        monkeypatch.setattr(
            registry_module, "entry_points", lambda group: [_entry_point("x", register)]
        )
        discover_extensions()
        discover_extensions()
        register.assert_called_once_with()

    def test_nothing_installed_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(registry_module, "entry_points", lambda group: [])
        discover_extensions()

    def test_a_failing_extension_raises(self, monkeypatch):
        def broken() -> None:
            raise RuntimeError("cannot register")

        monkeypatch.setattr(
            registry_module, "entry_points", lambda group: [_entry_point("broken", broken)]
        )
        with pytest.raises(RuntimeError, match="cannot register"):
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
    assert data["edition"] == edition_name()
