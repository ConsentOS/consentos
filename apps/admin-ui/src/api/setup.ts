import type { SiteSetup, SiteSetupSummary } from '../types/api';
import apiClient from './client';

export async function getSiteSetup(siteId: string): Promise<SiteSetup> {
  const { data } = await apiClient.get<SiteSetup>(`/sites/${siteId}/setup`);
  return data;
}

export async function confirmBanner(siteId: string): Promise<SiteSetup> {
  const { data } = await apiClient.post<SiteSetup>(`/sites/${siteId}/setup/banner-confirmed`);
  return data;
}

export async function dismissSetup(siteId: string): Promise<SiteSetup> {
  const { data } = await apiClient.post<SiteSetup>(`/sites/${siteId}/setup/dismiss`);
  return data;
}

export async function listSetupSummaries(): Promise<SiteSetupSummary[]> {
  const { data } = await apiClient.get<SiteSetupSummary[]>('/sites/setup-summary');
  return data;
}
