import { create } from 'zustand';

import { getMe, login as loginApi } from '../api/auth';
import { getAuthUiProvider, type AuthUiProvider } from '../extensions/registry';
import { initAnalytics, trackAuthEvent } from '../services/analytics';
import type { User } from '../types/api';

function isRejectedSession(error: unknown): boolean {
  const status = (error as { response?: { status?: number } }).response?.status;
  return status === 401 || status === 403;
}

async function hasProviderSession(provider: AuthUiProvider): Promise<boolean> {
  try {
    return (await provider.getToken()) !== null;
  } catch {
    return false;
  }
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** The auth provider has a session that this deployment rejected. */
  providerSessionUnprovisioned: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  loadUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!localStorage.getItem('access_token'),
  isLoading: false,
  providerSessionUnprovisioned: false,

  login: async (email: string, password: string) => {
    set({ isLoading: true });
    try {
      const tokens = await loginApi(email, password);
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);
      const user = await getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      initAnalytics(user);
      trackAuthEvent('login', user.id);
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: () => {
    const { user } = useAuthStore.getState();
    trackAuthEvent('logout', user?.id);
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');

    const provider = getAuthUiProvider();
    if (provider) {
      set({ user: null, isAuthenticated: false, providerSessionUnprovisioned: false });
      void provider.logout();
      return;
    }
    set({ user: null, isAuthenticated: false });
  },

  loadUser: async () => {
    const provider = getAuthUiProvider();
    if (provider) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      set({ isLoading: true, isAuthenticated: false });
      try {
        const user = await getMe();
        set({
          user,
          isAuthenticated: true,
          isLoading: false,
          providerSessionUnprovisioned: false,
        });
        initAnalytics(user);
      } catch (error) {
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
          providerSessionUnprovisioned:
            isRejectedSession(error) && (await hasProviderSession(provider)),
        });
      }
      return;
    }

    if (!localStorage.getItem('access_token')) {
      set({ isAuthenticated: false });
      return;
    }
    set({ isLoading: true });
    try {
      const user = await getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      initAnalytics(user);
    } catch {
      localStorage.removeItem('access_token');
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
