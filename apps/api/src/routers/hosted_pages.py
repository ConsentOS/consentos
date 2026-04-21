"""Hosted cookie management page.

Serves a public HTML page at ``/c/<site_id>/cookies`` that lists all
discovered cookies for a site, grouped by category, and lets the
visitor review and change their consent preferences. Site owners link
to this page from their footer (e.g. "Cookie preferences").

The page is self-contained — no external JS or CSS dependencies. It
reads the ``_consentos_consent`` cookie to show the current state and
writes it back when the visitor saves.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.cookie import Cookie, CookieCategory
from src.models.site import Site
from src.models.site_config import SiteConfig

router = APIRouter(prefix="/c", tags=["hosted-pages"])


@router.get("/{site_id}/cookies", response_class=HTMLResponse)
async def hosted_cookies_page(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Public hosted cookie management page."""
    # Load site
    site_result = await db.execute(
        select(Site).where(Site.id == site_id, Site.deleted_at.is_(None))
    )
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    # Load site config for branding
    config_result = await db.execute(select(SiteConfig).where(SiteConfig.site_id == site_id))
    config = config_result.scalar_one_or_none()

    # Load categories
    cat_result = await db.execute(select(CookieCategory).order_by(CookieCategory.display_order))
    categories = {cat.id: cat for cat in cat_result.scalars().all()}

    # Load cookies for this site
    cookie_result = await db.execute(
        select(Cookie).where(Cookie.site_id == site_id).order_by(Cookie.name)
    )
    cookies = list(cookie_result.scalars().all())

    # Group cookies by category
    grouped: dict[str, list[dict]] = {}
    for cat in categories.values():
        grouped[cat.slug] = []

    grouped["uncategorised"] = []

    for cookie in cookies:
        cat = categories.get(cookie.category_id) if cookie.category_id else None
        slug = cat.slug if cat else "uncategorised"
        if slug not in grouped:
            grouped[slug] = []
        grouped[slug].append(
            {
                "name": cookie.name,
                "domain": cookie.domain,
                "type": cookie.storage_type,
                "description": cookie.description or "",
                "vendor": cookie.vendor or "",
            }
        )

    # Build the category sections HTML
    category_html = ""
    category_meta = []
    for cat in categories.values():
        items = grouped.get(cat.slug, [])
        is_necessary = cat.is_essential
        category_meta.append(
            {
                "slug": cat.slug,
                "name": cat.name,
                "locked": is_necessary,
            }
        )
        category_html += _render_category_section(
            cat.name,
            cat.slug,
            cat.description or "",
            items,
            is_necessary,
        )

    # Uncategorised
    if grouped.get("uncategorised"):
        category_html += _render_category_section(
            "Uncategorised",
            "uncategorised",
            "Cookies that have not yet been assigned to a category.",
            grouped["uncategorised"],
            False,
        )

    privacy_url = config.privacy_policy_url if config else None
    expiry_days = config.consent_expiry_days if config else 365

    return _render_page(
        site_name=site.display_name or site.domain,
        domain=site.domain,
        category_html=category_html,
        category_meta=category_meta,
        privacy_url=privacy_url,
        expiry_days=expiry_days,
    )


def _render_category_section(
    name: str,
    slug: str,
    description: str,
    cookies: list[dict],
    locked: bool,
) -> str:
    if locked:
        toggle = '<span style="color:#666;font-size:13px;">Always active</span>'
    else:
        toggle = f'''<div style="display:flex;gap:16px;margin-top:8px;">
            <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:14px;">
                <input type="radio" name="cat-{slug}" data-category="{slug}" value="on" />
                Use
            </label>
            <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:14px;">
                <input type="radio" name="cat-{slug}" data-category="{slug}" value="off" checked />
                Do not use
            </label>
        </div>'''

    cookie_rows = ""
    if cookies:
        cookie_rows = (
            '<table style="width:100%;border-collapse:collapse;margin-top:12px;font-size:13px;">'
        )
        cookie_rows += '<tr style="border-bottom:1px solid #e5e5e5;text-align:left;">'
        cookie_rows += '<th style="padding:6px 8px;">Name</th>'
        cookie_rows += '<th style="padding:6px 8px;">Domain</th>'
        cookie_rows += '<th style="padding:6px 8px;">Type</th>'
        cookie_rows += '<th style="padding:6px 8px;">Description</th>'
        cookie_rows += "</tr>"
        for c in cookies:
            cookie_rows += '<tr style="border-bottom:1px solid #f0f0f0;">'
            cookie_rows += f'<td style="padding:6px 8px;font-family:monospace;font-size:12px;">{_esc(c["name"])}</td>'
            cookie_rows += f'<td style="padding:6px 8px;">{_esc(c["domain"])}</td>'
            cookie_rows += f'<td style="padding:6px 8px;">{_esc(c["type"])}</td>'
            cookie_rows += f'<td style="padding:6px 8px;">{_esc(c["description"])}</td>'
            cookie_rows += "</tr>"
        cookie_rows += "</table>"
    else:
        cookie_rows = (
            '<p style="color:#888;font-size:13px;margin-top:8px;">No cookies in this category.</p>'
        )

    return f"""
    <div style="border:1px solid #e5e5e5;border-radius:8px;padding:20px;margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <h3 style="margin:0;font-size:16px;">{_esc(name)}</h3>
            {toggle}
        </div>
        <p style="color:#666;font-size:14px;margin:8px 0 0;">{_esc(description)}</p>
        {cookie_rows}
    </div>
    """


