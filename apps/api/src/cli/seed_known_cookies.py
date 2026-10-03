"""Seed the known_cookies table from the Open Cookie Database CSV.

Usage:
    python -m src.cli.seed_known_cookies [--csv PATH] [--clear]

The Open Cookie Database is a community-maintained catalogue of ~2,200+
cookie patterns.  See https://github.com/jkwakman/Open-Cookie-Database
"""

from __future__ import annotations

import argparse
import csv
import sys
import uuid
from pathlib import Path

import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Category mapping: Open Cookie Database category → CMP slug
# ---------------------------------------------------------------------------
_CATEGORY_MAP: dict[str, str] = {
    "Functional": "functional",
    "Analytics": "analytics",
    "Marketing": "marketing",
    "Personalization": "personalisation",
    "Security": "necessary",
}

_DEFAULT_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "open-cookie-database.csv"


def _build_sync_url(async_url: str) -> str:
    """Convert an asyncpg DSN to a psycopg2 DSN for one-off scripts."""
    return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def seed(csv_path: Path, *, clear: bool = False) -> int:
    """Read the CSV and upsert rows into known_cookies.

    Returns the number of rows inserted.
    """
    from src.config.settings import get_settings

    settings = get_settings()
    engine = sa.create_engine(_build_sync_url(settings.database_url))

    with engine.begin() as conn:
        # Build slug → category_id lookup
        rows = conn.execute(sa.text("SELECT id, slug FROM cookie_categories"))
        slug_to_id: dict[str, str] = {r[1]: str(r[0]) for r in rows}

        if clear:
            conn.execute(sa.text("DELETE FROM known_cookies"))

        inserted = 0
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                category = row.get("Category", "").strip()
                slug = _CATEGORY_MAP.get(category)
                if not slug or slug not in slug_to_id:
                    continue

                name = row.get("Cookie / Data Key name", "").strip()
                if not name:
                    continue

                domain_raw = row.get("Domain", "").strip()
                domain = domain_raw if domain_raw else "*"

                wildcard = row.get("Wildcard match", "0").strip() == "1"
                description = row.get("Description", "").strip() or None
                vendor = row.get("Platform", "").strip() or None

                # Build pattern: if wildcard, append * to name for glob matching
                name_pattern = f"{name}*" if wildcard else name
                is_regex = False

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO known_cookies
                            (id, name_pattern, domain_pattern, category_id,
                             vendor, description, is_regex, created_at, updated_at)
                        VALUES
                            (:id, :name_pattern, :domain_pattern, :category_id,
                             :vendor, :description, :is_regex, NOW(), NOW())
                        ON CONFLICT (name_pattern, domain_pattern) DO UPDATE SET
                            category_id = EXCLUDED.category_id,
                            vendor      = EXCLUDED.vendor,
                            description = EXCLUDED.description,
                            is_regex    = EXCLUDED.is_regex,
                            updated_at  = NOW()
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "name_pattern": name_pattern,
                        "domain_pattern": domain,
                        "category_id": slug_to_id[slug],
                        "vendor": vendor,
                        "description": description,
                        "is_regex": is_regex,
                    },
                )
                inserted += 1

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed known cookies from Open Cookie Database")
    parser.add_argument(
        "--csv",
        type=Path,
        default=_DEFAULT_CSV,
        help="Path to the Open Cookie Database CSV (default: bundled copy)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all existing known_cookies before importing",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: CSV not found at {args.csv}", file=sys.stderr)
        sys.exit(1)

    count = seed(args.csv, clear=args.clear)
    print(f"Seeded {count} known cookie patterns from {args.csv.name}")


if __name__ == "__main__":
    main()
