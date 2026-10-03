"""Unit tests for consent analytics aggregation helpers (no database)."""

from src.services.analytics import merge_category_rates, rate


class TestRate:
    def test_zero_decisions_is_zero(self):
        assert rate(0, 0) == 0.0

    def test_all_granted_is_one(self):
        assert rate(10, 10) == 1.0

    def test_none_granted_is_zero(self):
        assert rate(0, 5) == 0.0

    def test_half_granted(self):
        # 4 granted of 8 decisions
        assert rate(4, 8) == 0.5

    def test_rounds_to_four_dp(self):
        assert rate(1, 3) == 0.3333


class TestMergeCategoryRates:
    def test_empty(self):
        assert merge_category_rates({}, {}) == []

    def test_sorted_and_rated(self):
        rates = merge_category_rates(
            {"marketing": 3, "analytics": 9},
            {"marketing": 1, "analytics": 1},
        )
        # alphabetical order
        assert [r.category for r in rates] == ["analytics", "marketing"]
        analytics = rates[0]
        assert analytics.accepted == 9
        assert analytics.rejected == 1
        assert analytics.rate == 0.9

    def test_category_only_rejected(self):
        rates = merge_category_rates({}, {"marketing": 4})
        assert rates[0].rate == 0.0
        assert rates[0].accepted == 0
        assert rates[0].rejected == 4
