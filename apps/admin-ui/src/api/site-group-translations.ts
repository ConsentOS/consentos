import type { SiteGroupTranslation } from '../types/api';
import apiClient from './client';

export async function listSiteGroupTranslations(groupId: string): Promise<SiteGroupTranslation[]> {
  const { data } = await apiClient.get<SiteGroupTranslation[]>(
    `/site-groups/${groupId}/translations/`,
  );
  return data;
}

export async function getSiteGroupTranslation(
  groupId: string,
  locale: string,
): Promise<SiteGroupTranslation> {
  const { data } = await apiClient.get<SiteGroupTranslation>(
    `/site-groups/${groupId}/translations/${locale}`,
  );
  return data;
}

export async function createSiteGroupTranslation(
  groupId: string,
  body: { locale: string; strings: Record<string, string> },
): Promise<SiteGroupTranslation> {
  const { data } = await apiClient.post<SiteGroupTranslation>(
    `/site-groups/${groupId}/translations/`,
    body,
  );
  return data;
}

export async function updateSiteGroupTranslation(
  groupId: string,
  locale: string,
  body: { strings: Record<string, string> },
): Promise<SiteGroupTranslation> {
  const { data } = await apiClient.put<SiteGroupTranslation>(
    `/site-groups/${groupId}/translations/${locale}`,
    body,
  );
  return data;
}

export async function deleteSiteGroupTranslation(groupId: string, locale: string): Promise<void> {
  await apiClient.delete(`/site-groups/${groupId}/translations/${locale}`);
}
