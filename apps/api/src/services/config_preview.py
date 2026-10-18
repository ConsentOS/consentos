"""Signed, short-lived links that show a site's draft config on the real site.

The token is the only key: whoever holds it sees the draft for that one
site until it expires. It is a separate token type from sign-in tokens,
so neither can be used as the other.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from src.config.settings import get_settings

PREVIEW_TOKEN_TYPE = "config_preview"
PREVIEW_LIFETIME = timedelta(minutes=30)


def create_preview_token(site_id: uuid.UUID) -> tuple[str, datetime]:
    """A token that previews ``site_id``'s draft, and when it expires."""
    settings = get_settings()
    expires_at = datetime.now(UTC) + PREVIEW_LIFETIME
    payload = {"type": PREVIEW_TOKEN_TYPE, "site_id": str(site_id), "exp": expires_at}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def preview_site_id(token: str) -> uuid.UUID | None:
    """The site a valid preview token is for, or ``None`` if it isn't valid."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != PREVIEW_TOKEN_TYPE:
            return None
        return uuid.UUID(payload["site_id"])
    except (JWTError, KeyError, ValueError):
        return None
