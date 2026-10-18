import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { createPreviewLink, getDiff, publishDraft, publishErrorMessage } from '../api/revisions';
import { useAuthStore } from '../stores/auth';
import ConfigDiffView from './ConfigDiffView';
import { canPublish } from './permissions';
import { describeReconsentReasons } from './reconsent';
import { Alert } from './ui/alert';
import { Button } from './ui/button';
import { LoadingState } from './ui/loading-state';
import { Modal } from './ui/modal';
import { Textarea } from './ui/textarea';

interface Props {
  siteId: string;
  onClose: () => void;
}

export default function PublishDialog({ siteId, onClose }: Props) {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const allowed = canPublish(user);
  const diffQuery = useQuery({
    queryKey: ['sites', siteId, 'diff', 'draft'],
    queryFn: () => getDiff(siteId),
  });
  const diff = diffQuery.data;
  const reasons = diff?.reconsent_reasons ?? [];
  const [note, setNote] = useState('');
  // Pre-ticked when the changes affect what visitors consented to, until
  // the user makes their own choice.
  const [askAgainChoice, setAskAgainChoice] = useState<boolean | null>(null);
  const askAgain = askAgainChoice ?? reasons.length > 0;

  const mutation = useMutation({
    mutationFn: () =>
      publishDraft(siteId, {
        // Publish exactly what was reviewed; the API refuses if it changed.
        expected_content_hash: diff!.to.content_hash!,
        note: note.trim() || null,
        ask_visitors_again: askAgain,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'draft'] });
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'revisions'] });
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'diff'] });
      onClose();
    },
  });

  const previewMutation = useMutation({ mutationFn: () => createPreviewLink(siteId) });
  const previewLink = previewMutation.data;

  function reviewAgain() {
    mutation.reset();
    diffQuery.refetch();
  }

  const isStale =
    mutation.isError &&
    (mutation.error as { response?: { status?: number } })?.response?.status === 409;

  return (
    <Modal open onClose={onClose} title="Review and publish" className="max-w-2xl">
      <div className="space-y-4 text-sm">
        <div className="max-h-[50vh] overflow-y-auto">
          {diffQuery.isLoading && <LoadingState message="Loading changes..." />}
          {diffQuery.isError && <Alert variant="error">Couldn't load the changes.</Alert>}
          {diff && (
            <>
              <p className="mb-3 text-text-secondary">
                {diff.from ? `Changes since v${diff.from.number}:` : 'First publish of this site:'}
              </p>
              <ConfigDiffView changes={diff.changes} />
            </>
          )}
        </div>

        {allowed ? (
          <>
            <div className="rounded-md border border-border-subtle p-3">
              {previewLink ? (
                <p>
                  <a
                    href={previewLink.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-copper hover:underline"
                  >
                    Open your site with these changes
                  </a>
                  <span className="block text-xs text-text-secondary">
                    Only you see them, until{' '}
                    {new Date(previewLink.expires_at).toLocaleTimeString()}. Nothing is saved
                    as consent while previewing.
                  </span>
                </p>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={previewMutation.isPending}
                  onClick={() => previewMutation.mutate()}
                >
                  {previewMutation.isPending ? 'Creating link...' : 'Preview on your site'}
                </Button>
              )}
              {previewMutation.isError && (
                <p className="mt-1 text-xs text-status-error-fg">
                  {publishErrorMessage(previewMutation.error, "Couldn't create a preview link.")}
                </p>
              )}
            </div>
            <label className="block">
              <span className="mb-1 block font-medium">Note (optional)</span>
              <Textarea
                value={note}
                maxLength={500}
                onChange={(e) => setNote(e.target.value)}
                placeholder="What changed and why"
              />
            </label>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={askAgain}
                disabled={!diff}
                onChange={(e) => setAskAgainChoice(e.target.checked)}
              />
              <span>
                Ask visitors to consent again
                {reasons.length > 0 && (
                  <span className="block text-text-secondary">
                    Recommended: this changes the {describeReconsentReasons(reasons)} visitors
                    consented to.
                  </span>
                )}
              </span>
            </label>
          </>
        ) : (
          <Alert variant="info">Only owners and admins can publish.</Alert>
        )}

        {mutation.isError && (
          <Alert variant="error">
            {publishErrorMessage(mutation.error, 'The publish failed. Nothing was changed.')}
            {isStale && (
              <Button variant="link" size="sm" onClick={reviewAgain}>
                Review the latest changes
              </Button>
            )}
          </Alert>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          {allowed && (
            <Button
              disabled={!diff || mutation.isPending || isStale}
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? 'Publishing...' : 'Publish'}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
