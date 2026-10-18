"""Unit tests for the publish lifecycle helpers (no database)."""

import pytest

from src.services.config_publishing import reconsent_reasons


def _snapshot(**config):
    return {
        "config": {
            "enabled_categories": ["necessary", "analytics"],
            "disclosed_vendor_ids": [1, 2],
            "privacy_policy_url": None,
            **config,
        },
        "category_tcf_purposes": {"analytics": [1, 7]},
    }


class TestReconsentReasons:
    def test_no_change(self):
        assert reconsent_reasons(_snapshot(), _snapshot()) == []

    @pytest.mark.parametrize(
        "change",
        [
            {"privacy_policy_url": "https://x.test/p"},
            {"banner_config": {"primaryColour": "#000"}},
            {"blocking_mode": "opt_out"},
        ],
    )
    def test_other_changes_do_not_count(self, change):
        assert reconsent_reasons(_snapshot(), _snapshot(**change)) == []

    def test_categories(self):
        draft = _snapshot(enabled_categories=["necessary", "analytics", "marketing"])
        assert reconsent_reasons(_snapshot(), draft) == ["categories"]

    def test_purposes(self):
        draft = {**_snapshot(), "category_tcf_purposes": {"analytics": [1, 7, 8]}}
        assert reconsent_reasons(_snapshot(), draft) == ["purposes"]

    def test_vendors(self):
        assert reconsent_reasons(_snapshot(), _snapshot(disclosed_vendor_ids=[1, 2, 3])) == [
            "vendors"
        ]

    def test_several(self):
        draft = _snapshot(enabled_categories=["necessary"], disclosed_vendor_ids=[])
        assert reconsent_reasons(_snapshot(), draft) == ["categories", "vendors"]
