"""Shared Pydantic validators used by the config update schemas."""

import re
from typing import Any
from urllib.parse import urlsplit


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


_URL_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.-]*):", re.IGNORECASE)


def validate_link_url(value: str) -> str:
    """Accept an absolute http(s) URL or a root-relative path.

    These values are rendered as links in the banner, which only links
    http(s) and relative URLs. Protocol-relative values such as
    ``//example.com`` point at another host, so they are rejected.
    """
    value = value.strip()
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ValueError("must not contain whitespace or control characters")
    scheme = _URL_SCHEME_RE.match(value)
    if scheme:
        if scheme.group(1).lower() not in ("http", "https"):
            raise ValueError("must be an http(s) URL or a path starting with /")
        if not urlsplit(value).netloc:
            raise ValueError("must include a host name")
        return value
    if not value.startswith("/") or value.startswith(("//", "/\\")):
        raise ValueError("must be an http(s) URL or a path starting with a single /")
    return value


def validate_optional_link_url(value: str | None) -> str | None:
    return None if value is None else validate_link_url(value)
