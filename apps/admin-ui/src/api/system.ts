import type { VersionInfo } from '../types/api';
import apiClient from './client';

export async function getVersionInfo(): Promise<VersionInfo> {
  const { data } = await apiClient.get<VersionInfo>('/system/version');
  return data;
}
