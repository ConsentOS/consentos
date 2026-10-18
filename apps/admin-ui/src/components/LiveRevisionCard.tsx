import { useQuery } from '@tanstack/react-query';

import { getDraftStatus } from '../api/revisions';
import { Alert } from './ui/alert';
import { Badge } from './ui/badge';
import { Card } from './ui/card';
import type { PublishAttempt } from '../types/api';

const ACTION_LABELS: Record<PublishAttempt['action'], string> = {
  publish: 'publish',
  rollback: 'rollback',
  bulk_publish: 'bulk publish',
};

function LastAttempt({ attempt }: { attempt: PublishAttempt }) {
  const when = new Date(attempt.attempted_at).toLocaleString();
  const who = attempt.attempted_by_name ? ` by ${attempt.attempted_by_name}` : '';
  if (attempt.status === 'succeeded') {
    return (
      <p className="mt-2 text-xs text-text-secondary">
        Last {ACTION_LABELS[attempt.action]} succeeded{who}, {when}.
      </p>
    );
  }
  return (
    <Alert variant="error" className="mt-3">
      Last {ACTION_LABELS[attempt.action]} failed{who}, {when}: {attempt.error_message}
    </Alert>
  );
}

interface Props {
  siteId: string;
}

/** What visitors are being served: the live revision, or nothing yet. */
export default function LiveRevisionCard({ siteId }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['sites', siteId, 'draft'],
    queryFn: () => getDraftStatus(siteId),
  });

  if (isLoading) return null;

  const live = data?.live_revision ?? null;

  return (
    <Card className="p-6">
      <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">Live configuration</h3>
      {isError || !data ? (
        <p className="text-sm text-text-secondary">Couldn't load the publish status.</p>
      ) : live ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-medium text-foreground">v{live.number}</span>
          <span className="text-text-secondary">
            published {new Date(live.published_at).toLocaleString()}
          </span>
          {data.has_unpublished_changes && <Badge variant="warning">Unpublished changes</Badge>}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge variant="neutral">Not yet published</Badge>
          <span className="text-text-secondary">Visitors see the built-in defaults until you publish.</span>
        </div>
      )}
      {data?.last_attempt && <LastAttempt attempt={data.last_attempt} />}
    </Card>
  );
}
