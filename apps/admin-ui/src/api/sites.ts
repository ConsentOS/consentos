import type { ConfigInheritanceResponse, Site, SiteConfig } from '../types/api';
import apiClient from './client';

export async function listSites(): Promise<Site[]> {
  const { data } = await apiClient.get<Site[]>('/sites/');
  return data;
}

export async function getSite(id: string): Promise<Site> {
  const { data } = await apiClient.get<Site>(`/sites/${id}`);
  return data;
}

export async function createSite(body: {
  domain: string;
  display_name: string;
  site_group_id?: string;
}): Promise<Site> {
  const { data } = await apiClient.post<Site>('/sites/', body);
  return data;
}

export async function updateSite(id: string, body: Partial<Site>): Promise<Site> {
  const { data } = await apiClient.patch<Site>(`/sites/${id}`, body);
  return data;
}

export async function deleteSite(id: string): Promise<void> {
  await apiClient.delete(`/sites/${id}`);
}

export async function getSiteConfig(siteId: string): Promise<SiteConfig> {
  const { data } = await apiClient.get<SiteConfig>(`/sites/${siteId}/config`);
  return data;
}

export async function updateSiteConfig(
  siteId: string,
  body: Partial<SiteConfig>,
): Promise<SiteConfig> {
  // PATCH (not PUT) so unsupplied fields aren't wiped to schema
  // defaults — the categories tab and the configuration tab each
  // submit only their own fields and must not clobber the other's.
  const { data } = await apiClient.patch<SiteConfig>(`/sites/${siteId}/config`, body);
  return data;
}

export async function getConfigInheritance(siteId: string): Promise<ConfigInheritanceResponse> {
  const { data } = await apiClient.get<ConfigInheritanceResponse>(
    `/config/sites/${siteId}/inheritance`,
  );
  return data;
}
