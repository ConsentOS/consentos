"""add site_config_revisions

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-18

Immutable published snapshots of each site's config. A trigger rejects
changes to a revision's recorded content. ``sites.live_revision_id``
points at the revision the banner serves.

Every existing site with a config gets v1, built from its current
effective config, so it keeps serving exactly what it served before.
v1 takes the site's ``site_configs.id`` as its consent version, which is
what the banner was already given as ``config.id``, so no visitor is
asked to consent again because of the upgrade.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Kept here rather than imported from the model so this migration stays
# fixed if the model's copy changes later.
REJECT_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION reject_site_config_revision_update() RETURNS trigger AS $$
BEGIN
    IF NEW.site_id IS DISTINCT FROM OLD.site_id
        OR NEW.number IS DISTINCT FROM OLD.number
        OR NEW.consent_version IS DISTINCT FROM OLD.consent_version
        OR NEW.requires_reconsent IS DISTINCT FROM OLD.requires_reconsent
        OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
        OR NEW.site_layer IS DISTINCT FROM OLD.site_layer
        OR NEW.sources IS DISTINCT FROM OLD.sources
        OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
        OR NEW.note IS DISTINCT FROM OLD.note
        OR NEW.published_at IS DISTINCT FROM OLD.published_at
    THEN
        RAISE EXCEPTION 'site_config_revisions rows cannot be changed';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

REJECT_UPDATE_TRIGGER = """
CREATE TRIGGER site_config_revisions_reject_update
    BEFORE UPDATE ON site_config_revisions
    FOR EACH ROW EXECUTE FUNCTION reject_site_config_revision_update()
