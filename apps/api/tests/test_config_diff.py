"""Unit tests for config diffs (no database)."""

from src.services.config_diff import EMPTY, Version, diff_versions


def _version(config=None, *, site=None, org=None, group=None, **snapshot):
    sources = [{"kind": "organisation_config", "id": "o", "values": org or {}}]
    if group is not None:
        sources.append({"kind": "site_group_config", "id": "g", "values": group})
    return Version(
        snapshot={"config": config or {}, **snapshot},
        site_layer={"site_config": site or {}, "allow_list": snapshot.pop("allow_list", [])},
        sources=sources,
    )


def _changes(before, after):
    return [(c.area, c.key, c.before, c.after, c.source) for c in diff_versions(before, after)]


class TestConfig:
    def test_nothing_changed(self):
        version = _version({"terms_url": "https://t"})
        assert diff_versions(version, version) == []

    def test_site_change(self):
        before = _version({"terms_url": "https://a"}, site={"terms_url": "https://a"})
        after = _version({"terms_url": "https://b"}, site={"terms_url": "https://b"})
        assert _changes(before, after) == [
            ("settings", "terms_url", "https://a", "https://b", "site")
        ]

    def test_inherited_from_the_organisation(self):
        before = _version({"consent_expiry_days": 365})
        after = _version({"consent_expiry_days": 200}, org={"consent_expiry_days": 200})
        assert _changes(before, after)[0][4] == "organisation"

    def test_site_group_overrides_the_organisation(self):
        after = _version(
            {"consent_expiry_days": 90},
            org={"consent_expiry_days": 200},
            group={"consent_expiry_days": 90},
        )
        assert _changes(_version({"consent_expiry_days": 365}), after)[0][4] == "site_group"

    def test_system_default(self):
        before = _version({"consent_expiry_days": 200}, site={"consent_expiry_days": 200})
        after = _version({"consent_expiry_days": 365}, site={"consent_expiry_days": None})
        assert _changes(before, after)[0][4] == "system"

    def test_areas(self):
        after = _version({"enabled_categories": ["necessary"]})
        before = _version({"enabled_categories": ["necessary", "analytics"]})
        assert _changes(before, after)[0][0] == "categories"

    def test_consent_group_comes_from_the_group(self):
        after = _version({"consent_group_id": "g"})
        assert _changes(_version(), after)[0][4] == "site_group"

    def test_gvl_version(self):
        assert _changes(_version(gvl_version=1), _version(gvl_version=2)) == [
            ("settings", "gvl_version", 1, 2, "system")
        ]


class TestBanner:
    def test_one_change_per_option(self):
        before = _version({"banner_config": {"primaryColour": "#000", "position": "bottom"}})
        after = _version(
            {"banner_config": {"primaryColour": "#fff", "position": "bottom", "logo": "x"}},
            site={"banner_config": {"primaryColour": "#fff"}},
        )
        assert _changes(before, after) == [
            ("banner", "banner_config.logo", None, "x", "site"),
            ("banner", "banner_config.primaryColour", "#000", "#fff", "site"),
        ]


class TestTranslations:
    def test_per_string(self):
        before = _version(translations={"fr": {"title": "A", "body": "B"}})
        after = _version(translations={"fr": {"title": "C", "body": "B"}, "de": {"title": "D"}})
        assert _changes(before, after) == [
            ("translations", "de.title", None, "D", "site"),
            ("translations", "fr.title", "A", "C", "site"),
        ]


class TestCookies:
    def test_declared_cookies(self):
        ga = {"name": "_ga", "domain": ".x", "type": "cookie", "category": None}
        before = _version(cookies=[ga])
        after = _version(cookies=[{**ga, "category": "analytics"}])
        [change] = diff_versions(before, after)
        assert (change.area, change.key) == ("cookies", "cookies._ga@.x#cookie")
        assert change.after["category"] == "analytics"

    def test_allow_list(self):
        entry = {"name_pattern": "_ga", "domain_pattern": "*", "category_id": "c"}
        [change] = diff_versions(_version(), _version(allow_list=[entry]))
        assert (change.key, change.before) == ("allow_list._ga@*", None)


class TestOther:
    def test_category_purposes(self):
        before = _version(category_tcf_purposes={"analytics": [1]})
        after = _version(category_tcf_purposes={"analytics": [1, 7]})
        assert _changes(before, after) == [
            ("categories", "category_tcf_purposes.analytics", [1], [1, 7], "system")
        ]

    def test_extensions(self):
        assert _changes(_version(extensions={}), _version(extensions={"widget": 1})) == [
            ("other", "widget", None, 1, "system")
        ]

    def test_against_nothing_published(self):
        changes = diff_versions(EMPTY, _version({"terms_url": "https://t"}))
        assert [c.key for c in changes] == ["terms_url"]
