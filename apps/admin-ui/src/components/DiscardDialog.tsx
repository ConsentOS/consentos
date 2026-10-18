import { useMutation, useQueryClient } from '@tanstack/react-query';

import { discardDraft, publishErrorMessage } from '../api/revisions';
import { Alert } from './ui/alert';
import { Button } from './ui/button';
import { Modal } from './ui/modal';

interface Props {
  siteId: string;
  liveNumber: number;
  onClose: () => void;
}

export default function DiscardDialog({ siteId, liveNumber, onClose }: Props) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => discardDraft(siteId),
    onSuccess: () => {
      // Every tab shows draft values, so all of them need reloading.
      queryClient.invalidateQueries({ queryKey: ['sites', siteId] });
      queryClient.invalidateQueries({ queryKey: ['cookies', siteId] });
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title="Discard unpublished changes?">
      <div className="space-y-4 text-sm">
        <p className="text-text-secondary">
          This site's settings, banner, translations and cookie rules go back to how they were
          in v{liveNumber}. Unpublished edits are lost.
        </p>
        <p className="text-text-secondary">
          Changes inherited from organisation or site group defaults can't be discarded here.
          They stay until you publish them or change them where they were made. Cookies found
          since the last publish stay in the review list.
        </p>
        {mutation.isError && (
          <Alert variant="error">
            {publishErrorMessage(mutation.error, 'Nothing was discarded. Try again.')}
          </Alert>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? 'Discarding...' : 'Discard changes'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
