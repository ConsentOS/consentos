import apiClient from './client';
import type { DraftStatus, RevisionList } from '../types/api';

export async function getDraftStatus(siteId: string): Promise<DraftStatus> {
  const { data } = await apiClient.get<DraftStatus>(`/config/sites/${siteId}/draft`);
  return data;
}

export async function listRevisions(
  siteId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<RevisionList> {
  const { data } = await apiClient.get<RevisionList>(`/config/sites/${siteId}/revisions`, {
    params,
  });
  return data;
}
