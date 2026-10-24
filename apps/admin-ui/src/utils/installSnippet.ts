import type { SiteInstall } from '../types/api';

export interface InstallUrls {
  apiBase: string;
  cdnBase: string;
}

/**
 * Where the snippet should point, falling back to the admin UI's own
 * address for anything the deployment hasn't configured.
 */
export function resolveInstallUrls(install: SiteInstall | undefined, ownOrigin: string): InstallUrls {
  return {
    apiBase: install?.api_base ?? ownOrigin,
    cdnBase: install?.cdn_base ?? ownOrigin,
  };
}

/**
 * The script tag a site pastes into its pages.
 *
 * The loader fetches the rest of the banner from ``data-cdn-base``,
 * which defaults to the API address, so it is only included when the
 * banner is served from somewhere else.
 */
export function installSnippet(siteId: string, { apiBase, cdnBase }: InstallUrls): string {
  const cdnAttribute = cdnBase === apiBase ? '' : ` data-cdn-base="${cdnBase}"`;
  return `<script src="${cdnBase}/consent-loader.js" data-site-id="${siteId}" data-api-base="${apiBase}"${cdnAttribute}></script>`;
}
