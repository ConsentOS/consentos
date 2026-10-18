import { useQuery } from '@tanstack/react-query';

import { getDraftStatus } from '../api/revisions';
import { Badge } from './ui/badge';
import { Card } from './ui/card';

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
    </Card>
  );
}
