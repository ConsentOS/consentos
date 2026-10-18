import { type QueryKey, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

/**
 * Re-fetch ``queryKey`` after any successful save anywhere in the app.
 *
 * Unpublished-change checks depend on edits made through many different
 * mutations, so this listens to all of them rather than every save
 * having to know which checks to invalidate.
 */
export function useRefreshOnSave(queryKey: QueryKey): void {
  const queryClient = useQueryClient();
  const key = JSON.stringify(queryKey);
  useEffect(
    () =>
      queryClient.getMutationCache().subscribe((event) => {
        if (event.type === 'updated' && event.action.type === 'success') {
          queryClient.invalidateQueries({ queryKey: JSON.parse(key) as QueryKey });
        }
      }),
    [queryClient, key],
  );
}
