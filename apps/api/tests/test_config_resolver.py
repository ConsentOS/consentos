"""Tests for configuration hierarchy resolver and publisher."""

import uuid

import pytest

from src.services.config_resolver import (
    ALL_CATEGORIES,
    SYSTEM_DEFAULTS,
    _normalise_enabled_categories,
    build_public_config,
    resolve_config,
)


class TestResolveConfig:
    def test_returns_system_defaults_for_empty_config(self):
        result = resolve_config({})
        assert result["blocking_mode"] == "opt_in"
        assert result["consent_expiry_days"] == 365
        assert result["gcm_enabled"] is True
        assert result["tcf_enabled"] is False
        assert result["gpp_enabled"] is True
        assert result["gpp_supported_apis"] == ["usnat"]
        assert result["gpc_enabled"] is True
        assert result["gpc_jurisdictions"] == [
            "US-CA",
            "US-CO",
            "US-CT",
            "US-TX",
            "US-MT",
        ]
        assert result["gpc_global_honour"] is False

    def test_site_config_overrides_defaults(self):
        site_config = {
            "blocking_mode": "opt_out",
            "consent_expiry_days": 180,
            "tcf_enabled": True,
        }
        result = resolve_config(site_config)
        assert result["blocking_mode"] == "opt_out"
        assert result["consent_expiry_days"] == 180
        assert result["tcf_enabled"] is True
        # Non-overridden values stay as defaults
        assert result["gcm_enabled"] is True

    def test_org_defaults_override_system_defaults(self):
        org_defaults = {"consent_expiry_days": 90}
        result = resolve_config({}, org_defaults=org_defaults)
        assert result["consent_expiry_days"] == 90

    def test_site_config_overrides_org_defaults(self):
        org_defaults = {"consent_expiry_days": 90}
        site_config = {"consent_expiry_days": 30}
        result = resolve_config(site_config, org_defaults=org_defaults)
        assert result["consent_expiry_days"] == 30

    def test_none_values_in_site_config_do_not_override(self):
        site_config = {"blocking_mode": None, "consent_expiry_days": 180}
        result = resolve_config(site_config)
        # None should not override the default
        assert result["blocking_mode"] == "opt_in"
        assert result["consent_expiry_days"] == 180

    def test_regional_override_applied(self):
        site_config = {
            "blocking_mode": "opt_in",
            "regional_modes": {"US-CA": "opt_out", "EU": "opt_in"},
        }
        result = resolve_config(site_config, region="US-CA")
        assert result["blocking_mode"] == "opt_out"

    def test_regional_override_falls_back_to_default(self):
        site_config = {
            "blocking_mode": "opt_in",
            "regional_modes": {"EU": "opt_in", "DEFAULT": "opt_out"},
        }
        result = resolve_config(site_config, region="BR")
        assert result["blocking_mode"] == "opt_out"

    def test_regional_override_no_match_keeps_site_config(self):
        site_config = {
            "blocking_mode": "opt_in",
            "regional_modes": {"EU": "opt_out"},
        }
        result = resolve_config(site_config, region="JP")
        assert result["blocking_mode"] == "opt_in"

    def test_no_region_ignores_regional_modes(self):
        site_config = {
            "blocking_mode": "opt_in",
            "regional_modes": {"US-CA": "opt_out"},
        }
        result = resolve_config(site_config)
        assert result["blocking_mode"] == "opt_in"

    def test_gpp_site_config_overrides_defaults(self):
        site_config = {
            "gpp_enabled": False,
            "gpp_supported_apis": ["usca", "usva"],
        }
        result = resolve_config(site_config)
        assert result["gpp_enabled"] is False
        assert result["gpp_supported_apis"] == ["usca", "usva"]

    def test_gpc_site_config_overrides_defaults(self):
        site_config = {
            "gpc_enabled": False,
            "gpc_global_honour": True,
            "gpc_jurisdictions": ["US-CA"],
        }
        result = resolve_config(site_config)
        assert result["gpc_enabled"] is False
        assert result["gpc_global_honour"] is True
        assert result["gpc_jurisdictions"] == ["US-CA"]

    def test_gpp_gpc_org_defaults_override_system(self):
        org_defaults = {
            "gpp_enabled": False,
            "gpc_global_honour": True,
        }
        result = resolve_config({}, org_defaults=org_defaults)
        assert result["gpp_enabled"] is False
        assert result["gpc_global_honour"] is True
        # Non-overridden GPP/GPC fields stay as system defaults
        assert result["gpc_enabled"] is True

    def test_gpp_gpc_site_overrides_org(self):
        org_defaults = {"gpp_supported_apis": ["usca"]}
        site_config = {"gpp_supported_apis": ["usnat", "usco"]}
        result = resolve_config(site_config, org_defaults=org_defaults)
        assert result["gpp_supported_apis"] == ["usnat", "usco"]

    def test_group_defaults_override_org_defaults(self):
        org_defaults = {"consent_expiry_days": 90, "tcf_enabled": True}
        group_defaults = {"consent_expiry_days": 60}
        result = resolve_config(
            {},
            org_defaults=org_defaults,
            group_defaults=group_defaults,
        )
        assert result["consent_expiry_days"] == 60  # Group overrides org
        assert result["tcf_enabled"] is True  # Still from org

    def test_site_config_overrides_group_defaults(self):
        group_defaults = {"consent_expiry_days": 60}
        site_config = {"consent_expiry_days": 30}
        result = resolve_config(site_config, group_defaults=group_defaults)
        assert result["consent_expiry_days"] == 30  # Site overrides group

    def test_none_in_group_defaults_does_not_override(self):
        org_defaults = {"consent_expiry_days": 90}
        group_defaults = {"consent_expiry_days": None}
        result = resolve_config(
            {},
            org_defaults=org_defaults,
            group_defaults=group_defaults,
        )
        assert result["consent_expiry_days"] == 90  # Org value preserved

    def test_full_hierarchy(self):
        org_defaults = {
            "consent_expiry_days": 90,
            "tcf_enabled": True,
        }
        site_config = {
            "consent_expiry_days": 60,
            "banner_config": {"primaryColour": "#ff0000"},
            "regional_modes": {"EU": "opt_in", "US": "opt_out"},
        }
        result = resolve_config(site_config, org_defaults=org_defaults, region="US")
        assert result["consent_expiry_days"] == 60  # Site overrides org
        assert result["tcf_enabled"] is True  # From org defaults
        assert result["blocking_mode"] == "opt_out"  # Regional override
        assert result["banner_config"] == {"primaryColour": "#ff0000"}

    def test_full_hierarchy_with_group(self):
        org_defaults = {
            "consent_expiry_days": 90,
            "tcf_enabled": True,
            "blocking_mode": "opt_in",
        }
        group_defaults = {
            "consent_expiry_days": 60,
            "privacy_policy_url": "https://group.example.com/privacy",
        }
        site_config = {
            "banner_config": {"primaryColour": "#ff0000"},
            "regional_modes": {"US": "opt_out"},
        }
        result = resolve_config(
            site_config,
            org_defaults=org_defaults,
            group_defaults=group_defaults,
            region="US",
        )
        assert result["consent_expiry_days"] == 60  # From group
        assert result["tcf_enabled"] is True  # From org
        assert result["blocking_mode"] == "opt_out"  # Regional override
        assert result["privacy_policy_url"] == "https://group.example.com/privacy"  # From group
        assert result["banner_config"] == {"primaryColour": "#ff0000"}  # From site


