"""Hosted cookie management page.

Serves a tiny HTML stub at ``/c/<site_id>/cookies`` that loads the
ConsentOS banner bundle and lets it render the cookies-management
widget client-side. The actual UI is built by the bundle's
``window.ConsentOS.renderCookies`` flow, fetching data from
``/api/v1/config/sites/{site_id}/cookies``.

Replaces the previous server-rendered HTML page which was hard to
brand and shipped categories the site had disabled. Site owners can
also embed the widget on their own page by adding a script tag plus
``<div data-consentos-cookies></div>``; this page is a turnkey
fallback for sites that don't want to host one themselves.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site import Site

router = APIRouter(prefix="/c", tags=["hosted-pages"])


@router.get("/{site_id}/cookies", response_class=HTMLResponse)
async def hosted_cookies_page(
    site_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Public hosted cookie management page."""
    site_result = await db.execute(
        select(Site).where(Site.id == site_id, Site.deleted_at.is_(None))
    )
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    site_name = site.display_name or site.domain
    api_base = str(request.base_url).rstrip("/")

    return _render_stub(site_id=site_id, site_name=site_name, api_base=api_base)


def _render_stub(*, site_id: uuid.UUID, site_name: str, api_base: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cookie Preferences — {_esc(site_name)}</title>
    <style>
        body {{
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #0E1929;
            background: #FFFFFF;
            line-height: 1.6;
        }}
        main {{ max-width: 720px; margin: 0 auto; padding: 40px 20px; }}
        footer {{ max-width: 720px; margin: 32px auto 48px; padding: 0 20px; color: #5A6E96; font-size: 13px; }}
        footer a {{ color: inherit; }}
    </style>
    <script
        src="/consent-loader.js"
        data-site-id="{site_id}"
        data-api-base="{_esc(api_base)}"
        async></script>
</head>
<body>
    <main>
        <div data-consentos-cookies></div>
    </main>
    <footer>
        Powered by <a href="https://www.consentos.dev">ConsentOS</a>
    </footer>
</body>
</html>"""


def _esc(s: str) -> str:
    """Basic HTML escaping."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
