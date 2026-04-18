import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Fragment, useState } from 'react';

import { getScan, getScanDiff, listScans, triggerScan } from '../api/scanner';
import { getSiteConfig, updateSiteConfig } from '../api/sites';
import { trackFeatureUsage } from '../services/analytics';
import type { CookieDiffItem, ScanDiff, ScanJob, ScanJobDetail, ScanResult, SiteConfig } from '../types/api';
import { Alert } from './ui/alert';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { LoadingState } from './ui/loading-state';
import { Select } from './ui/select';

interface Props {
  siteId: string;
}

const SCHEDULE_OPTIONS: { value: string; label: string; cron: string | null }[] = [
  { value: 'disabled', label: 'Disabled', cron: null },
  { value: 'daily', label: 'Daily', cron: '0 3 * * *' },
  { value: 'weekly', label: 'Weekly', cron: '0 3 * * 0' },
  { value: 'fortnightly', label: 'Fortnightly', cron: '0 3 1,15 * *' },
  { value: 'monthly', label: 'Monthly', cron: '0 3 1 * *' },
];

function cronToScheduleValue(cron: string | null | undefined): string {
  if (!cron) return 'disabled';
  const match = SCHEDULE_OPTIONS.find((o) => o.cron === cron);
  return match?.value ?? 'custom';
}

function statusVariant(status: string): 'warning' | 'info' | 'success' | 'error' | 'neutral' {
  const map: Record<string, 'warning' | 'info' | 'success' | 'error'> = {
    pending: 'warning',
    running: 'info',
    completed: 'success',
    failed: 'error',
  };
  return map[status] ?? 'neutral';
}

function diffVariant(status: string): 'success' | 'error' | 'warning' | 'neutral' {
  const map: Record<string, 'success' | 'error' | 'warning'> = {
    new: 'success',
    removed: 'error',
    changed: 'warning',
  };
  return map[status] ?? 'neutral';
}

