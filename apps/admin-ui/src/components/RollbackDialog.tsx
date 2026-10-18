import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { getRevision, publishErrorMessage, rollbackToRevision } from '../api/revisions';
import { describeReconsentReasons } from './reconsent';
import { Alert } from './ui/alert';
import { Button } from './ui/button';
import { Modal } from './ui/modal';
import type { RevisionListItem } from '../types/api';

interface Props {
  siteId: string;
  revision: RevisionListItem;
  onClose: () => void;
}

export default function RollbackDialog({ siteId, revision, onClose }: Props) {
  const queryClient = useQueryClient();
  const { data: detail, isLoading } = useQuery({
    queryKey: ['sites', siteId, 'revisions', 'detail', revision.id],
    queryFn: () => getRevision(siteId, revision.id),
  });
  const reasons = detail?.rollback_reconsent_reasons ?? [];
  // Pre-ticked when the rollback changes what visitors consented to,
  // until the user makes their own choice.
  const [askAgainChoice, setAskAgainChoice] = useState<boolean | null>(null);
  const askAgain = askAgainChoice ?? reasons.length > 0;

  const mutation = useMutation({
    mutationFn: () => rollbackToRevision(siteId, revision.id, askAgain),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'revisions'] });
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'draft'] });
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title={`Roll back to v${revision.number}?`}>
      <div className="space-y-4 text-sm">
        <p className="text-text-secondary">
          Visitors will be served exactly what v{revision.number} served. This is added to the
          history as a new version. Unpublished changes are kept.
        </p>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={askAgain}
            disabled={isLoading}
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
        {mutation.isError && (
          <Alert variant="error">
            {publishErrorMessage(mutation.error, 'The rollback failed. Nothing was changed.')}
          </Alert>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={isLoading || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? 'Rolling back...' : `Roll back to v${revision.number}`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
