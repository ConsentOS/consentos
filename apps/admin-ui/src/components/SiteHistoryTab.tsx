import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { listRevisions } from '../api/revisions';
import { Alert } from './ui/alert';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { EmptyState } from './ui/empty-state';
import { LoadingState } from './ui/loading-state';

const PAGE_SIZE = 25;

interface Props {
  siteId: string;
}

export default function SiteHistoryTab({ siteId }: Props) {
  const [page, setPage] = useState(0);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['sites', siteId, 'revisions', page],
    queryFn: () => listRevisions(siteId, { limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
  });

  if (isLoading) return <LoadingState message="Loading history..." />;
  if (isError || !data) return <Alert variant="error">Couldn't load the publish history.</Alert>;
  if (data.total === 0) {
    return <EmptyState message="Nothing has been published yet. Visitors see the built-in defaults." />;
  }

  const pageCount = Math.ceil(data.total / PAGE_SIZE);

  return (
    <Card className="p-6">
      <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">Publish history</h3>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-text-secondary">
          <tr>
            <th className="py-2 pr-4 font-medium">Version</th>
            <th className="py-2 pr-4 font-medium">Published</th>
            <th className="py-2 pr-4 font-medium">By</th>
            <th className="py-2 font-medium">Note</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((revision) => (
            <tr key={revision.id} className="border-t border-border-subtle align-top">
              <td className="py-3 pr-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-foreground">v{revision.number}</span>
                  {revision.is_live && <Badge variant="success">Live</Badge>}
                  {revision.requires_reconsent && (
                    <Badge variant="info">Asked visitors again</Badge>
                  )}
                </div>
              </td>
              <td className="py-3 pr-4 text-text-secondary">
                {new Date(revision.published_at).toLocaleString()}
              </td>
              <td className="py-3 pr-4 text-text-secondary">
                {revision.published_by_name ?? (revision.published_by ? 'Deleted user' : 'System')}
              </td>
              <td className="py-3 text-text-secondary">
                {revision.rolled_back_from_number !== null && (
                  <span className="mr-1">Copy of v{revision.rolled_back_from_number}.</span>
                )}
                {revision.note ?? (revision.rolled_back_from_number === null ? '—' : null)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {pageCount > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-text-secondary">
          <span>
            Page {page + 1} of {pageCount}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
              Newer
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page + 1 >= pageCount}
              onClick={() => setPage(page + 1)}
            >
              Older
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
