"""Configuration hierarchy resolver.

Resolves site configuration by merging:
  System Defaults → Org Defaults → Site Group Defaults → Site Config → Regional Overrides

Produces a fully resolved public config suitable for the banner script.
"""

from __future__ import annotations

from typing import Any

# Every known cookie category, in the canonical display order the
# banner uses. The system default for ``enabled_categories`` is this
# full list; operators subset from the top via the cascade.
ALL_CATEGORIES: list[str] = [
    "necessary",
    "functional",
    "analytics",
    "marketing",
    "personalisation",
]

# ``necessary`` is never optional — operators can't hide it and the
# merged result always contains it, even if it's been accidentally
# dropped from every layer of the cascade.
REQUIRED_CATEGORIES: frozenset[str] = frozenset({"necessary"})


# System-level defaults (hard-coded, lowest priority)
SYSTEM_DEFAULTS: dict[str, Any] = {
    "blocking_mode": "opt_in",
    "tcf_enabled": False,
    "gpp_enabled": True,
    "gpp_supported_apis": ["usnat"],
    "gpc_enabled": True,
    "gpc_jurisdictions": ["US-CA", "US-CO", "US-CT", "US-TX", "US-MT"],
    "gpc_global_honour": False,
    "gcm_enabled": True,
    "shopify_privacy_enabled": False,
    "gcm_default": {
        "ad_storage": "denied",
        "ad_user_data": "denied",
        "ad_personalization": "denied",
        "analytics_storage": "denied",
        "functionality_storage": "denied",
        "personalization_storage": "denied",
        "security_storage": "granted",
    },
    "banner_config": None,
    "privacy_policy_url": None,
    "terms_url": None,
    "consent_expiry_days": 365,
    # All five categories visible by default; any cascade layer may
    # narrow this to a subset. The resolver normalises the result
    # via ``_normalise_enabled_categories``.
    "enabled_categories": ALL_CATEGORIES,
}


def resolve_config(
    site_config: dict[str, Any],
    org_defaults: dict[str, Any] | None = None,
    group_defaults: dict[str, Any] | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Resolve the full configuration by merging layers.

    Args:
        site_config: Site-specific configuration from the database.
        org_defaults: Organisation-level default overrides (optional).
        group_defaults: Site-group-level default overrides (optional).
        region: ISO region code for regional mode override (optional).

    Returns:
        Fully resolved configuration dictionary.
    """
    # Start with system defaults
    resolved = {**SYSTEM_DEFAULTS}

    # Apply organisation defaults (if any)
    if org_defaults:
        _merge_non_none(resolved, org_defaults)

    # Apply site group defaults (if any)
    if group_defaults:
        _merge_non_none(resolved, group_defaults)

    # Apply site-specific config
    _merge_non_none(resolved, site_config)

    # Apply regional blocking mode override
    if region and site_config.get("regional_modes"):
        regional_modes = site_config["regional_modes"]
        if isinstance(regional_modes, dict):
            # Try exact match first, then fall back to DEFAULT
            regional_mode = regional_modes.get(region) or regional_modes.get("DEFAULT")
            if regional_mode:
                resolved["blocking_mode"] = regional_mode

    resolved["enabled_categories"] = _normalise_enabled_categories(
        resolved.get("enabled_categories")
    )

    return resolved


def _normalise_enabled_categories(value: Any) -> list[str]:
    """Clean a merged ``enabled_categories`` value into a canonical list.

    - ``None`` / empty / invalid types fall back to the full default.
    - Unknown slugs are stripped so a typo can't light up a category
      the banner doesn't actually render.
    - ``necessary`` is always forced into the output — required
      categories can never be absent, regardless of what the operator
      configured. The order mirrors ``ALL_CATEGORIES`` so the banner
      renders tabs in a consistent order no matter the insertion order.
    """
    if not isinstance(value, list) or not value:
        return list(ALL_CATEGORIES)

    known = set(ALL_CATEGORIES)
    picked = {slug for slug in value if isinstance(slug, str) and slug in known}
    picked.update(REQUIRED_CATEGORIES)
    return [slug for slug in ALL_CATEGORIES if slug in picked]


def build_public_config(
    site_id: str,
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Build a public configuration JSON for the banner script.

    Strips internal fields and adds the site_id for identification.
    """
    return {
        "id": resolved.get("id", ""),
        "site_id": site_id,
        "blocking_mode": resolved["blocking_mode"],
        "regional_modes": resolved.get("regional_modes"),
        "tcf_enabled": resolved["tcf_enabled"],
        "gpp_enabled": resolved["gpp_enabled"],
        "gpp_supported_apis": resolved.get("gpp_supported_apis"),
        "gpc_enabled": resolved["gpc_enabled"],
        "gpc_jurisdictions": resolved.get("gpc_jurisdictions"),
        "gpc_global_honour": resolved["gpc_global_honour"],
        "gcm_enabled": resolved["gcm_enabled"],
        "gcm_default": resolved.get("gcm_default"),
        "shopify_privacy_enabled": resolved["shopify_privacy_enabled"],
        "banner_config": resolved.get("banner_config"),
        "privacy_policy_url": resolved.get("privacy_policy_url"),
        "terms_url": resolved.get("terms_url"),
        "consent_expiry_days": resolved["consent_expiry_days"],
        "consent_group_id": resolved.get("consent_group_id"),
        "ab_test": resolved.get("ab_test"),
        # Public name is ``enabled_categories`` here; the banner schema
        # converts that to ``enabledCategories`` when it serialises.
        "enabled_categories": _normalise_enabled_categories(resolved.get("enabled_categories")),
        "consent_bridge_url": resolved.get("consent_bridge_url"),
    }


CONFIG_FIELDS = (
    "blocking_mode",
    "regional_modes",
    "tcf_enabled",
    "tcf_publisher_cc",
    "gpp_enabled",
    "gpp_supported_apis",
    "gpc_enabled",
    "gpc_jurisdictions",
    "gpc_global_honour",
    "gcm_enabled",
    "gcm_default",
    "shopify_privacy_enabled",
    "banner_config",
    "privacy_policy_url",
    "terms_url",
    "consent_expiry_days",
    "enabled_categories",
    "consent_sharing_enabled",
    "consent_bridge_url",
)


def orm_to_config_dict(obj: Any, *, include_id: bool = False) -> dict[str, Any]:
    """Convert a SiteConfig or OrgConfig ORM object to a dict of config fields.

    Only includes fields that are explicitly set (not NULL). This allows the
    hierarchy to work correctly: unset fields at higher-priority layers don't
    block inheritance from lower-priority layers.
    """
    d: dict[str, Any] = {}
    if include_id and hasattr(obj, "id"):
        d["id"] = str(obj.id)
    for field in CONFIG_FIELDS:
        if hasattr(obj, field):
            value = getattr(obj, field)
            if value is not None:
                d[field] = value
    return d


def _merge_non_none(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Merge source into target, skipping None values in source."""
    for key, value in source.items():
        if value is not None:
            target[key] = value
