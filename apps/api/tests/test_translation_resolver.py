"""Tests for the translation cascade resolver."""

from src.services.translation_resolver import (
    TRANSLATION_KEYS,
    resolve_translation,
    resolve_translation_sources,
)


class TestResolveTranslation:
    def test_empty_everywhere_returns_empty(self):
        assert resolve_translation("fr") == {}

    def test_site_only_matches_existing_behaviour(self):
        site_rows = {"fr": {"title": "Bonjour"}}
        result = resolve_translation("fr", site_rows=site_rows)
        assert result == {"title": "Bonjour"}

    def test_site_overrides_group_overrides_org_per_key(self):
        org_rows = {"fr": {"title": "Org title", "acceptAll": "Org accept"}}
        group_rows = {"fr": {"acceptAll": "Group accept"}}
        site_rows = {"fr": {"title": "Site title"}}
        result = resolve_translation(
            "fr", org_rows=org_rows, group_rows=group_rows, site_rows=site_rows
        )
        # Site wins for "title" (its own override); group wins for
        # "acceptAll" since site never redefines it — org's value for
        # that key is shadowed, not the whole locale block.
        assert result == {"title": "Site title", "acceptAll": "Group accept"}

    def test_org_only_provides_keys_site_never_defines(self):
        org_rows = {"fr": {"title": "Org title", "acceptAll": "Org accept"}}
        site_rows = {"fr": {"title": "Site title"}}
        result = resolve_translation("fr", org_rows=org_rows, site_rows=site_rows)
        assert result == {"title": "Site title", "acceptAll": "Org accept"}

    def test_base_language_fallback_applies_independently_per_layer(self):
        # Site has fr-CA only; org has fr only. Each layer resolves its
        # own base-language fallback before the per-key merge happens.
        org_rows = {"fr": {"acceptAll": "Org accept"}}
        site_rows = {"fr-ca": {"title": "Titre site"}}
        result = resolve_translation("fr-CA", org_rows=org_rows, site_rows=site_rows)
        assert result == {"acceptAll": "Org accept", "title": "Titre site"}

    def test_no_match_at_any_layer_returns_empty(self):
        org_rows = {"de": {"title": "Hallo"}}
        result = resolve_translation("fr", org_rows=org_rows)
        assert result == {}

    def test_locale_matching_is_case_insensitive(self):
        site_rows = {"fr": {"title": "Bonjour"}}
        result = resolve_translation("FR", site_rows=site_rows)
        assert result == {"title": "Bonjour"}


class TestResolveTranslationSources:
    def test_every_key_reported_even_when_unset(self):
        sources = resolve_translation_sources("fr")
        assert set(sources.keys()) == set(TRANSLATION_KEYS)
        for info in sources.values():
            assert info["source"] == "system"
            assert info["resolved_value"] is None

    def test_source_attribution_follows_precedence(self):
        org_rows = {"fr": {"title": "Org title", "acceptAll": "Org accept"}}
        group_rows = {"fr": {"acceptAll": "Group accept"}}
        site_rows = {"fr": {"title": "Site title"}}
        sources = resolve_translation_sources(
            "fr", org_rows=org_rows, group_rows=group_rows, site_rows=site_rows
        )
        assert sources["title"]["source"] == "site"
        assert sources["title"]["resolved_value"] == "Site title"
        assert sources["title"]["org_value"] == "Org title"
        assert sources["title"]["group_value"] is None

        assert sources["acceptAll"]["source"] == "group"
        assert sources["acceptAll"]["resolved_value"] == "Group accept"
        assert sources["acceptAll"]["org_value"] == "Org accept"

        assert sources["rejectAll"]["source"] == "system"
        assert sources["rejectAll"]["resolved_value"] is None
