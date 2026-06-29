import type { AllowListEntry, Cookie, CookieCategory } from '../types/api';
import apiClient from './client';

export async function listCategories(): Promise<CookieCategory[]> {
  const { data } = await apiClient.get<CookieCategory[]>('/cookies/categories');
  return data;
}

export async function listCookies(
  siteId: string,
  params?: { review_status?: string; category_id?: string },
): Promise<Cookie[]> {
  const { data } = await apiClient.get<Cookie[]>(`/cookies/sites/${siteId}`, { params });
  return data;
}

export interface CookieCreatePayload {
  name: string;
  domain: string;
  storage_type?: string;
  category_id?: string | null;
  vendor?: string | null;
  description?: string | null;
  path?: string | null;
  same_site?: string | null;
  max_age_seconds?: number | null;
}

export async function createCookie(
  siteId: string,
  body: CookieCreatePayload,
): Promise<Cookie> {
  const { data } = await apiClient.post<Cookie>(`/cookies/sites/${siteId}`, body);
  return data;
}

export async function updateCookie(
  siteId: string,
  cookieId: string,
  body: Partial<Cookie>,
): Promise<Cookie> {
  const { data } = await apiClient.patch<Cookie>(`/cookies/sites/${siteId}/${cookieId}`, body);
  return data;
}

export async function getCookieSummary(
  siteId: string,
): Promise<{ total: number; by_status: Record<string, number>; by_category: Record<string, number>; uncategorised: number }> {
  const { data } = await apiClient.get(`/cookies/sites/${siteId}/summary`);
  return data as { total: number; by_status: Record<string, number>; by_category: Record<string, number>; uncategorised: number };
}

export async function listAllowList(siteId: string): Promise<AllowListEntry[]> {
  const { data } = await apiClient.get<AllowListEntry[]>(`/cookies/sites/${siteId}/allow-list`);
  return data;
}

export async function createAllowListEntry(
  siteId: string,
  body: { name_pattern: string; domain_pattern: string; category_id: string; description?: string },
): Promise<AllowListEntry> {
  const { data } = await apiClient.post<AllowListEntry>(`/cookies/sites/${siteId}/allow-list`, body);
  return data;
}

export async function deleteAllowListEntry(siteId: string, entryId: string): Promise<void> {
  await apiClient.delete(`/cookies/sites/${siteId}/allow-list/${entryId}`);
}