function DiffSection({ title, items }: { title: string; items: CookieDiffItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium text-text-secondary">{title} ({items.length})</h4>
      <div className="mt-2 overflow-hidden rounded-md border border-border">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-background">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Name</th>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Domain</th>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Type</th>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Status</th>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((item, idx) => (
              <tr key={`${item.name}-${item.domain}-${idx}`}>
                <td className="px-3 py-2 font-mono text-xs">{item.name}</td>
                <td className="px-3 py-2 text-text-secondary">{item.domain}</td>
                <td className="px-3 py-2 text-text-secondary">{item.storage_type}</td>
                <td className="px-3 py-2"><Badge variant={diffVariant(item.diff_status)}>{item.diff_status}</Badge></td>
                <td className="px-3 py-2 text-text-secondary">{item.details ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScanDiffView({ scanId }: { scanId: string }) {
  const { data: diff, isLoading } = useQuery<ScanDiff>({
    queryKey: ['scans', scanId, 'diff'],
    queryFn: () => getScanDiff(scanId),
  });

  if (isLoading) return <LoadingState message="Loading diff..." className="py-2" />;
  if (!diff) return null;

  const hasChanges = diff.total_new + diff.total_removed + diff.total_changed > 0;

  return (
    <div className="mt-3 rounded-md border border-border bg-background p-4">
      <h3 className="font-heading text-sm font-semibold text-foreground">
        Scan Diff
        {diff.previous_scan_id ? '' : ' (first scan — no comparison available)'}
      </h3>
      {hasChanges ? (
        <>
          <DiffSection title="New Cookies" items={diff.new_cookies} />
          <DiffSection title="Removed Cookies" items={diff.removed_cookies} />
          <DiffSection title="Changed Cookies" items={diff.changed_cookies} />
        </>
      ) : (
        <p className="mt-2 text-sm text-text-secondary">No changes detected.</p>
      )}
    </div>
  );
}

function InitiatorChain({ chain }: { chain: string[] }) {
  if (chain.length === 0) return <span className="text-text-tertiary">—</span>;

  return (
    <div className="flex flex-wrap items-center gap-1 text-xs">
      {chain.map((url, idx) => {
        // Show just the pathname for brevity
        let label: string;
        try {
          const parsed = new URL(url);
          label = parsed.pathname.length > 40
            ? '…' + parsed.pathname.slice(-38)
            : parsed.pathname;
        } catch {
          label = url.length > 40 ? '…' + url.slice(-38) : url;
        }
        return (
          <span key={idx} className="flex items-center gap-1">
            {idx > 0 && <span className="text-text-tertiary">→</span>}
            <span
              className="rounded bg-mist px-1.5 py-0.5 font-mono text-text-secondary"
              title={url}
            >
              {label}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function ScanResultsView({ scanId }: { scanId: string }) {
  const { data: detail, isLoading } = useQuery<ScanJobDetail>({
    queryKey: ['scans', scanId, 'detail'],
    queryFn: () => getScan(scanId),
  });

  if (isLoading) return <LoadingState message="Loading results..." className="py-2" />;
  if (!detail || detail.results.length === 0) {
    return <p className="py-2 text-sm text-text-secondary">No results recorded.</p>;
  }

  // Only show results that have an initiator chain
  const withChain = detail.results.filter(
    (r: ScanResult) => r.initiator_chain && r.initiator_chain.length > 1,
  );

  if (withChain.length === 0) {
    return <p className="py-2 text-sm text-text-secondary">No initiator chains detected in this scan.</p>;
  }

  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium text-text-secondary">
        Initiator Chains ({withChain.length} cookies)
      </h4>
      <div className="mt-2 overflow-hidden rounded-md border border-border">
        <table className="min-w-full divide-y divide-border text-sm">
          <thead className="bg-background">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Cookie</th>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Domain</th>
              <th className="px-3 py-2 text-left font-medium text-text-secondary">Chain</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {withChain.map((r: ScanResult) => (
              <tr key={r.id}>
                <td className="px-3 py-2 font-mono text-xs">{r.cookie_name}</td>
                <td className="px-3 py-2 text-text-secondary">{r.cookie_domain}</td>
                <td className="px-3 py-2">
                  <InitiatorChain chain={r.initiator_chain!} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SiteScannerTab({ siteId }: Props) {
  const queryClient = useQueryClient();
  const [expandedScanId, setExpandedScanId] = useState<string | null>(null);

  const { data: config } = useQuery<SiteConfig>({
    queryKey: ['sites', siteId, 'config'],
    queryFn: () => getSiteConfig(siteId),
  });

  const currentCron = config?.scan_schedule_cron ?? null;
  const savedValue = cronToScheduleValue(currentCron);
  const [selectedSchedule, setSelectedSchedule] = useState<string | null>(null);
  const [customCron, setCustomCron] = useState('');

  // Use local selection if the user has interacted, otherwise fall
  // back to what's saved on the server.
  const activeValue = selectedSchedule ?? savedValue;
  const showCustomInput = activeValue === 'custom';

  const scheduleMutation = useMutation({
    mutationFn: (cron: string | null) => updateSiteConfig(siteId, { scan_schedule_cron: cron } as Partial<SiteConfig>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'config'] });
      trackFeatureUsage('scan', 'schedule_change', { site_id: siteId });
      setSelectedSchedule(null); // reset to server state
    },
  });

  const handleScheduleChange = (value: string) => {
    setSelectedSchedule(value);
    if (value === 'custom') {
      setCustomCron(currentCron ?? '');
      return;
    }
    const option = SCHEDULE_OPTIONS.find((o) => o.value === value);
    scheduleMutation.mutate(option?.cron ?? null);
  };

  const handleCustomSave = () => {
    const trimmed = customCron.trim();
    scheduleMutation.mutate(trimmed || null);
  };

  const { data: scans, isLoading } = useQuery<ScanJob[]>({
    queryKey: ['scans', siteId],
    queryFn: () => listScans(siteId),
  });

  const triggerMutation = useMutation({
    mutationFn: () => triggerScan(siteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scans', siteId] });
      trackFeatureUsage('scan', 'trigger', { site_id: siteId });
    },
  });

  if (isLoading) {
    return <LoadingState message="Loading scans..." />;
  }

  return (
    <div>
      {/* Scan schedule */}
      <Card className="mb-6 p-5">
        <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">Scan Schedule</h3>
        <p className="mb-3 text-xs text-text-secondary">
          Scheduled scans run automatically and re-discover cookies so your inventory stays
          current. Select a preset or enter a custom cron expression.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[180px]">
            <Select
              value={activeValue}
              onChange={(e) => handleScheduleChange(e.target.value)}
              disabled={scheduleMutation.isPending}
            >
              {SCHEDULE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
              <option value="custom">Custom cron</option>
            </Select>
          </div>
          {showCustomInput && (
            <>
              <input
                type="text"
                className="rounded-md border border-border bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-text-tertiary focus:border-copper focus:outline-none"
                placeholder="0 3 * * 0"
                value={customCron}
                onChange={(e) => setCustomCron(e.target.value)}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCustomSave}
                disabled={scheduleMutation.isPending || !customCron.trim()}
              >
                Save
              </Button>
              <a
                href="https://crontab.guru"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-copper hover:underline"
              >
                Need help? Use crontab.guru &rarr;
              </a>
            </>
          )}
          {scheduleMutation.isPending && (
            <span className="text-xs text-text-secondary">Saving…</span>
          )}
        </div>
        {currentCron && (
          <p className="mt-2 text-xs text-text-secondary">
            Current schedule: <code className="rounded bg-mist px-1.5 py-0.5 font-mono">{currentCron}</code>
          </p>
        )}
      </Card>

      {/* Header with trigger button */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-heading text-lg font-semibold text-foreground">Cookie Scans</h2>
        <Button
          onClick={() => triggerMutation.mutate()}
          disabled={triggerMutation.isPending}
        >
          {triggerMutation.isPending ? 'Triggering...' : 'Trigger Scan'}
        </Button>
      </div>

      {triggerMutation.isError && (
        <Alert variant="error" className="mb-4">
          Failed to trigger scan. A scan may already be in progress.
        </Alert>
      )}

      {/* Scan history */}
      {!scans || scans.length === 0 ? (
        <div className="py-8 text-center text-sm text-text-secondary">
          No scans yet. Trigger a scan to discover cookies on your site.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="bg-background">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-text-secondary">Status</th>
                <th className="px-4 py-3 text-left font-medium text-text-secondary">Trigger</th>
                <th className="px-4 py-3 text-left font-medium text-text-secondary">Pages</th>
                <th className="px-4 py-3 text-left font-medium text-text-secondary">Cookies Found</th>
                <th className="px-4 py-3 text-left font-medium text-text-secondary">Started</th>
                <th className="px-4 py-3 text-left font-medium text-text-secondary">Completed</th>
                <th className="px-4 py-3 text-left font-medium text-text-secondary">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {scans.map((scan) => (
                <Fragment key={scan.id}>
                  <tr className="hover:bg-mist">
                    <td className="px-4 py-3"><Badge variant={statusVariant(scan.status)}>{scan.status}</Badge></td>
                    <td className="px-4 py-3 text-text-secondary">{scan.trigger}</td>
                    <td className="px-4 py-3 text-text-secondary">
                      {scan.pages_scanned}{scan.pages_total ? ` / ${scan.pages_total}` : ''}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{scan.cookies_found}</td>
                    <td className="px-4 py-3 text-text-secondary">
                      {scan.started_at ? new Date(scan.started_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {scan.completed_at ? new Date(scan.completed_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {scan.status === 'completed' && (
                        <button
                          onClick={() => setExpandedScanId(expandedScanId === scan.id ? null : scan.id)}
                          className="text-copper hover:text-copper/80 text-xs font-medium"
                        >
                          {expandedScanId === scan.id ? 'Hide Diff' : 'View Diff'}
                        </button>
                      )}
                      {scan.status === 'failed' && scan.error_message && (
                        <span className="text-xs text-status-error-fg" title={scan.error_message}>
                          Error
                        </span>
                      )}
                    </td>
                  </tr>
                  {expandedScanId === scan.id && (
                    <tr key={`${scan.id}-diff`}>
                      <td colSpan={7} className="px-4 py-2">
                        <ScanDiffView scanId={scan.id} />
                        <ScanResultsView scanId={scan.id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
