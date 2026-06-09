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
from src.schemas.validators import coerce_blank_to_none


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
