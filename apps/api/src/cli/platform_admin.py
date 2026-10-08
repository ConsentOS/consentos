"""Grant or revoke the platform admin flag on a user.

Usage:
    docker exec -it consentos-api python -m src.cli.platform_admin \\
        --email admin@example.com [--revoke] [--yes]

Platform admins can edit the shared known cookies list, which applies to
every organisation on the instance. The flag cannot be set through the
API, so it is managed here by whoever operates the deployment. The
matched user and their organisation are shown, and the change must be
confirmed unless ``--yes`` is given.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass

import sqlalchemy as sa


@dataclass(frozen=True)
class UserSummary:
    id: uuid.UUID
    email: str
    full_name: str
    organisation_name: str
    is_superuser: bool


def _build_sync_url(async_url: str) -> str:
    """Convert an asyncpg DSN to a psycopg2 DSN for one-off scripts."""
    return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def _engine() -> sa.Engine:
    from src.config.settings import get_settings

    return sa.create_engine(_build_sync_url(get_settings().database_url))


def find_user(email: str) -> UserSummary | None:
    """Return the active user with this email, with their organisation's name."""
    with _engine().connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT u.id, u.email, u.full_name, o.name, u.is_superuser "
                "FROM users u JOIN organisations o ON o.id = u.organisation_id "
                "WHERE u.email = :email AND u.deleted_at IS NULL"
            ),
            {"email": email},
        ).one_or_none()
    return UserSummary(*row) if row else None


def set_platform_admin(user_id: uuid.UUID, *, enabled: bool) -> bool:
    """Set the flag on one user. Returns False if the user no longer exists."""
    with _engine().begin() as conn:
        result = conn.execute(
            sa.text(
                "UPDATE users SET is_superuser = :enabled, updated_at = NOW() "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"enabled": enabled, "id": user_id},
        )
    return result.rowcount > 0


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke platform admin")
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--revoke", action="store_true", help="Remove the flag instead")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args(argv)

    enabled = not args.revoke
    user = find_user(args.email)
    if user is None:
        print(f"Error: no active user found with email {args.email}", file=sys.stderr)
        sys.exit(1)

    print(f"User:           {user.full_name} <{user.email}>")
    print(f"Organisation:   {user.organisation_name}")
    print(f"Platform admin: {'yes' if user.is_superuser else 'no'}")

    if user.is_superuser == enabled:
        print("No change needed.")
        return

    verb = "Grant platform admin to" if enabled else "Revoke platform admin from"
    if not args.yes and not _confirm(f"{verb} this user? [y/N] "):
        print("Aborted.", file=sys.stderr)
        sys.exit(1)

    if not set_platform_admin(user.id, enabled=enabled):
        print(f"Error: user {args.email} no longer exists", file=sys.stderr)
        sys.exit(1)

    action = "granted to" if enabled else "revoked from"
    print(f"Platform admin {action} {user.email}")


if __name__ == "__main__":
    main()
