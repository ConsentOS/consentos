import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { checkInstallation, getInstallation } from '../api/installation';
import { apiErrorMessage } from '../api/revisions';
import { useAuthStore } from '../stores/auth';
import type { Installation, InstallationCheckItem, InstallationState } from '../types/api';
import { canEdit } from './permissions';
import { Alert } from './ui/alert';
import { Badge } from './ui/badge';
import { Button } from './ui/button';

/** How often to look again while the banner hasn't been seen. */
export const INSTALLATION_POLL_INTERVAL_MS = 30_000;

const STATE_BADGES: Record<InstallationState, { label: string; variant: 'neutral' | 'success' | 'error' }> = {
  not_detected: { label: 'Not detected', variant: 'neutral' },
  installed: { label: 'Installed', variant: 'success' },
  problem: { label: 'Problem found', variant: 'error' },
};

export function InstallationBadge({ state }: { state: InstallationState }) {
  const { label, variant } = STATE_BADGES[state];
  return <Badge variant={variant}>{label}</Badge>;
}

interface Props {
  siteId: string;
}

/** Whether the banner is on the site, with a check that explains any problem. */
export default function InstallationStatus({ siteId }: Props) {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const queryKey = ['sites', siteId, 'installation'];

  const { data: installation } = useQuery({
    queryKey,
    queryFn: () => getInstallation(siteId),
    refetchInterval: (query) =>
      query.state.data?.state === 'installed' ? false : INSTALLATION_POLL_INTERVAL_MS,
  });

  const check = useMutation({
    mutationFn: () => checkInstallation(siteId),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKey, result);
      queryClient.invalidateQueries({ queryKey: ['installations'] });
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          {installation && <InstallationBadge state={installation.state} />}
          <p className="text-sm text-text-secondary">{summary(installation)}</p>
        </div>
        {canEdit(user) ? (
          <Button variant="secondary" onClick={() => check.mutate()} disabled={check.isPending}>
            {check.isPending ? 'Checking…' : 'Check now'}
          </Button>
        ) : (
          <p className="text-xs text-text-tertiary">Editors, admins and owners can run a check.</p>
        )}
      </div>

      {check.isPending && (
        <p className="text-sm text-text-secondary" role="status">
          Loading your home page as a new visitor. This can take up to a minute.
        </p>
      )}
      {check.isError && (
        <Alert variant="error">{apiErrorMessage(check.error, "The check couldn't run.")}</Alert>
      )}

      {installation?.last_check && !check.isPending && (
        <div>
          <p className="mb-2 text-xs text-text-secondary">
            Checked {installation.last_check.url} on{' '}
            {new Date(installation.last_check.checked_at).toLocaleString()}
          </p>
          <ul className="space-y-2">
            {installation.last_check.checks.map((item) => (
              <CheckRow key={item.key} item={item} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function summary(installation: Installation | undefined): string {
  if (!installation) return '';
  if (installation.last_seen_at) {
    const when = new Date(installation.last_seen_at).toLocaleString();
    return `Last seen ${when}${installation.last_seen_url ? ` on ${installation.last_seen_url}` : ''}.`;
  }
  return "We haven't seen the banner on your site yet. It's detected automatically the first time a page with it loads, or you can check now.";
}

const MARKS = {
  passed: { symbol: '✓', className: 'text-status-success-fg', label: 'Passed' },
  failed: { symbol: '✗', className: 'text-status-error-fg', label: 'Failed' },
  warning: { symbol: '!', className: 'text-status-warning-fg', label: 'Warning' },
  skipped: { symbol: '–', className: 'text-text-tertiary', label: 'Not checked' },
};

function CheckRow({ item }: { item: InstallationCheckItem }) {
  const mark =
    item.status === 'failed' && item.severity === 'warning' ? MARKS.warning : MARKS[item.status];
  return (
    <li className="flex gap-3 text-sm">
      <span aria-label={mark.label} className={`w-4 shrink-0 text-center font-semibold ${mark.className}`}>
        {mark.symbol}
      </span>
      <div className={item.status === 'skipped' ? 'text-text-tertiary' : 'text-foreground'}>
        <p>{item.label}</p>
        {item.fix && <p className="mt-0.5 text-text-secondary">{item.fix}</p>}
        {/* Only worth showing when the loader was added by another script. */}
        {item.key === 'snippet_present' && item.status === 'passed' && item.detail && (
          <p className="mt-0.5 text-xs text-text-secondary">{item.detail}</p>
        )}
      </div>
    </li>
  );
}
