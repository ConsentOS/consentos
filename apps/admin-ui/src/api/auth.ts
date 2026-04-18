import type { TokenResponse, User } from '../types/api';
import apiClient from './client';

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/login', { email, password });
  return data;
}

export async function refreshToken(token: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/refresh', {
    refresh_token: token,
  });
  return data;
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>('/auth/me');
  return data;
}

export interface Profile {
  id: string;
  email: string;
  full_name: string;
  role: string;
  organisation_id: string;
}

export async function getProfile(): Promise<Profile> {
  const { data } = await apiClient.get<Profile>('/auth/me');
  return data;
}

export async function updateProfile(body: { email?: string; full_name?: string }): Promise<Profile> {
  const { data } = await apiClient.patch<Profile>('/auth/me', body);
  return data;
}

export async function changePassword(body: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  await apiClient.patch('/auth/me/password', body);
}
