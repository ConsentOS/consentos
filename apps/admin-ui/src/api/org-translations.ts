import type { OrgTranslation } from '../types/api';
import apiClient from './client';

export async function listOrgTranslations(): Promise<OrgTranslation[]> {
  const { data } = await apiClient.get<OrgTranslation[]>('/org-translations/');
  return data;
}

export async function getOrgTranslation(locale: string): Promise<OrgTranslation> {
  const { data } = await apiClient.get<OrgTranslation>(`/org-translations/${locale}`);
  return data;
}

export async function createOrgTranslation(body: {
  locale: string;
  strings: Record<string, string>;
}): Promise<OrgTranslation> {
  const { data } = await apiClient.post<OrgTranslation>('/org-translations/', body);
  return data;
}

export async function updateOrgTranslation(
  locale: string,
  body: { strings: Record<string, string> },
): Promise<OrgTranslation> {
  const { data } = await apiClient.put<OrgTranslation>(`/org-translations/${locale}`, body);
  return data;
}

export async function deleteOrgTranslation(locale: string): Promise<void> {
  await apiClient.delete(`/org-translations/${locale}`);
}