"""


def upgrade() -> None:
    op.create_table(
        "site_config_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("consent_version", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requires_reconsent", sa.Boolean(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("site_layer", postgresql.JSONB(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "rolled_back_from_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("site_config_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "published_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("site_id", "number", name="uq_site_config_revisions_site_number"),
        sa.CheckConstraint("number > 0", name="ck_site_config_revisions_number_positive"),
    )
    op.create_index("ix_site_config_revisions_site_id", "site_config_revisions", ["site_id"])
    op.execute(REJECT_UPDATE_FUNCTION)
    op.execute(REJECT_UPDATE_TRIGGER)
    op.add_column(
        "sites",
        sa.Column("live_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sites_live_revision_id",
        "sites",
        "site_config_revisions",
        ["live_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    backfill_initial_revisions(op.get_bind())


def downgrade() -> None:
    op.drop_constraint("fk_sites_live_revision_id", "sites", type_="foreignkey")
    op.drop_column("sites", "live_revision_id")
    op.execute(
        "DROP TRIGGER IF EXISTS site_config_revisions_reject_update ON site_config_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_site_config_revision_update()")
    op.drop_index("ix_site_config_revisions_site_id", table_name="site_config_revisions")
    op.drop_table("site_config_revisions")


# ── v1 backfill ──────────────────────────────────────────────────────
#
# A copy of the snapshot builder as it stood when this migration was
# written, using plain SQL, so later changes to the models or services
# can't change what this migration reads or produces. At the time of
# writing it builds exactly what ``src.services.config_snapshot`` does,
# so upgraded sites don't show unpublished changes straight away.

SNAPSHOT_FORMAT = 1

# The cascade fields each config table has.
SITE_FIELDS = (
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
    "disclosed_vendor_ids",
)
ORG_FIELDS = SITE_FIELDS
GROUP_FIELDS = (*SITE_FIELDS, "consent_sharing_enabled", "consent_bridge_url")

ALL_CATEGORIES = ["necessary", "functional", "analytics", "marketing", "personalisation"]

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
    "enabled_categories": ALL_CATEGORIES,
    "disclosed_vendor_ids": [],
}


def backfill_initial_revisions(conn: sa.engine.Connection) -> None:
    """Publish v1 for every site that has a config and no live revision.

    Deleted sites are skipped. Inactive sites are included so they keep
    their config if they are reactivated.
    """
    shared = {
        "gvl_version": conn.execute(
            sa.text("SELECT vendor_list_version FROM iab_gvl_meta LIMIT 1")
        ).scalar(),
        "category_tcf_purposes": {
            slug: ids
            for slug, ids in conn.execute(
                sa.text(
                    "SELECT slug, tcf_purpose_ids FROM cookie_categories "
                    "WHERE tcf_purpose_ids IS NOT NULL"
                )
            )
            if ids
        },
    }
    sites = conn.execute(
        sa.text(
            "SELECT s.id, s.organisation_id, g.id AS group_id, c.id AS config_id "
            "FROM sites s "
            "JOIN site_configs c ON c.site_id = s.id "
            "LEFT JOIN site_groups g "
            "  ON g.id = s.site_group_id AND g.organisation_id = s.organisation_id "
            "WHERE s.deleted_at IS NULL AND s.live_revision_id IS NULL"
        )
    ).all()
    for site in sites:
        _publish_v1(conn, site, shared)


def _publish_v1(conn: sa.engine.Connection, site: Any, shared: dict[str, Any]) -> None:
    site_values = _row(conn, "site_configs", SITE_FIELDS, "site_id", site.id) or {}
    org_defaults = _non_null(
        _row(conn, "org_configs", ORG_FIELDS, "organisation_id", site.organisation_id)
    )
    group_defaults = (
        _non_null(_row(conn, "site_group_configs", GROUP_FIELDS, "site_group_id", site.group_id))
        if site.group_id
        else None
    )

    resolved = dict(SYSTEM_DEFAULTS)
    for layer in (org_defaults, group_defaults, site_values):
        for key, value in (layer or {}).items():
            if value is not None:
                resolved[key] = value
    resolved["enabled_categories"] = _normalise_categories(resolved.get("enabled_categories"))
    if site.group_id and resolved.get("consent_sharing_enabled"):
        resolved["consent_group_id"] = str(site.group_id)

    translations = conn.execute(
        sa.text(
            "SELECT locale, strings FROM translations WHERE site_id = :site_id ORDER BY locale"
        ),
        {"site_id": site.id},
    ).all()
    snapshot = _to_json(
        {
            "format": SNAPSHOT_FORMAT,
            "config": resolved,
            "extensions": {},
            **shared,
            "cookie_count": conn.execute(
                sa.text("SELECT count(*) FROM cookie_allow_list WHERE site_id = :site_id"),
                {"site_id": site.id},
            ).scalar_one(),
            "translations": {locale.lower(): strings for locale, strings in translations},
            "cookies": [
                dict(row._mapping)
                for row in conn.execute(
                    sa.text(
                        "SELECT c.name, c.domain, c.storage_type AS type, "
                        "  coalesce(c.description, '') AS description, "
                        "  coalesce(c.vendor, '') AS vendor, cat.slug AS category "
                        "FROM cookies c "
                        "LEFT JOIN cookie_categories cat ON cat.id = c.category_id "
                        "WHERE c.site_id = :site_id AND c.review_status != 'rejected' "
                        "ORDER BY c.name, c.domain, c.storage_type"
                    ),
                    {"site_id": site.id},
                )
            ],
        }
    )
    site_layer = _to_json(
        {
            "format": SNAPSHOT_FORMAT,
            "site_config": site_values,
            "translations": dict(translations),
            "cookies": [
                dict(row._mapping)
                for row in conn.execute(
                    sa.text(
                        "SELECT id, category_id, review_status FROM cookies "
                        "WHERE site_id = :site_id ORDER BY id"
                    ),
                    {"site_id": site.id},
                )
            ],
            "allow_list": [
                dict(row._mapping)
                for row in conn.execute(
                    sa.text(
                        "SELECT category_id, name_pattern, domain_pattern, description "
                        "FROM cookie_allow_list WHERE site_id = :site_id "
                        "ORDER BY name_pattern, domain_pattern"
                    ),
                    {"site_id": site.id},
                )
            ],
        }
    )
    sources = [
        {
            "kind": "organisation_config",
            "id": str(site.organisation_id),
            "content_hash": _hash(org_defaults or {}),
        }
    ]
    if site.group_id:
        sources.append(
            {
                "kind": "site_group_config",
                "id": str(site.group_id),
                "content_hash": _hash(group_defaults or {}),
            }
        )

    # psycopg2 can't bind ``uuid.UUID`` values, so ids are passed as text.
    revision_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO site_config_revisions (id, site_id, number, consent_version, "
            "  requires_reconsent, snapshot, site_layer, sources, content_hash, note) "
            "VALUES (:id, :site_id, 1, :consent_version, false, CAST(:snapshot AS jsonb), "
            "  CAST(:site_layer AS jsonb), CAST(:sources AS jsonb), :content_hash, "
            "  'Initial revision')"
        ),
        {
            "id": revision_id,
            "site_id": str(site.id),
            "consent_version": str(site.config_id),
            "snapshot": json.dumps(snapshot),
            "site_layer": json.dumps(site_layer),
            "sources": json.dumps(_to_json(sources)),
            "content_hash": _hash(snapshot),
        },
    )
    conn.execute(
        sa.text("UPDATE sites SET live_revision_id = :revision_id WHERE id = :site_id"),
        {"revision_id": revision_id, "site_id": str(site.id)},
    )


def _row(
    conn: sa.engine.Connection, table: str, fields: tuple[str, ...], key: str, value: Any
) -> dict[str, Any] | None:
    row = conn.execute(
        sa.text(f"SELECT {', '.join(fields)} FROM {table} WHERE {key} = :value"),
        {"value": value},
    ).first()
    return dict(row._mapping) if row else None


def _non_null(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    return {key: value for key, value in values.items() if value is not None}


def _normalise_categories(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return list(ALL_CATEGORIES)
    picked = {slug for slug in value if isinstance(slug, str) and slug in ALL_CATEGORIES}
    picked.add("necessary")
    return [slug for slug in ALL_CATEGORIES if slug in picked]


def _hash(value: Any) -> str:
    canonical = json.dumps(_to_json(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
