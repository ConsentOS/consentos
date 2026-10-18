/**
 * Fetch the site's published config, falling back to built-in defaults.
 */

import type { SiteConfig } from './types';

/**
 * Load the live config for this visitor's region and locale.
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
  try {
    const resp = await fetch(
      `${apiBase}/api/v1/config/sites/${siteId}/geo-resolved?locale=${encodeURIComponent(locale)}`,
    );
    if (resp.status === 404) {
      console.info(
        '[ConsentOS] This site has not been published yet, so the built-in defaults are in use.',
      );
      return fallback();
    }
    if (!resp.ok) throw new Error(`Config fetch failed: ${resp.status}`);
    return (await resp.json()) as SiteConfig;
  } catch (err) {
    console.error('[ConsentOS] Failed to load site config:', err);
    return fallback();
  }
}