class TestBuildPublicConfig:
    def test_includes_required_fields(self):
        site_id = str(uuid.uuid4())
        resolved = {**SYSTEM_DEFAULTS, "id": "config-123"}
        result = build_public_config(site_id, resolved)

        assert result["site_id"] == site_id
        assert result["id"] == "config-123"
        assert result["blocking_mode"] == "opt_in"
        assert result["consent_expiry_days"] == 365
        assert "gcm_enabled" in result
        assert "tcf_enabled" in result
        assert "banner_config" in result
        assert result["gpp_enabled"] is True
        assert result["gpp_supported_apis"] == ["usnat"]
        assert result["gpc_enabled"] is True
        assert result["gpc_jurisdictions"] == [
            "US-CA",
            "US-CO",
            "US-CT",
            "US-TX",
            "US-MT",
        ]
        assert result["gpc_global_honour"] is False

    def test_strips_unknown_internal_fields(self):
        site_id = str(uuid.uuid4())
        resolved = {
            **SYSTEM_DEFAULTS,
            "id": "",
            "internal_field": "should_not_appear",
            "scan_enabled": True,
        }
        result = build_public_config(site_id, resolved)
        assert "internal_field" not in result
        assert "scan_enabled" not in result


class TestConfigRoutes:
    def test_resolved_config_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/api/v1/config/sites/{site_id}/resolved" in routes

    def test_publish_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/api/v1/config/sites/{site_id}/publish" in routes

    def test_inheritance_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/api/v1/config/sites/{site_id}/inheritance" in routes

    @pytest.mark.asyncio
    async def test_publish_requires_auth(self, client):
        site_id = uuid.uuid4()
        resp = await client.post(f"/api/v1/config/sites/{site_id}/publish")
        assert resp.status_code == 401


