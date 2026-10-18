"""The edition label reported by ``/health`` and telemetry."""

from __future__ import annotations

from src.extensions.registry import get_registry


def edition_name() -> str:
    """Return the label set by an installed extension, or the default."""
    return get_registry().edition
