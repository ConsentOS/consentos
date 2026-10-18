import { useQuery } from '@tanstack/react-query';

import { getDiff } from '../api/revisions';
import ConfigDiffView from './ConfigDiffView';
import { Alert } from './ui/alert';
import { LoadingState } from './ui/loading-state';
import { Modal } from './ui/modal';
import type { RevisionListItem } from '../types/api';

interface Props {
  siteId: string;
  from: RevisionListItem;
  to: RevisionListItem;
  onClose: () => void;
}

export default function CompareRevisionsDialog({ siteId, from, to, onClose }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['sites', siteId, 'diff', from.id, to.id],
    queryFn: () => getDiff(siteId, { from_revision: from.id, to_revision: to.id }),
  });

  return (
    <Modal open onClose={onClose} title={`v${from.number} → v${to.number}`} className="max-w-2xl">
      <div className="max-h-[60vh] overflow-y-auto">
        {isLoading && <LoadingState message="Loading changes..." />}
        {isError && <Alert variant="error">Couldn't load the changes.</Alert>}
        {data && <ConfigDiffView changes={data.changes} />}
      </div>
    </Modal>
  );
}
