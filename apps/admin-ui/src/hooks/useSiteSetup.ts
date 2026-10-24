import { useQuery } from '@tanstack/react-query';

import { getSiteSetup } from '../api/setup';
import type { SiteSetup } from '../types/api';
import { useRefreshOnSave } from './useRefreshOnSave';

/** How often to look again while the scan is running. */
export const SETUP_SCAN_POLL_INTERVAL_MS = 3000;
/**
 * How often to look again otherwise, until setup is complete, so a
 * banner detected on the site shows up without a reload.
 */
export const SETUP_POLL_INTERVAL_MS = 30_000;

export function setupQueryKey(siteId: string): string[] {
  return ['sites', siteId, 'setup'];
}

export function setupPollInterval(setup: SiteSetup | undefined): number | false {
  if (!setup || setup.dismissed || setup.complete) return false;
  return setup.steps.some((s) => s.status === 'in_progress')
    ? SETUP_SCAN_POLL_INTERVAL_MS
    : SETUP_POLL_INTERVAL_MS;
}

/** The site's setup checklist, kept up to date while it is in use. */
export function useSiteSetup(siteId: string) {
  useRefreshOnSave(setupQueryKey(siteId));
  return useQuery({
    queryKey: setupQueryKey(siteId),
    queryFn: () => getSiteSetup(siteId),
    refetchInterval: (query) => setupPollInterval(query.state.data),
  });
}
