"""Shared Pydantic validators used by the config update schemas."""

from typing import Any


def coerce_blank_to_none(value: Any) -> Any:
    """Map an empty or whitespace-only string to ``None``.

    The admin UI's "Reset to inherited" flow clears a free-text field,
    which submits as ``""``. Persisting that empty string would block the
    cascade resolver from falling through to the parent layer, since the
    resolver only inherits when the value is ``None``. Coerce blanks
    here so the user-visible "clear" action behaves as inheritance.
    """
    if isinstance(value, str) and value.strip() == "":
        return None
    return value
