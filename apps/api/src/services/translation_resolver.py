"""Translation cascade resolver.

Resolves banner translation strings by merging:
  Org Translations -> Site Group Translations -> Site Translations

Unlike ``config_resolver.resolve_config`` (which replaces a config
field wholesale per layer), translations merge key-by-key within a
locale: an operator can define common strings once at the
organisation level and override only the handful that differ at
group/site level, without redeclaring every key. English hard-coded
defaults remain client-side in the banner (``apps/banner/src/i18n.ts``)
and are intentionally not modelled here.
"""

from __future__ import annotations

# The translation keys the banner understands. Kept in sync with
# apps/banner/src/i18n.ts's TranslationStrings interface and
# apps/admin-ui/src/constants/translations.ts's TRANSLATION_KEYS.
TRANSLATION_KEYS: tuple[str, ...] = (
    "title",
    "description",
    "acceptAll",
    "rejectAll",
    "managePreferences",
    "savePreferences",
    "privacyPolicyLink",
    "closeLabel",
    "categoryNecessary",
    "categoryNecessaryDesc",
    "categoryFunctional",
    "categoryFunctionalDesc",
    "categoryAnalytics",
    "categoryAnalyticsDesc",
    "categoryMarketing",
    "categoryMarketingDesc",
    "categoryPersonalisation",
    "categoryPersonalisationDesc",
    "cookieCount",
)


def _locale_candidates(locale: str) -> list[str]:
    """Exact match then base-language fallback, lower-cased.

    Mirrors the fallback algorithm previously used by the site-only
    translation lookup (``en-us`` -> ``en``).
    """
    requested = locale.lower()
    candidates = [requested]
    base = requested.split("-")[0]
    if base != requested:
        candidates.append(base)
    return candidates


def _pick_layer_strings(
    rows_by_locale: dict[str, dict[str, str]], locale: str
) -> dict[str, str]:
    """Return the first matching candidate's strings for one scope.

    ``rows_by_locale`` holds every locale stored at that scope (not
    just the requested candidates) because each layer must attempt its
    own base-language fallback independently — a site's ``fr-CA`` row
    and an org's ``fr`` row can both contribute keys to the same
    resolved locale even though neither is an exact match for the
    other.
    """
    for candidate in _locale_candidates(locale):
        if candidate in rows_by_locale:
            return rows_by_locale[candidate]
    return {}


def resolve_translation(
    locale: str,
    *,
    org_rows: dict[str, dict[str, str]] | None = None,
    group_rows: dict[str, dict[str, str]] | None = None,
    site_rows: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    """Merge translation strings key-by-key across Org -> Group -> Site.

    Each layer only overrides the keys it actually defines, so an
    operator can set common strings once at org level and override
    only the few that differ at site level.
    """
    merged: dict[str, str] = {}
    for rows in (org_rows or {}, group_rows or {}, site_rows or {}):
        merged.update(_pick_layer_strings(rows, locale))
    return merged


def resolve_translation_sources(
    locale: str,
    *,
    org_rows: dict[str, dict[str, str]] | None = None,
    group_rows: dict[str, dict[str, str]] | None = None,
    site_rows: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict]:
    """Per-key source attribution for the admin inheritance UI.

    Mirrors ``config_resolver``'s per-field inheritance shape but keyed
    by translation key instead of config field. ``system_value`` is
    always ``None`` here — the English defaults live client-side in the
    banner, not in this service; the admin UI already renders those as
    input placeholders.
    """
    org_layer = _pick_layer_strings(org_rows or {}, locale)
    group_layer = _pick_layer_strings(group_rows or {}, locale)
    site_layer = _pick_layer_strings(site_rows or {}, locale)

    sources: dict[str, dict] = {}
    for key in TRANSLATION_KEYS:
        site_val = site_layer.get(key)
        group_val = group_layer.get(key)
        org_val = org_layer.get(key)
        if site_val is not None:
            source, resolved = "site", site_val
        elif group_val is not None:
            source, resolved = "group", group_val
        elif org_val is not None:
            source, resolved = "org", org_val
        else:
            source, resolved = "system", None
        sources[key] = {
            "resolved_value": resolved,
            "source": source,
            "site_value": site_val,
            "group_value": group_val,
            "org_value": org_val,
            "system_value": None,
        }
    return sources
