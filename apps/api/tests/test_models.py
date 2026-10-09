"""Tests for SQLAlchemy model definitions.

These tests verify model structure without needing a database connection.
"""

from sqlalchemy import inspect

from src.models import (
    Base,
    ConsentRecord,
    Cookie,
    CookieAllowListEntry,
    CookieCategory,
    KnownCookie,
    Organisation,
    ScanJob,
    ScanResult,
    Site,
    SiteConfig,
    Translation,
    User,
)


def test_all_models_registered_in_metadata():
    """All expected tables should be present in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "organisations",
        "users",
        "sites",
        "site_configs",
        "cookie_categories",
        "cookies",
        "cookie_allow_list",
        "known_cookies",
        "consent_records",
        "scan_jobs",
        "scan_results",
        "translations",
    }
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_organisation_columns():
    mapper = inspect(Organisation)
    column_names = {c.key for c in mapper.columns}
    assert "id" in column_names
    assert "name" in column_names
    assert "slug" in column_names
    assert "contact_email" in column_names
    assert "created_at" in column_names
    assert "updated_at" in column_names
    assert "deleted_at" in column_names


def test_user_columns_and_fk():
    mapper = inspect(User)
    column_names = {c.key for c in mapper.columns}
    assert "organisation_id" in column_names
    assert "email" in column_names
    assert "password_hash" in column_names
    assert "role" in column_names


def test_site_unique_constraint():
    table = Site.__table__
    constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
    assert "uq_sites_org_domain" in constraint_names


def test_site_config_jsonb_fields():
    mapper = inspect(SiteConfig)
    column_names = {c.key for c in mapper.columns}
    for field in ["regional_modes", "gcm_default", "banner_config"]:
        assert field in column_names, f"Missing JSONB field: {field}"


def test_cookie_category_columns():
    mapper = inspect(CookieCategory)
    column_names = {c.key for c in mapper.columns}
    assert "tcf_purpose_ids" in column_names
    assert "gcm_consent_types" in column_names
    assert "is_essential" in column_names


def test_cookie_unique_constraint():
    table = Cookie.__table__
    constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
    assert "uq_cookies_site_name_domain_type" in constraint_names


def test_cookie_allow_list_unique_constraint():
    table = CookieAllowListEntry.__table__
    constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
    assert "uq_allow_list_site_name_domain" in constraint_names


def test_known_cookie_unique_constraint():
    table = KnownCookie.__table__
    constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
    assert "uq_known_cookies_name_domain" in constraint_names


def test_consent_record_columns():
    mapper = inspect(ConsentRecord)
    column_names = {c.key for c in mapper.columns}
    for field in [
        "visitor_id",
        "action",
        "categories_accepted",
        "tc_string",
        "gcm_state",
        "country_code",
        "consented_at",
    ]:
        assert field in column_names, f"Missing field: {field}"


def test_scan_job_columns():
    mapper = inspect(ScanJob)
    column_names = {c.key for c in mapper.columns}
    assert "status" in column_names
    assert "pages_scanned" in column_names
    assert "cookies_found" in column_names


def test_scan_result_columns():
    mapper = inspect(ScanResult)
    column_names = {c.key for c in mapper.columns}
    assert "page_url" in column_names
    assert "cookie_name" in column_names
    assert "script_source" in column_names
    assert "auto_category" in column_names


def test_translation_unique_constraint():
    table = Translation.__table__
    constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
    assert "uq_translations_site_locale" in constraint_names


def test_uuid_primary_keys():
    """All models should use UUID primary keys."""
    models = [
        Organisation,
        User,
        Site,
        SiteConfig,
        CookieCategory,
        Cookie,
        CookieAllowListEntry,
        KnownCookie,
        ConsentRecord,
        ScanJob,
        ScanResult,
        Translation,
    ]
    for model in models:
        mapper = inspect(model)
        pk_cols = mapper.primary_key
        assert len(pk_cols) == 1, f"{model.__name__} should have exactly one PK column"
        assert str(pk_cols[0].type) == "UUID", (
            f"{model.__name__} PK should be UUID, got {pk_cols[0].type}"
        )
