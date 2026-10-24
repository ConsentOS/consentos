import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { listScans } from '../api/scanner';
import type { ScanJob } from '../types/api';

/** How often to re-check a site's scans while one is in progress. */
export const SCAN_POLL_INTERVAL_MS = 3000;

export function isScanActive(scan: ScanJob): boolean {
  return scan.status === 'pending' || scan.status === 'running';
}

/** The poll interval for a site's scans: only while one is in progress. */
export function scanPollInterval(scans: ScanJob[] | undefined): number | false {
  return scans?.some(isScanActive) ? SCAN_POLL_INTERVAL_MS : false;
}

/**
 * A site's scans, kept up to date while any of them is running.
 *
 * When a scan finishes, the cookie list and the draft are refreshed,
 * because the scan adds what it found to the site's cookies.
 */
export function useSiteScans(siteId: string) {
  const queryClient = useQueryClient();
  const query = useQuery<ScanJob[]>({
    queryKey: ['scans', siteId],
    queryFn: () => listScans(siteId),
    refetchInterval: (q) => scanPollInterval(q.state.data),
  });

  const activeIds = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!query.data) return;
    const nowActive = new Set(query.data.filter(isScanActive).map((s) => s.id));
    const previous = activeIds.current;
    activeIds.current = nowActive;
    if (previous && [...previous].some((id) => !nowActive.has(id))) {
      queryClient.invalidateQueries({ queryKey: ['cookies', siteId] });
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'draft'] });
    }
  }, [query.data, queryClient, siteId]);

  return query;
}
