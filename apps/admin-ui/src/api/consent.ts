import type { ConsentRecord, PaginatedResponse } from '../types/api';
import apiClient from './client';

export async function listConsentRecords(
  siteId: string,
  params?: { visitor_id?: string; page?: number; page_size?: number },
): Promise<PaginatedResponse<ConsentRecord>> {
  const { data } = await apiClient.get<PaginatedResponse<ConsentRecord>>('/consent/', {
    params: { site_id: siteId, ...params },
  });
  return data;
}
