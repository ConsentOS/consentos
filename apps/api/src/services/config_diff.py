"""Field-by-field differences between two versions of a site's config.

Compares what two snapshots serve, grouped by the area of the admin UI
the change belongs to, and says where each changed value comes from so
inherited changes can be labelled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Snapshot config fields by admin UI area. Anything not listed is a
# setting.
_FIELD_AREAS = {
    "banner_config": "banner",
    "enabled_categories": "categories",
}


@dataclass(frozen=True)
class Change:
    area: str
    key: str
    before: Any
    after: Any
    # Where the new value comes from: "site", "site_group",
    # "organisation" or "system".
    source: str


@dataclass(frozen=True)
class Version:
    """One side of a comparison: a revision, the draft, or nothing yet."""

    snapshot: dict[str, Any]
    site_layer: dict[str, Any]
    sources: list[dict[str, Any]]


EMPTY = Version(snapshot={}, site_layer={}, sources=[])


def diff_versions(before: Version, after: Version) -> list[Change]:
    """Every difference between two versions, in a stable order."""
    return [
        *_config_changes(before, after),
        *_banner_changes(before, after),
        *_translation_changes(before, after),
        *_category_purpose_changes(before, after),
        *_cookie_changes(before, after),
        *_extension_changes(before, after),
    ]


def _config_changes(before: Version, after: Version) -> list[Change]:
    old = before.snapshot.get("config", {})
    new = after.snapshot.get("config", {})
    changes = [
        Change(
            area=_FIELD_AREAS.get(key, "settings"),
            key=key,
            before=old.get(key),
            after=new.get(key),
            source=_config_source(after, key),
        )
        for key in sorted(old.keys() | new.keys())
        if key != "banner_config" and old.get(key) != new.get(key)
    ]
    if before.snapshot.get("gvl_version") != after.snapshot.get("gvl_version"):
        changes.append(
            Change(
                area="settings",
                key="gvl_version",
                before=before.snapshot.get("gvl_version"),
                after=after.snapshot.get("gvl_version"),
                source="system",
            )
        )
    return changes


def _banner_changes(before: Version, after: Version) -> list[Change]:
    """Banner settings, one change per option rather than one blob."""
    old = before.snapshot.get("config", {}).get("banner_config") or {}
    new = after.snapshot.get("config", {}).get("banner_config") or {}
    source = _config_source(after, "banner_config")
    return [
        Change(
            area="banner",
            key=f"banner_config.{key}",
            before=old.get(key),
            after=new.get(key),
            source=source,
        )
        for key in sorted(old.keys() | new.keys())
        if old.get(key) != new.get(key)
    ]


def _translation_changes(before: Version, after: Version) -> list[Change]:
    old = before.snapshot.get("translations", {})
    new = after.snapshot.get("translations", {})
    changes = []
    for locale in sorted(old.keys() | new.keys()):
        old_strings = old.get(locale, {})
        new_strings = new.get(locale, {})
        changes.extend(
            Change(
                area="translations",
                key=f"{locale}.{key}",
                before=old_strings.get(key),
                after=new_strings.get(key),
                source="site",
            )
            for key in sorted(old_strings.keys() | new_strings.keys())
            if old_strings.get(key) != new_strings.get(key)
        )
    return changes


def _category_purpose_changes(before: Version, after: Version) -> list[Change]:
    old = before.snapshot.get("category_tcf_purposes", {})
    new = after.snapshot.get("category_tcf_purposes", {})
    return [
        Change(
            area="categories",
            key=f"category_tcf_purposes.{slug}",
            before=old.get(slug),
            after=new.get(slug),
            source="system",
        )
        for slug in sorted(old.keys() | new.keys())
        if old.get(slug) != new.get(slug)
    ]


def _cookie_changes(before: Version, after: Version) -> list[Change]:
    """Declared cookies and allow-list entries, keyed by what identifies them."""
    changes = _keyed_changes(
        before.snapshot.get("cookies", []),
        after.snapshot.get("cookies", []),
        key=lambda c: f"cookies.{c['name']}@{c['domain']}#{c['type']}",
    )
    changes += _keyed_changes(
        before.site_layer.get("allow_list", []),
        after.site_layer.get("allow_list", []),
        key=lambda e: f"allow_list.{e['name_pattern']}@{e['domain_pattern']}",
    )
    return changes


def _keyed_changes(old: list[dict], new: list[dict], *, key) -> list[Change]:
    old_by_key = {key(item): item for item in old}
    new_by_key = {key(item): item for item in new}
    return [
        Change(
            area="cookies",
            key=item_key,
            before=old_by_key.get(item_key),
            after=new_by_key.get(item_key),
            source="site",
        )
        for item_key in sorted(old_by_key.keys() | new_by_key.keys())
        if old_by_key.get(item_key) != new_by_key.get(item_key)
    ]


def _extension_changes(before: Version, after: Version) -> list[Change]:
    old = before.snapshot.get("extensions", {})
    new = after.snapshot.get("extensions", {})
    return [
        Change(
            area="other",
            key=key,
            before=old.get(key),
            after=new.get(key),
            source="system",
        )
        for key in sorted(old.keys() | new.keys())
        if old.get(key) != new.get(key)
    ]


def _config_source(version: Version, key: str) -> str:
    """Which layer a config value in ``version`` comes from."""
    if key == "consent_group_id":
        return "site_group"
    if version.site_layer.get("site_config", {}).get(key) is not None:
        return "site"
    # Later sources override earlier ones, so the last that sets it wins.
    for source in reversed(version.sources):
        if source.get("values", {}).get(key) is not None:
            return _SOURCE_KINDS.get(source["kind"], source["kind"])
    return "system"


_SOURCE_KINDS = {
    "organisation_config": "organisation",
    "site_group_config": "site_group",
}