class TestEnabledCategories:
    """Cascade semantics for ``enabled_categories``."""

    def test_system_default_is_all_five(self):
        result = resolve_config({})
        assert result["enabled_categories"] == ALL_CATEGORIES

    def test_site_override_narrows_system_default(self):
        result = resolve_config({"enabled_categories": ["necessary", "analytics"]})
        assert result["enabled_categories"] == ["necessary", "analytics"]

    def test_site_override_beats_org_override(self):
        result = resolve_config(
            site_config={"enabled_categories": ["necessary", "marketing"]},
            org_defaults={"enabled_categories": ["necessary", "analytics"]},
        )
        assert result["enabled_categories"] == ["necessary", "marketing"]

    def test_group_override_beats_org_override_when_site_unset(self):
        result = resolve_config(
            site_config={},
            org_defaults={"enabled_categories": ["necessary", "analytics"]},
            group_defaults={"enabled_categories": ["necessary", "functional"]},
        )
        assert result["enabled_categories"] == ["necessary", "functional"]

    def test_unset_site_inherits_org(self):
        result = resolve_config(
            site_config={},
            org_defaults={"enabled_categories": ["necessary", "marketing"]},
        )
        assert result["enabled_categories"] == ["necessary", "marketing"]

    def test_necessary_forced_in_when_missing_from_override(self):
        """Operators can't accidentally drop ``necessary``."""
        result = resolve_config({"enabled_categories": ["analytics", "marketing"]})
        assert "necessary" in result["enabled_categories"]
        assert result["enabled_categories"] == ["necessary", "analytics", "marketing"]

    def test_unknown_slugs_are_stripped(self):
        result = resolve_config({"enabled_categories": ["necessary", "spam", "analytics"]})
        assert result["enabled_categories"] == ["necessary", "analytics"]

    def test_empty_list_falls_back_to_default(self):
        """An empty list is treated as 'no categories configured' → default."""
        result = resolve_config({"enabled_categories": []})
        assert result["enabled_categories"] == ALL_CATEGORIES

    def test_non_list_value_falls_back_to_default(self):
        result = resolve_config({"enabled_categories": "not-a-list"})  # type: ignore[dict-item]
        assert result["enabled_categories"] == ALL_CATEGORIES

    def test_result_is_in_canonical_display_order(self):
        """Insertion order from the cascade must not leak into the output."""
        result = resolve_config({"enabled_categories": ["marketing", "necessary", "analytics"]})
        assert result["enabled_categories"] == ["necessary", "analytics", "marketing"]

    def test_public_config_includes_enabled_categories(self):
        resolved = resolve_config({"enabled_categories": ["necessary", "analytics"]})
        public = build_public_config("site-xyz", resolved)
        assert public["enabled_categories"] == ["necessary", "analytics"]

    def test_normalise_handles_none(self):
        assert _normalise_enabled_categories(None) == ALL_CATEGORIES

    def test_normalise_preserves_explicit_full_list(self):
        assert _normalise_enabled_categories(list(ALL_CATEGORIES)) == ALL_CATEGORIES
