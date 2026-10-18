/**
 * Fetch the site's published config, falling back to built-in defaults.
 */

import type { SiteConfig } from './types';

const PREVIEW_PARAM = 'consentos_preview';
const PREVIEW_STORAGE_KEY = 'consentos_preview';

/**
 * The draft preview token for this tab, if one is in use.
 *
 * A ``?consentos_preview=<token>`` link starts a preview, which then
 * lasts for the tab's session as the holder browses the site.
 * ``?consentos_preview=off`` ends it.
 */
export function previewToken(): string | null {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get(PREVIEW_PARAM);
    if (fromUrl === 'off') {
      sessionStorage.removeItem(PREVIEW_STORAGE_KEY);
      return null;
    }
    if (fromUrl) {
      sessionStorage.setItem(PREVIEW_STORAGE_KEY, fromUrl);
      return fromUrl;
    }
    return sessionStorage.getItem(PREVIEW_STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode, blocked site data).
    return null;
  }
}

function endPreview(): void {
  try {
    sessionStorage.removeItem(PREVIEW_STORAGE_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
}

/**
 * Load the live config for this visitor's region and locale.
 *
 * With a preview token the API returns the draft instead, marked
 * ``preview``. If it doesn't (the link expired), the preview ends and
 * the live config is used.
 *
 * A 404 means the site hasn't been published yet, which is expected for
 * a new site, so it's reported as information rather than an error. Any
 * other failure is logged as an error. Either way the banner carries on
 * with ``fallback()``.
 */
export async function fetchSiteConfig(
  apiBase: string,
  siteId: string,
  locale: string,
  fallback: () => SiteConfig,
): Promise<SiteConfig> {
  const token = previewToken();
  const preview = token ? `&preview=${encodeURIComponent(token)}` : '';
  try {
    const resp = await fetch(
      `${apiBase}/api/v1/config/sites/${siteId}/geo-resolved?locale=${encodeURIComponent(locale)}${preview}`,
    );
    if (resp.status === 404) {
      if (token) endPreview();
      console.info(
        '[ConsentOS] This site has not been published yet, so the built-in defaults are in use.',
      );
      return fallback();
    }
    if (!resp.ok) throw new Error(`Config fetch failed: ${resp.status}`);
    const config = (await resp.json()) as SiteConfig;
    if (config.preview) {
      console.info('[ConsentOS] Previewing unpublished changes. Nothing is saved as consent.');
    } else if (token) {
      endPreview();
    }
    return config;
  } catch (err) {
    console.error('[ConsentOS] Failed to load site config:', err);
    return fallback();
  }
}
