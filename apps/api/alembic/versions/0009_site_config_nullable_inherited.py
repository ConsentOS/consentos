"""make inheritable site_configs columns nullable

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-08

The admin UI's "Reset to inherited" button sends ``null`` for the
field being reset so the cascade (group → org → system) can supply
the value. Several columns on ``site_configs`` were ``NOT NULL`` with
defaults, which made the PATCH fail at the DB layer. This migration
drops ``NOT NULL`` from the affected columns; ``server_default`` is
preserved so newly-inserted rows still get a sensible value when the
caller doesn't supply one.

Existing rows are unaffected — their explicit values stay in place;
operators reset them per-field via the admin UI as needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Each tuple: (column, type, server_default-or-None)
_COLUMNS: list[tuple[str, sa.types.TypeEngine, str | None]] = [
    ("blocking_mode", sa.String(20), "opt_in"),
    ("tcf_enabled", sa.Boolean(), "false"),
    ("gpp_enabled", sa.Boolean(), "true"),
    ("gpc_enabled", sa.Boolean(), "true"),
    ("gpc_global_honour", sa.Boolean(), "false"),
    ("gcm_enabled", sa.Boolean(), "true"),
    ("shopify_privacy_enabled", sa.Boolean(), "false"),
    ("display_mode", sa.String(30), "bottom_banner"),
    ("scan_max_pages", sa.Integer(), "50"),
    ("consent_expiry_days", sa.Integer(), "365"),
]


def upgrade() -> None:
    for name, type_, _ in _COLUMNS:
        op.alter_column(
            "site_configs",
            name,
            existing_type=type_,
            nullable=True,
        )


def downgrade() -> None:
    # Re-imposing NOT NULL would fail if any rows have been NULLed via
    # the reset flow; backfill those to their server defaults first.
    for name, _, default in _COLUMNS:
        if default is not None:
            op.execute(
                f"UPDATE site_configs SET {name} = '{default}' WHERE {name} IS NULL"
                if isinstance(default, str)
                and not default.lstrip("-").isdigit()
                and default not in ("true", "false")
                else f"UPDATE site_configs SET {name} = {default} WHERE {name} IS NULL"
            )
    for name, type_, _ in _COLUMNS:
        op.alter_column(
            "site_configs",
            name,
            existing_type=type_,
            nullable=False,
        )
