"""Typed banner configuration accepted by the config update endpoints.

Field names mirror the camelCase JSON keys read by the banner script.
Unknown keys are kept as-is, since older configs carry snake_case
settings (e.g. ``show_reject_all``) that other parts of the API read.
"""

import unicodedata
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from src.schemas.validators import coerce_blank_to_none

_MAX_CSS_VALUE_LENGTH = 200
_FORBIDDEN_CSS_CHARS = frozenset(";{}<>\\")
_QUOTES = frozenset("\"'")


def _check_css_value(value: str, *, allow_quotes: bool) -> str:
    """Accept any CSS value that cannot end its declaration or rule.

    Rejects characters that would close the declaration, block or style
    element, CSS comments and escapes, ``url()`` and control characters.
    Quotes are only accepted when ``allow_quotes`` is set and every
    quoted string is closed.
    """
    value = value.strip()
    if not value or len(value) > _MAX_CSS_VALUE_LENGTH:
        raise ValueError(f"must be between 1 and {_MAX_CSS_VALUE_LENGTH} characters")
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("must not contain control characters")
    forbidden = _FORBIDDEN_CSS_CHARS if allow_quotes else _FORBIDDEN_CSS_CHARS | _QUOTES
    if any(ch in forbidden for ch in value) or "/*" in value or "*/" in value:
        raise ValueError("contains a character that is not allowed in this CSS value")
    if "url(" in value.lower():
        raise ValueError("must not contain url()")
    if allow_quotes and not _quotes_balanced(value):
        raise ValueError("must close every quoted string")
    return value


def _quotes_balanced(value: str) -> bool:
    open_quote = None
    for ch in value:
        if open_quote is None and ch in _QUOTES:
            open_quote = ch
        elif ch == open_quote:
            open_quote = None
    return open_quote is None


def _validate_colour(value: str) -> str:
    return _check_css_value(value, allow_quotes=False)


def _validate_font_family(value: str) -> str:
    return _check_css_value(value, allow_quotes=True)


Colour = Annotated[str, AfterValidator(_validate_colour)]
FontFamily = Annotated[str, AfterValidator(_validate_font_family)]

# Separate int and float branches keep whole numbers stored as integers.
Radius = Annotated[int, Field(ge=0, le=100)] | Annotated[float, Field(ge=0, le=100)]
Width = Annotated[int, Field(ge=0, le=4000)] | Annotated[float, Field(ge=0, le=4000)]
LogoHeight = Annotated[int, Field(ge=0, le=1000)] | Annotated[float, Field(ge=0, le=1000)]


class _BannerSection(BaseModel):
    """Base for banner config sections: keeps unknown keys and only
    serialises the keys that were provided, so stored JSON keeps its shape."""

    model_config = ConfigDict(extra="allow")

    @model_serializer(mode="wrap")
    def _dump_provided(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        provided = self.model_fields_set | set(self.model_extra or {})
        return {key: value for key, value in data.items() if key in provided}


class ButtonConfig(_BannerSection):
    backgroundColour: Colour | None = None
    textColour: Colour | None = None
    borderColour: Colour | None = None
    style: Literal["filled", "outline", "text"] | None = None

    _coerce_blank = field_validator(
        "backgroundColour", "textColour", "borderColour", mode="before"
    )(coerce_blank_to_none)


class BannerTextConfig(_BannerSection):
    title: str | None = None
    description: str | None = None
    acceptAll: str | None = None
    rejectAll: str | None = None
    managePreferences: str | None = None
    savePreferences: str | None = None


class BannerConfig(_BannerSection):
    displayMode: Literal["bottom_banner", "top_banner", "overlay", "corner_popup"] | None = None
    cornerPosition: Literal["left", "right"] | None = None
    showOverlayBackdrop: bool | None = None
    primaryColour: Colour | None = None
    backgroundColour: Colour | None = None
    textColour: Colour | None = None
    fontFamily: FontFamily | None = None
    borderRadius: Radius | None = None
    bannerWidth: Width | None = None
    showLogo: bool | None = None
    logoUrl: str | None = None
    logoHeight: LogoHeight | None = None
    showRejectAll: bool | None = None
    showManagePreferences: bool | None = None
    showCloseButton: bool | None = None
    showCookieCount: bool | None = None
    showPreferencesButton: bool | None = None
    preferencesButtonPosition: Literal["left", "right"] | None = None
    acceptButton: ButtonConfig | None = None
    rejectButton: ButtonConfig | None = None
    manageButton: ButtonConfig | None = None
    text: BannerTextConfig | None = None

    _coerce_blank = field_validator(
        "primaryColour",
        "backgroundColour",
        "textColour",
        "fontFamily",
        mode="before",
    )(coerce_blank_to_none)
