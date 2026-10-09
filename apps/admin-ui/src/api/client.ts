import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { getAuthUiProvider } from '../extensions/registry';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// ── Token storage helpers ──────────────────────────────────────────
function getAccessToken(): string | null {
  return localStorage.getItem('access_token');
}

function setAccessToken(token: string): void {
  localStorage.setItem('access_token', token);
}

function getRefreshToken(): string | null {
  return localStorage.getItem('refresh_token');
}

function setRefreshToken(token: string): void {
  localStorage.setItem('refresh_token', token);
}

function clearTokens(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

// ── Request interceptor: attach bearer token ───────────────────────
apiClient.interceptors.request.use(async (config) => {
  const provider = getAuthUiProvider();
  const token = provider ? await provider.getToken() : getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor: refresh-on-401 ──────────────────────────
/**
 * When a request fails with 401, transparently attempt a single token
 * refresh using the stored refresh token. Concurrent 401s share the
 * same refresh promise so we don't hit ``/auth/refresh`` in parallel.
 *
 * If the refresh itself fails (no stored token, 401, or any other
 * error), clear stored tokens and redirect to the login page.
 */
type RetryableRequest = InternalAxiosRequestConfig & { _retry?: boolean };

let refreshPromise: Promise<string> | null = null;

async function performRefresh(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  // Use a bare axios call so we don't re-enter this interceptor.
  const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
    `${API_BASE}/auth/refresh`,
    { refresh_token: refreshToken },
    { headers: { 'Content-Type': 'application/json' } },
  );
  setAccessToken(data.access_token);
  setRefreshToken(data.refresh_token);
  return data.access_token;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryableRequest | undefined;
    const status = error.response?.status;

    if (status === 401 && getAuthUiProvider()) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }

    // Not a 401, or we've already retried — give up and propagate.
    if (status !== 401 || !original || original._retry) {
      if (status === 401) {
        clearTokens();
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }

    // Don't loop on the refresh endpoint itself.
    if (original.url?.includes('/auth/refresh')) {
      clearTokens();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }

    original._retry = true;

    try {
      // Coalesce concurrent refresh attempts.
      refreshPromise = refreshPromise ?? performRefresh();
      const newAccess = await refreshPromise;
      refreshPromise = null;

      original.headers = original.headers ?? {};
      original.headers.Authorization = `Bearer ${newAccess}`;
      return apiClient.request(original);
    } catch (refreshError) {
      refreshPromise = null;
      clearTokens();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(
        refreshError instanceof Error ? refreshError : new Error(String(refreshError)),
      );
    }
  },
);

export default apiClient;