def _render_page(
    *,
    site_name: str,
    domain: str,
    category_html: str,
    category_meta: list[dict],
    privacy_url: str | None,
    expiry_days: int,
) -> str:
    import json

    meta_json = json.dumps(category_meta)

    privacy_link = ""
    if privacy_url:
        privacy_link = f'<p style="margin-top:16px;font-size:13px;">Read our <a href="{_esc(privacy_url)}" style="color:#2C6AE4;">privacy policy</a>.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cookie Preferences — {_esc(site_name)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; background: #fafafa; }}
        .container {{ max-width: 720px; margin: 0 auto; padding: 40px 20px; }}
        h1 {{ font-size: 28px; font-weight: 600; margin-bottom: 8px; }}
        .subtitle {{ color: #666; font-size: 15px; margin-bottom: 32px; }}
        .actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 24px; }}
        .btn {{ padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; border: none; }}
        .btn-primary {{ background: #1B3C7C; color: #fff; }}
        .btn-primary:hover {{ background: #152f62; }}
        .btn-secondary {{ background: #fff; color: #1a1a1a; border: 1px solid #d1d1d1; }}
        .btn-secondary:hover {{ background: #f5f5f5; }}
        .saved {{ display: none; color: #0a8a4a; font-size: 14px; padding: 10px 0; }}
        footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e5e5; font-size: 13px; color: #888; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Cookie Preferences</h1>
        <p class="subtitle">
            Manage your cookie preferences for {_esc(domain)}.
            You can change these settings at any time.
        </p>

        {category_html}

        <div class="actions">
            <button class="btn btn-primary" onclick="savePreferences()">Save preferences</button>
            <button class="btn btn-secondary" onclick="acceptAll()">Accept all</button>
            <button class="btn btn-secondary" onclick="rejectAll()">Reject all</button>
        </div>
        <p class="saved" id="saved-msg">Your preferences have been saved.</p>

        {privacy_link}

        <footer>
            Powered by <a href="https://consentos.dev" style="color:#888;">ConsentOS</a>
        </footer>
    </div>

    <script>
    (function() {{
        var COOKIE_NAME = '_consentos_consent';
        var EXPIRY_DAYS = {expiry_days};
        var CATEGORIES = {meta_json};

        function readConsent() {{
            var match = document.cookie.split('; ').find(function(r) {{
                return r.startsWith(COOKIE_NAME + '=');
            }});
            if (!match) return null;
            try {{ return JSON.parse(decodeURIComponent(match.split('=')[1])); }}
            catch(e) {{ return null; }}
        }}

        function writeConsent(accepted) {{
            var existing = readConsent();
            var state = {{
                visitorId: (existing && existing.visitorId) || crypto.randomUUID(),
                accepted: accepted,
                rejected: CATEGORIES.filter(function(c) {{ return !c.locked; }}).map(function(c) {{ return c.slug; }}).filter(function(s) {{ return accepted.indexOf(s) === -1; }}),
                consentedAt: new Date().toISOString(),
                bannerVersion: 'hosted-page'
            }};
            var value = encodeURIComponent(JSON.stringify(state));
            var expires = new Date(Date.now() + EXPIRY_DAYS * 86400000).toUTCString();
            var secure = location.protocol === 'https:' ? '; Secure' : '';
            document.cookie = COOKIE_NAME + '=' + value + '; path=/; expires=' + expires + '; SameSite=Lax' + secure;
        }}

        function prefill() {{
            var consent = readConsent();
            if (!consent) return;
            var accepted = consent.accepted || [];
            CATEGORIES.forEach(function(cat) {{
                if (cat.locked) return;
                var isOn = accepted.indexOf(cat.slug) !== -1;
                var radios = document.querySelectorAll('input[name="cat-' + cat.slug + '"]');
                radios.forEach(function(r) {{
                    r.checked = (r.value === 'on') === isOn;
                }});
            }});
        }}

        function getAccepted() {{
            var accepted = ['necessary'];
            CATEGORIES.forEach(function(cat) {{
                if (cat.locked) return;
                var on = document.querySelector('input[name="cat-' + cat.slug + '"][value="on"]');
                if (on && on.checked) accepted.push(cat.slug);
            }});
            return accepted;
        }}

        function showSaved() {{
            document.getElementById('saved-msg').style.display = 'block';
            setTimeout(function() {{ document.getElementById('saved-msg').style.display = 'none'; }}, 3000);
        }}

        window.savePreferences = function() {{
            writeConsent(getAccepted());
            showSaved();
        }};

        window.acceptAll = function() {{
            CATEGORIES.forEach(function(cat) {{
                if (cat.locked) return;
                var on = document.querySelector('input[name="cat-' + cat.slug + '"][value="on"]');
                if (on) on.checked = true;
            }});
            var all = ['necessary'];
            CATEGORIES.forEach(function(c) {{ if (!c.locked) all.push(c.slug); }});
            writeConsent(all);
            showSaved();
        }};

        window.rejectAll = function() {{
            CATEGORIES.forEach(function(cat) {{
                if (cat.locked) return;
                var off = document.querySelector('input[name="cat-' + cat.slug + '"][value="off"]');
                if (off) off.checked = true;
            }});
            writeConsent(['necessary']);
            showSaved();
        }};

        prefill();
    }})();
    </script>
</body>
</html>"""


def _esc(s: str) -> str:
    """Basic HTML escaping."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
