"""Unit tests for the revision snapshot helpers (no database)."""

import datetime
import uuid

import pytest

from src.services.config_resolver import (
    SYSTEM_DEFAULTS,
    apply_consent_group,
    apply_region,
    resolve_config,
)
from src.services.config_snapshot import (
    changed_sources,
    content_hash,
    render_public_config,
    select_translation,
    to_json,
)


def _snapshot(**overrides):
    config = resolve_config({"blocking_mode": "opt_in"})
    config.pop("scan_max_pages")
    snapshot = {
        "format": 1,
        "config": config,
        "extensions": {},
        "gvl_version": 42,
        "category_tcf_purposes": {"analytics": [1, 7]},
        "cookie_count": 3,
        "translations": {"en": {"title": "Hello"}, "fr": {"title": "Bonjour"}},
        "cookies": [],
    }
    snapshot.update(overrides)
    return snapshot


class TestApplyRegion:
    def test_exact_region_wins(self):
        resolved = {"blocking_mode": "opt_in", "regional_modes": {"US-CA": "opt_out"}}
        assert apply_region(resolved, "US-CA")["blocking_mode"] == "opt_out"

    def test_falls_back_to_default(self):
        resolved = {"blocking_mode": "opt_in", "regional_modes": {"DEFAULT": "opt_out"}}
        assert apply_region(resolved, "GB")["blocking_mode"] == "opt_out"

    def test_returns_a_copy(self):
        resolved = {"blocking_mode": "opt_in", "regional_modes": {"GB": "opt_out"}}
        apply_region(resolved, "GB")
        assert resolved["blocking_mode"] == "opt_in"

    def test_no_mapping_leaves_mode(self):
        assert apply_region({"blocking_mode": "opt_in"}, "GB")["blocking_mode"] == "opt_in"


class TestCascadedRegionalModes:
    def test_org_regional_modes_apply_when_site_has_none(self):
        resolved = resolve_config(
            {},
            org_defaults={"regional_modes": {"US-CA": "opt_out"}},
            region="US-CA",
        )
        assert resolved["blocking_mode"] == "opt_out"

    def test_group_regional_modes_apply_when_site_has_none(self):
        resolved = resolve_config(
            {},
            group_defaults={"regional_modes": {"DEFAULT": "informational"}},
            region="GB",
        )
        assert resolved["blocking_mode"] == "informational"

    def test_site_regional_modes_override_parents(self):
        resolved = resolve_config(
            {"regional_modes": {"US-CA": "opt_in"}},
            org_defaults={"regional_modes": {"US-CA": "opt_out"}},
            region="US-CA",
        )
        assert resolved["blocking_mode"] == "opt_in"


class TestApplyConsentGroup:
    def test_sets_group_when_sharing_enabled(self):
        group_id = uuid.uuid4()
        resolved = {"consent_sharing_enabled": True}
        apply_consent_group(resolved, group_id)
        assert resolved["consent_group_id"] == str(group_id)

    def test_leaves_unset_when_sharing_disabled(self):
        resolved = {"consent_sharing_enabled": False}
        apply_consent_group(resolved, uuid.uuid4())
        assert "consent_group_id" not in resolved

    def test_leaves_unset_without_group(self):
        resolved = {"consent_sharing_enabled": True}
        apply_consent_group(resolved, None)
        assert "consent_group_id" not in resolved


class TestRenderPublicConfig:
    def test_id_is_the_consent_version(self):
        version = uuid.uuid4()
        public = render_public_config(_snapshot(), site_id="site-1", consent_version=version)
        assert public["id"] == str(version)
        assert public["site_id"] == "site-1"

    def test_carries_snapshot_extras(self):
        public = render_public_config(_snapshot(), site_id="s", consent_version=uuid.uuid4())
        assert public["gvl_version"] == 42
        assert public["category_tcf_purposes"] == {"analytics": [1, 7]}
        assert public["cookie_count"] == 3

    def test_applies_region(self):
        snapshot = _snapshot()
        snapshot["config"]["regional_modes"] = {"US-CA": "opt_out"}
        public = render_public_config(
            snapshot, site_id="s", consent_version=uuid.uuid4(), region="US-CA"
        )
        assert public["blocking_mode"] == "opt_out"
        assert snapshot["config"]["blocking_mode"] == "opt_in"

    def test_merges_extension_output(self):
        public = render_public_config(
            _snapshot(extensions={"widget": {"enabled": True}}),
            site_id="s",
            consent_version=uuid.uuid4(),
        )
        assert public["widget"] == {"enabled": True}

    def test_includes_requested_translation_only(self):
        public = render_public_config(
            _snapshot(), site_id="s", consent_version=uuid.uuid4(), locale="fr-CA"
        )
        assert public["translations"] == {"fr-ca": {"title": "Bonjour"}}

    def test_defaults_match_system_defaults(self):
        public = render_public_config(_snapshot(), site_id="s", consent_version=uuid.uuid4())
        assert public["consent_expiry_days"] == SYSTEM_DEFAULTS["consent_expiry_days"]


TRANSLATIONS = {"en": {"title": "Hello"}, "en-gb": {"title": "Hello there"}}
ORG_SOURCE = {"kind": "organisation_config", "id": "o1", "content_hash": "a"}
GROUP_SOURCE = {"kind": "site_group_config", "id": "g1", "content_hash": "b"}


class TestSelectTranslation:
    def test_exact_match(self):
        assert select_translation(TRANSLATIONS, "en-GB") == {"en-gb": {"title": "Hello there"}}

    def test_base_language_fallback(self):
        assert select_translation(TRANSLATIONS, "en-US") == {"en-us": {"title": "Hello"}}

    def test_no_locale(self):
        assert select_translation(TRANSLATIONS, None) == {}

    def test_no_match(self):
        assert select_translation(TRANSLATIONS, "de") == {}


class TestContentHash:
    def test_ignores_key_order(self):
        assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})

    def test_changes_with_content(self):
        assert content_hash({"a": 1}) != content_hash({"a": 2})

    def test_same_before_and_after_json_round_trip(self):
        value = {"id": uuid.UUID(int=1), "when": datetime.date(2026, 1, 1)}
        assert content_hash(value) == content_hash(to_json(value))


class TestToJson:
    def test_converts_uuid_and_dates(self):
        value = to_json({"id": uuid.UUID(int=1), "on": datetime.date(2026, 1, 2)})
        assert value == {"id": "00000000-0000-0000-0000-000000000001", "on": "2026-01-02"}

    def test_rejects_unknown_types(self):
        with pytest.raises(TypeError):
            to_json({"value": object()})


class TestChangedSources:
    def test_nothing_changed(self):
        assert changed_sources([ORG_SOURCE, GROUP_SOURCE], [ORG_SOURCE, GROUP_SOURCE]) == []

    def test_parent_content_changed(self):
        current = {**ORG_SOURCE, "content_hash": "z"}
        assert changed_sources([ORG_SOURCE], [current]) == [current]

    def test_parent_added(self):
        assert changed_sources([ORG_SOURCE], [ORG_SOURCE, GROUP_SOURCE]) == [GROUP_SOURCE]

    def test_parent_removed(self):
        assert changed_sources([ORG_SOURCE, GROUP_SOURCE], [ORG_SOURCE]) == [GROUP_SOURCE]
