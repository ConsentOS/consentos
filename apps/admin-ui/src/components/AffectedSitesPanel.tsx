import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { bulkPublish, listAffectedSites, publishErrorMessage } from '../api/revisions';
import { useRefreshOnSave } from '../hooks/useRefreshOnSave';
import { useAuthStore } from '../stores/auth';
import { canPublish } from './permissions';
import { Alert } from './ui/alert';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Modal } from './ui/modal';
import { Textarea } from './ui/textarea';
import type { AffectedSite, BulkPublishResult } from '../types/api';

interface Props {
  /** Limit to one site group; organisation-wide when omitted. */
  siteGroupId?: string;
}

/** Sites whose visitors don't yet see changed defaults, with a way to publish them all. */
export default function AffectedSitesPanel({ siteGroupId }: Props) {
  const queryKey = ['affected-sites', siteGroupId ?? 'organisation'];
  const { data: sites } = useQuery({
    queryKey,
    queryFn: () => listAffectedSites(siteGroupId),
  });
  useRefreshOnSave(queryKey);
  // The list as it was when publishing started. The live list refreshes
  // once the publish succeeds, and the results must stay on screen.
  const [publishing, setPublishing] = useState<AffectedSite[] | null>(null);
  const { user } = useAuthStore();

  return (
    <>
      {sites && sites.length > 0 && (
        <AffectedList sites={sites} canPublish={canPublish(user)} onPublish={setPublishing} />
      )}
      {publishing && <BulkPublishDialog sites={publishing} onClose={() => setPublishing(null)} />}
    </>
  );
}

interface ListProps {
  sites: AffectedSite[];
  canPublish: boolean;
  onPublish: (sites: AffectedSite[]) => void;
}

function AffectedList({ sites, canPublish, onPublish }: ListProps) {
  return (
    <div className="mb-4 rounded-lg border border-status-warning-fg/30 bg-status-warning-bg px-4 py-3 text-sm text-status-warning-fg">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-medium">
          {sites.length === 1 ? '1 site has' : `${sites.length} sites have`} unpublished changes
        </p>
        {canPublish ? (
          <Button size="sm" onClick={() => onPublish(sites)}>
            Publish all affected sites
          </Button>
        ) : (
          <span className="text-xs">Only owners and admins can publish.</span>
        )}
      </div>
      <ul className="mt-2 space-y-1 text-xs">
        {sites.map((site) => (
          <li key={site.site_id}>
            {site.name} <span className="opacity-75">(live v{site.live_number})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface DialogProps {
  sites: AffectedSite[];
  onClose: () => void;
}

function BulkPublishDialog({ sites, onClose }: DialogProps) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const [askAgain, setAskAgain] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      bulkPublish({
        sites: sites.map((site) => ({
          site_id: site.site_id,
          expected_content_hash: site.content_hash,
        })),
        note: note.trim() || null,
        ask_visitors_again: askAgain,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
    },
  });
  const results = mutation.data?.results;
  const byId = new Map(sites.map((site) => [site.site_id, site]));

  return (
    <Modal open onClose={onClose} title={`Publish ${sites.length} sites?`}>
      <div className="space-y-4 text-sm text-foreground">
        {results ? (
          <ul className="space-y-1">
            {results.map((result) => (
              <ResultRow key={result.site_id} result={result} name={byId.get(result.site_id)?.name} />
            ))}
          </ul>
        ) : (
          <>
            <p className="text-text-secondary">
              Each site is published as its own new version with the same note. A site that
              fails is left as it is and the others still publish.
            </p>
            <label className="block">
              <span className="mb-1 block font-medium">Note (optional)</span>
              <Textarea
                value={note}
                maxLength={500}
                onChange={(e) => setNote(e.target.value)}
                placeholder="What changed and why"
              />
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={askAgain}
                onChange={(e) => setAskAgain(e.target.checked)}
              />
              Ask visitors to consent again on every site
            </label>
          </>
        )}
        {mutation.isError && (
          <Alert variant="error">
            {publishErrorMessage(mutation.error, 'Nothing was published. Try again.')}
          </Alert>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {results ? 'Done' : 'Cancel'}
          </Button>
          {!results && (
            <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>
              {mutation.isPending ? 'Publishing...' : `Publish ${sites.length} sites`}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}

function ResultRow({ result, name }: { result: BulkPublishResult; name?: string }) {
  return (
    <li className="flex flex-wrap items-center gap-2">
      <span className="font-medium">{name ?? result.site_id}</span>
      {result.status === 'succeeded' ? (
        <Badge variant="success">Published v{result.revision_number}</Badge>
      ) : (
        <>
          <Badge variant="error">Failed</Badge>
          <span className="text-text-secondary">{result.error_message}</span>
        </>
      )}
    </li>
  );
}
