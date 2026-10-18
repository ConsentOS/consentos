import apiClient from './client';
import type {
  ConfigDiff,
  DraftStatus,
  RevisionDetail,
  RevisionList,
  RevisionSummary,
} from '../types/api';

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

export async function getRevision(siteId: string, revisionId: string): Promise<RevisionDetail> {
  const { data } = await apiClient.get<RevisionDetail>(
    `/config/sites/${siteId}/revisions/${revisionId}`,
  );
  return data;
}

export async function rollbackToRevision(
  siteId: string,
  revisionId: string,
  askVisitorsAgain: boolean,
): Promise<RevisionSummary> {
  const { data } = await apiClient.post<RevisionSummary>(
    `/config/sites/${siteId}/revisions/${revisionId}/rollback`,
    { ask_visitors_again: askVisitorsAgain },
  );
  return data;
}

/** Compare two revisions; by default the live revision with the draft. */
export async function getDiff(
  siteId: string,
  params: { from_revision?: string; to_revision?: string } = {},
): Promise<ConfigDiff> {
  const { data } = await apiClient.get<ConfigDiff>(`/config/sites/${siteId}/diff`, { params });
  return data;
}

export async function publishDraft(
  siteId: string,
  body: { expected_content_hash: string; note: string | null; ask_visitors_again: boolean },
): Promise<RevisionSummary> {
  const { data } = await apiClient.post<RevisionSummary>(`/config/sites/${siteId}/publish`, body);
  return data;
}

/** The API's own explanation of a failed request, or ``fallback``. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}
