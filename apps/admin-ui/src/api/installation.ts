import type { Installation, InstallationSummary } from '../types/api';
import apiClient from './client';

export async function getInstallation(siteId: string): Promise<Installation> {
  const { data } = await apiClient.get<Installation>(`/sites/${siteId}/installation`);
  return data;
}

export async function checkInstallation(siteId: string): Promise<Installation> {
  const { data } = await apiClient.post<Installation>(`/sites/${siteId}/installation/check`);
  return data;
}

export async function listInstallations(): Promise<InstallationSummary[]> {
  const { data } = await apiClient.get<InstallationSummary[]>('/sites/installations');
  return data;
}
