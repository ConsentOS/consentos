"""Extension registry for the open-core architecture.

Provides registration hooks that allow enterprise/commercial code to inject
routers, model modules, startup tasks, and OpenAPI tags into the core
application — without the core needing any direct knowledge of the
extensions.

In community edition (CE) mode, ``discover_extensions()`` is a no-op
because the ``ee`` package is not present.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from fastapi import APIRouter, FastAPI

    from src.services.auth_provider import AuthProvider

logger = logging.getLogger(__name__)


@dataclass
class OpenAPITag:
    """Metadata for a FastAPI OpenAPI tag."""

    name: str
    description: str


@dataclass
class RouterEntry:
    """A router registered by an extension."""

    router: APIRouter
    prefix: str = "/api/v1"
    tags: list[OpenAPITag] = field(default_factory=list)


@dataclass
class ExtensionRegistry:
    """Central registry for extension-contributed components.

    Extensions call the module-level helper functions (``register_router``,
    ``register_model_module``, etc.) which delegate to the singleton
    instance stored in ``_registry``.
    """

    routers: list[RouterEntry] = field(default_factory=list)
    model_modules: list[str] = field(default_factory=list)
    startup_hooks: list[Callable[[FastAPI], Coroutine[Any, Any, None]]] = field(
        default_factory=list,
    )
    config_enrichers: list[Callable] = field(default_factory=list)
    consent_record_hooks: list[Callable] = field(default_factory=list)
    auth_provider: AuthProvider | None = None

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def add_router(
        self,
        router: APIRouter,
        *,
        prefix: str = "/api/v1",
        tags: list[OpenAPITag] | None = None,
    ) -> None:
        self.routers.append(RouterEntry(router=router, prefix=prefix, tags=tags or []))

    def add_model_module(self, module_path: str) -> None:
        self.model_modules.append(module_path)

    def add_startup_hook(
        self,
        hook: Callable[[FastAPI], Coroutine[Any, Any, None]],
    ) -> None:
        self.startup_hooks.append(hook)

    def add_config_enricher(self, enricher: Callable) -> None:
        self.config_enrichers.append(enricher)

    def add_consent_record_hook(self, hook: Callable) -> None:
        self.consent_record_hooks.append(hook)

    def set_auth_provider(self, provider: AuthProvider) -> None:
        if self.auth_provider is not None:
            raise RuntimeError(
                "An auth provider is already registered; only one is allowed.",
            )
        self.auth_provider = provider

    # ------------------------------------------------------------------
    # Application wiring
    # ------------------------------------------------------------------

    def apply(self, app: FastAPI) -> None:
        """Mount all registered routers and tags onto *app*."""
        for entry in self.routers:
            # Inject OpenAPI tags
            for tag in entry.tags:
                existing = app.openapi_tags or []
                if not any(t["name"] == tag.name for t in existing):
                    existing.append(
                        {"name": tag.name, "description": tag.description},
                    )
                    app.openapi_tags = existing

            app.include_router(entry.router, prefix=entry.prefix)

        if self.routers:
            logger.info(
                "Registered %d extension router(s)",
                len(self.routers),
            )

        # Import model modules so SQLAlchemy picks them up
        for mod in self.model_modules:
            importlib.import_module(mod)

        if self.model_modules:
            logger.info(
                "Registered %d extension model module(s)",
                len(self.model_modules),
            )


# Singleton ------------------------------------------------------------------

_registry = ExtensionRegistry()


def get_registry() -> ExtensionRegistry:
    """Return the global extension registry."""
    return _registry


# Convenience module-level API -----------------------------------------------


def register_router(
    router: APIRouter,
    *,
    prefix: str = "/api/v1",
    tags: list[OpenAPITag] | None = None,
) -> None:
    """Register an API router to be mounted at startup."""
    _registry.add_router(router, prefix=prefix, tags=tags)


def register_model_module(module_path: str) -> None:
    """Register a dotted module path whose SQLAlchemy models should be imported."""
    _registry.add_model_module(module_path)


def register_startup_hook(
    hook: Callable[[FastAPI], Coroutine[Any, Any, None]],
) -> None:
    """Register an async callable to run during application startup."""
    _registry.add_startup_hook(hook)


def register_config_enricher(enricher: Callable) -> None:
    """Register a callable that enriches published config.

    The callable signature is ``async (site_id: UUID, db: AsyncSession, config: dict) -> None``.
    It should mutate *config* in-place to add extension-specific data
    (e.g. A/B test variants).
    """
    _registry.add_config_enricher(enricher)


def register_consent_record_hook(hook: Callable) -> None:
    """Register a callable invoked after a consent record is persisted.

    The callable signature is ``async (db: AsyncSession, consent_record) -> None``.
    It is called from ``POST /api/v1/consent`` after the record has been
    flushed to the database. Typical use: generating a consent receipt
    (EE), writing audit logs, firing webhooks.
    """
    _registry.add_consent_record_hook(hook)


def register_auth_provider(provider: AuthProvider) -> None:
    """Register the authentication provider for this deployment.

    Only one provider may be registered. Enterprise packages call this
    at import time to replace the default ``PgAuthProvider``. If no
    provider is registered, the default is used.
    """
    _registry.set_auth_provider(provider)


# Discovery ------------------------------------------------------------------


def discover_extensions() -> None:
    """Import the EE registration module if installed.

    Enterprise edition is distributed as a separate ``consent-enterprise``
    package. When installed in the same environment, importing
    ``ee.api.src.register`` triggers its side-effect registrations. In
    community edition the import simply fails and we carry on.
    """
    try:
        import ee.api.src.register  # noqa: F401

        logger.info("Enterprise extensions loaded")
    except ImportError:
        logger.debug("No enterprise extensions found (CE mode)")
