"""Tests for banner config and link URL validation on config schemas."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas.banner_config import BannerConfig
from src.schemas.org_config import OrgConfigUpdate
from src.schemas.site import SiteConfigCreate, SiteConfigUpdate
from src.schemas.site_group_config import SiteGroupConfigUpdate
from src.schemas.validators import validate_link_url, validate_optional_link_url

CONFIG_SCHEMAS = [SiteConfigCreate, SiteConfigUpdate, OrgConfigUpdate, SiteGroupConfigUpdate]

CSS_VALUES_PATH = (
    Path(__file__).resolve().parents[2] / "banner/src/__tests__/fixtures/css-values.json"
)
CSS_VALUES = json.loads(CSS_VALUES_PATH.read_text(encoding="utf-8"))


class TestColours:
    @pytest.mark.parametrize("value", CSS_VALUES["colour"]["valid"])
    def test_valid_colours_accepted(self, value: str) -> None:
        cfg = BannerConfig(primaryColour=value, acceptButton={"borderColour": value})
        assert cfg.primaryColour == value
        assert cfg.acceptButton is not None
        assert cfg.acceptButton.borderColour == value

    @pytest.mark.parametrize("value", CSS_VALUES["colour"]["invalid"])
    @pytest.mark.parametrize("field", ["primaryColour", "backgroundColour", "textColour"])
    def test_invalid_colours_rejected(self, field: str, value: str) -> None:
        with pytest.raises(ValidationError):
            BannerConfig(**{field: value})

    @pytest.mark.parametrize("field", ["backgroundColour", "textColour", "borderColour"])
    def test_invalid_button_colours_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            BannerConfig(rejectButton={field: "blue;}"})

    def test_length_limit(self) -> None:
        assert BannerConfig(textColour="a" * 200).textColour == "a" * 200
        with pytest.raises(ValidationError):
            BannerConfig(textColour="a" * 201)

    def test_colour_is_trimmed(self) -> None:
        assert BannerConfig(textColour="  #000 ").textColour == "#000"

    def test_blank_colour_becomes_none(self) -> None:
        cfg = BannerConfig(primaryColour="", acceptButton={"textColour": " "})
        assert cfg.primaryColour is None
        assert cfg.acceptButton is not None
        assert cfg.acceptButton.textColour is None


class TestFontFamily:
    @pytest.mark.parametrize("value", CSS_VALUES["fontFamily"]["valid"])
    def test_valid_font_accepted(self, value: str) -> None:
        assert BannerConfig(fontFamily=value).fontFamily == value

    @pytest.mark.parametrize("value", [*CSS_VALUES["fontFamily"]["invalid"], "a" * 201])
    def test_invalid_font_rejected(self, value: str) -> None:
        with pytest.raises(ValidationError):
            BannerConfig(fontFamily=value)


class TestOtherBannerFields:
    def test_numbers_within_range_keep_their_type(self) -> None:
        dumped = BannerConfig(borderRadius=12, bannerWidth=600.5, logoHeight=28).model_dump()
        assert dumped == {"borderRadius": 12, "bannerWidth": 600.5, "logoHeight": 28}
        assert isinstance(dumped["borderRadius"], int)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("borderRadius", -1),
            ("borderRadius", 101),
            ("borderRadius", "6px"),
            ("bannerWidth", 5000),
            ("logoHeight", -5),
        ],
    )
    def test_numbers_out_of_range_rejected(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            BannerConfig(**{field: value})

    @pytest.mark.parametrize(
        "field,value",
        [
            ("displayMode", "sidebar"),
            ("cornerPosition", "middle"),
            ("preferencesButtonPosition", "top"),
        ],
    )
    def test_unknown_enum_values_rejected(self, field: str, value: str) -> None:
        with pytest.raises(ValidationError):
            BannerConfig(**{field: value})

    def test_unknown_button_style_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BannerConfig(acceptButton={"style": "glow"})

    def test_dump_keeps_only_provided_and_unknown_keys(self) -> None:
        raw = {
            "displayMode": "overlay",
            "show_reject_all": False,
            "acceptButton": {"style": "filled", "legacy": 1},
            "text": {"title": "Hi"},
        }
        assert BannerConfig.model_validate(raw).model_dump() == raw


class TestLinkUrls:
    @pytest.mark.parametrize(
        "value",
        ["https://example.com/privacy", "http://example.com", "HTTPS://EXAMPLE.COM/x", "/privacy"],
    )
    def test_valid_urls_accepted(self, value: str) -> None:
        assert validate_link_url(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "javascript:void(0)",
            "data:text/html,hi",
            "mailto:a@example.com",
            "www.example.com/privacy",
            "privacy",
            "https://",
            "https://exa mple.com",
            "https://example.com/\x00",
            "//example.com/privacy",
            "/\\example.com/privacy",
        ],
    )
    def test_invalid_urls_rejected(self, value: str) -> None:
        with pytest.raises(ValueError):
            validate_link_url(value)

    def test_url_is_trimmed(self) -> None:
        assert validate_link_url(" https://example.com ") == "https://example.com"

    def test_optional_passes_none(self) -> None:
        assert validate_optional_link_url(None) is None


@pytest.mark.parametrize("schema", CONFIG_SCHEMAS)
class TestConfigSchemas:
    def test_valid_banner_config_accepted(self, schema: type) -> None:
        body = schema(
            banner_config={"primaryColour": "#2563eb", "fontFamily": "Inter, sans-serif"},
            privacy_policy_url="https://example.com/privacy",
            terms_url="/terms",
        )
        assert body.model_dump(exclude_unset=True)["banner_config"] == {
            "primaryColour": "#2563eb",
            "fontFamily": "Inter, sans-serif",
        }

    def test_invalid_banner_colour_rejected(self, schema: type) -> None:
        with pytest.raises(ValidationError):
            schema(banner_config={"backgroundColour": "red; display: none"})

    def test_invalid_font_rejected(self, schema: type) -> None:
        with pytest.raises(ValidationError):
            schema(banner_config={"fontFamily": "Arial; color: red"})

    @pytest.mark.parametrize("field", ["privacy_policy_url", "terms_url"])
    def test_invalid_link_url_rejected(self, schema: type, field: str) -> None:
        with pytest.raises(ValidationError):
            schema(**{field: "javascript:void(0)"})

    def test_null_banner_config_allowed(self, schema: type) -> None:
        assert schema(banner_config=None).banner_config is None
