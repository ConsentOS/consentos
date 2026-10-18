import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { getDraftStatus } from '../api/revisions';
import { useRefreshOnSave } from '../hooks/useRefreshOnSave';
import { useAuthStore } from '../stores/auth';
import DiscardDialog from './DiscardDialog';
import { canPublish } from './permissions';
import PublishDialog from './PublishDialog';
import { Button } from './ui/button';

interface Props {
  siteId: string;
}

/** Shown on every site tab while the draft differs from what visitors see. */
export default function UnpublishedChangesBar({ siteId }: Props) {
  const [reviewing, setReviewing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const { user } = useAuthStore();
  const { data } = useQuery({
    queryKey: ['sites', siteId, 'draft'],
    queryFn: () => getDraftStatus(siteId),
  });

  useRefreshOnSave(['sites', siteId, 'draft']);

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
      <div className="flex gap-2">
        {live && canPublish(user) && (
          <Button size="sm" variant="outline" onClick={() => setDiscarding(true)}>
            Discard changes
          </Button>
        )}
        <Button size="sm" onClick={() => setReviewing(true)}>
          Review and publish
        </Button>
      </div>
      {reviewing && <PublishDialog siteId={siteId} onClose={() => setReviewing(false)} />}
      {discarding && live && (
        <DiscardDialog
          siteId={siteId}
          liveNumber={live.number}
          onClose={() => setDiscarding(false)}
        />
      )}
    </div>
  );
}
