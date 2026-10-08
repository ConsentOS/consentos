"""Unit tests for shared schema validators.

These cover the ``coerce_blank_to_none`` field validator applied to the
free-text columns on ``SiteConfigUpdate``, ``OrgConfigUpdate`` and
``SiteGroupConfigUpdate``. The validator exists so the admin UI's
"Reset to inherited" flow can clear a field by submitting ``""`` and
have the cascade resolver fall through to the parent layer, rather
than persisting an empty string that blocks inheritance.
"""

import pytest

from src.schemas.org_config import OrgConfigUpdate
from src.schemas.site import SiteConfigUpdate
from src.schemas.site_group_config import SiteGroupConfigUpdate
from src.schemas.validators import (
    MAX_REGEX_PATTERN_LENGTH,
    coerce_blank_to_none,
    validate_regex_pattern,
)


class TestCoerceBlankToNone:
    @pytest.mark.parametrize("value", ["", " ", "\t", "\n  \t"])
    def test_blank_strings_become_none(self, value: str) -> None:
        assert coerce_blank_to_none(value) is None

    @pytest.mark.parametrize(
        "value",
        ["x", " not blank ", "https://example.com", "0 0 * * *"],
    )
    def test_non_blank_strings_pass_through(self, value: str) -> None:
        assert coerce_blank_to_none(value) == value

    @pytest.mark.parametrize("value", [None, 0, False, [], {}])
    def test_non_strings_pass_through(self, value: object) -> None:
        assert coerce_blank_to_none(value) == value


class TestSiteConfigUpdateBlankCoercion:
    @pytest.mark.parametrize(
        "field",
        ["privacy_policy_url", "terms_url", "scan_schedule_cron", "tcf_publisher_cc"],
    )
    def test_blank_input_becomes_none(self, field: str) -> None:
        parsed = SiteConfigUpdate.model_validate({field: ""})
        assert getattr(parsed, field) is None

    def test_non_blank_url_is_preserved(self) -> None:
        parsed = SiteConfigUpdate.model_validate(
            {"privacy_policy_url": "https://example.com/privacy"}
        )
        assert parsed.privacy_policy_url == "https://example.com/privacy"

    def test_explicit_null_still_clears(self) -> None:
        parsed = SiteConfigUpdate.model_validate({"privacy_policy_url": None})
        assert parsed.privacy_policy_url is None
        # ``model_dump(exclude_unset=True)`` must still include the field so
        # the PATCH handler routes ``null`` through to the column update.
        assert "privacy_policy_url" in parsed.model_dump(exclude_unset=True)


class TestOrgAndGroupBlankCoercion:
    @pytest.mark.parametrize(
        "field",
        ["privacy_policy_url", "terms_url", "scan_schedule_cron", "tcf_publisher_cc"],
    )
    def test_org_update_coerces_blank(self, field: str) -> None:
        parsed = OrgConfigUpdate.model_validate({field: "   "})
        assert getattr(parsed, field) is None

    @pytest.mark.parametrize(
        "field",
        [
            "privacy_policy_url",
            "terms_url",
            "scan_schedule_cron",
            "tcf_publisher_cc",
            "consent_bridge_url",
        ],
    )
    def test_group_update_coerces_blank(self, field: str) -> None:
        parsed = SiteGroupConfigUpdate.model_validate({field: ""})
        assert getattr(parsed, field) is None


class TestValidateRegexPattern:
    @pytest.mark.parametrize(
        "pattern",
        [r"_hj.*", r"_pk_id\..*", r".*", r"(_ga|_gid)", r"_ga_[A-Z0-9]+", r"(ab)?", r"(a|b)+"],
    )
    def test_accepts_ordinary_patterns(self, pattern):
        assert validate_regex_pattern(pattern) == pattern

    @pytest.mark.parametrize(
        "pattern",
        [
            r"(a+)+",
            r"(a*)*",
            r"(a|aa)+",
            r"(?:ab|cd){2,}",
            r"(\w+\s?)*",
            r"x(?=(a+)+)",
            r"(.*a){20}",
        ],
    )
    def test_rejects_nested_quantifiers(self, pattern):
        with pytest.raises(ValueError, match="must not repeat"):
            validate_regex_pattern(pattern)

    @pytest.mark.parametrize("pattern", [r"[abc", r"(unclosed", r"*start", r"a{99999999999}"])
    def test_rejects_invalid_syntax(self, pattern):
        with pytest.raises(ValueError, match="Invalid regular expression"):
            validate_regex_pattern(pattern)

    def test_rejects_overlong_pattern(self):
        with pytest.raises(ValueError, match="at most"):
            validate_regex_pattern("a" * (MAX_REGEX_PATTERN_LENGTH + 1))

    def test_accepts_pattern_at_length_limit(self):
        pattern = "a" * MAX_REGEX_PATTERN_LENGTH
        assert validate_regex_pattern(pattern) == pattern
