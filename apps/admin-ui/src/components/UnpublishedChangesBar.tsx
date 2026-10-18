import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { getDraftStatus } from '../api/revisions';
import PublishDialog from './PublishDialog';
import { Button } from './ui/button';

interface Props {
  siteId: string;
}

/** Shown on every site tab while the draft differs from what visitors see. */
export default function UnpublishedChangesBar({ siteId }: Props) {
  const queryClient = useQueryClient();
  const [reviewing, setReviewing] = useState(false);
  const { data } = useQuery({
    queryKey: ['sites', siteId, 'draft'],
    queryFn: () => getDraftStatus(siteId),
  });

  // Any successful save on any tab may change the draft, so re-check.
  // Saves go through many different mutations, which is why this listens
  // to all of them rather than each tab invalidating the status itself.
  useEffect(
    () =>
      queryClient.getMutationCache().subscribe((event) => {
        if (event.type === 'updated' && event.action.type === 'success') {
          queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'draft'] });
        }
      }),
    [queryClient, siteId],
  );

  if (!data?.has_unpublished_changes) return null;

  const live = data.live_revision;
  return (
    <div
      role="status"
      className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-status-warning-fg/30 bg-status-warning-bg px-4 py-3 text-sm text-status-warning-fg"
    >
      <div>
        <p className="font-medium">
          {live ? `Unpublished changes since v${live.number}` : 'Not yet published'}
        </p>
        {data.changed_sources.length > 0 && (
          <p className="text-xs">Defaults have changed since this revision.</p>
        )}
        {!live && (
          <p className="text-xs">Visitors see the built-in defaults until you publish.</p>
        )}
      </div>
      <Button size="sm" onClick={() => setReviewing(true)}>
        Review and publish
      </Button>
      {reviewing && <PublishDialog siteId={siteId} onClose={() => setReviewing(false)} />}
    </div>
  );
}
