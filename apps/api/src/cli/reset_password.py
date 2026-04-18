"""Reset a user's password from the command line.

Usage:
    docker exec consentos-api python -m src.cli.reset_password \\
        --email admin@example.com --password new-secret

For use when the password has been forgotten and the admin UI is
inaccessible. Connects directly to the database, so it must run
inside a container (or host) that can reach PostgreSQL.
"""

from __future__ import annotations

import argparse
import sys

import sqlalchemy as sa


def _build_sync_url(async_url: str) -> str:
    return async_url.replace("postgresql+asyncpg://", "postgresql://")


def reset(email: str, password: str) -> bool:
    """Reset the password for the given email. Returns True on success."""
    from src.config.settings import get_settings
    from src.services.auth import hash_password

    settings = get_settings()
    engine = sa.create_engine(_build_sync_url(settings.database_url))

    with engine.begin() as conn:
        result = conn.execute(
            sa.text("SELECT id FROM users WHERE email = :email AND deleted_at IS NULL"),
            {"email": email},
        )
        row = result.fetchone()
        if row is None:
            return False

        conn.execute(
            sa.text("UPDATE users SET password_hash = :pw, updated_at = NOW() WHERE id = :id"),
            {"pw": hash_password(password), "id": str(row[0])},
        )

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset a user's password")
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--password", required=True, help="New password")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("Error: password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    if reset(args.email, args.password):
        print(f"Password reset for {args.email}")
    else:
        print(f"Error: no active user found with email {args.email}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
