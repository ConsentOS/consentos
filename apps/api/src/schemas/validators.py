"""Shared Pydantic validators used by the API schemas."""

import re
import re._constants as _re_constants
import re._parser as _re_parser
from collections.abc import Iterator
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


MAX_REGEX_PATTERN_LENGTH = 255

_REPEAT_OPCODES = frozenset(
    {_re_constants.MAX_REPEAT, _re_constants.MIN_REPEAT, _re_constants.POSSESSIVE_REPEAT}
)


def _child_subpatterns(value: Any) -> Iterator[_re_parser.SubPattern]:
    if isinstance(value, _re_parser.SubPattern):
        yield value
    elif isinstance(value, tuple | list):
        for item in value:
            yield from _child_subpatterns(item)


def _is_repeat(op: Any, av: Any) -> bool:
    return op in _REPEAT_OPCODES and av[1] > 1


def _can_repeat(subpattern: _re_parser.SubPattern) -> bool:
    for op, av in subpattern:
        if _is_repeat(op, av) or op is _re_constants.BRANCH:
            return True
        if any(_can_repeat(child) for child in _child_subpatterns(av)):
            return True
    return False


def _has_nested_quantifier(subpattern: _re_parser.SubPattern) -> bool:
    """Detect a repeat whose body can itself match in more than one way.

    Covers shapes such as ``(a+)+``, ``(a*)*`` and ``(a|aa)+``, which can
    take exponential time to fail a match.
    """
    for op, av in subpattern:
        if _is_repeat(op, av) and _can_repeat(av[2]):
            return True
        if any(_has_nested_quantifier(child) for child in _child_subpatterns(av)):
            return True
    return False


def validate_regex_pattern(pattern: str) -> str:
    """Check a known-cookie regex is valid, short and free of nested quantifiers.

    Raises ``ValueError`` describing the first problem found.
    """
    if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
        raise ValueError(
            f"Regular expression must be at most {MAX_REGEX_PATTERN_LENGTH} characters"
        )
    try:
        re.compile(pattern)
        parsed = _re_parser.parse(pattern)
    except (re.error, OverflowError) as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from exc
    if _has_nested_quantifier(parsed):
        raise ValueError(
            "Regular expression must not repeat a group that is itself repeated "
            "or contains alternatives, e.g. (a+)+ or (a|aa)+"
        )
    return pattern
