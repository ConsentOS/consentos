/**
 * Tests for the pluggable auth UI provider.
 *
 * Covers registry registration rules and the API client's token
 * sourcing: default localStorage JWT versus a registered provider.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AuthUiProvider } from '../extensions/registry';

async function freshRegistry() {
  vi.resetModules();
  return import('../extensions/registry');
}

function httpError(status: number): Error {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status },
  });
}

function stubProvider(token: string | null): AuthUiProvider {
  return {
    getToken: vi.fn(async () => token),
    logout: vi.fn(async () => undefined),
    LoginComponent: () => null,
  };
}

describe('registerAuthUiProvider', () => {
  it('returns null when nothing is registered', async () => {
    const registry = await freshRegistry();
    expect(registry.getAuthUiProvider()).toBeNull();
  });

  it('returns the registered provider', async () => {
    const registry = await freshRegistry();
    const provider = stubProvider('tok');
    registry.registerAuthUiProvider(provider);
    expect(registry.getAuthUiProvider()).toBe(provider);
  });

  it('rejects a second registration', async () => {
    const registry = await freshRegistry();
    registry.registerAuthUiProvider(stubProvider('a'));
    expect(() => registry.registerAuthUiProvider(stubProvider('b'))).toThrow(
      /already registered/,
    );
  });
});

describe('api client token sourcing', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('uses localStorage token when no provider is registered', async () => {
    localStorage.setItem('access_token', 'stored-jwt');
    const { default: apiClient } = await import('../api/client');

    const handler = apiClient.interceptors.request as unknown as {
      handlers: Array<{ fulfilled: (c: unknown) => Promise<{ headers: Record<string, string> }> }>;
    };
    const config = await handler.handlers[0].fulfilled({ headers: {} });
    expect(config.headers.Authorization).toBe('Bearer stored-jwt');
  });

  it('uses the provider token when registered', async () => {
    const registry = await import('../extensions/registry');
    registry.registerAuthUiProvider(stubProvider('provider-session-token'));
    const { default: apiClient } = await import('../api/client');

    const handler = apiClient.interceptors.request as unknown as {
      handlers: Array<{ fulfilled: (c: unknown) => Promise<{ headers: Record<string, string> }> }>;
    };
    const config = await handler.handlers[0].fulfilled({ headers: {} });
    expect(config.headers.Authorization).toBe('Bearer provider-session-token');
  });

  it('sends no header when the provider has no session', async () => {
    const registry = await import('../extensions/registry');
    registry.registerAuthUiProvider(stubProvider(null));
    const { default: apiClient } = await import('../api/client');

    const handler = apiClient.interceptors.request as unknown as {
      handlers: Array<{ fulfilled: (c: unknown) => Promise<{ headers: Record<string, string> }> }>;
    };
    const config = await handler.handlers[0].fulfilled({ headers: {} });
    expect(config.headers.Authorization).toBeUndefined();
  });
});

describe('loadUser with a registered provider', () => {
  afterEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
  });

  async function loadUserFailingWith(status: number, token: string | null) {
    vi.resetModules();
    vi.doMock('../api/auth', () => ({
      getMe: vi.fn(async () => {
        throw httpError(status);
      }),
      login: vi.fn(),
    }));
    const registry = await import('../extensions/registry');
    registry.registerAuthUiProvider(stubProvider(token));

    const { useAuthStore } = await import('../stores/auth');
    await useAuthStore.getState().loadUser();
    return useAuthStore.getState();
  }

  it.each([401, 403])(
    'flags an unprovisioned session when the API rejects a held token with %i',
    async (status) => {
      const state = await loadUserFailingWith(status, 'still-valid-token');
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
      expect(state.providerSessionUnprovisioned).toBe(true);
    },
  );

  it('does not flag unprovisioned when the provider has no token', async () => {
    const state = await loadUserFailingWith(401, null);
    expect(state.isAuthenticated).toBe(false);
    expect(state.providerSessionUnprovisioned).toBe(false);
  });

  it.each([500, 502])('does not flag unprovisioned when the API fails with %i', async (status) => {
    const state = await loadUserFailingWith(status, 'still-valid-token');
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
    expect(state.providerSessionUnprovisioned).toBe(false);
  });

  it('does not flag unprovisioned when the API cannot be reached', async () => {
    vi.resetModules();
    vi.doMock('../api/auth', () => ({
      getMe: vi.fn(async () => {
        throw new Error('Network Error');
      }),
      login: vi.fn(),
    }));
    const registry = await import('../extensions/registry');
    registry.registerAuthUiProvider(stubProvider('still-valid-token'));

    const { useAuthStore } = await import('../stores/auth');
    await useAuthStore.getState().loadUser();

    expect(useAuthStore.getState().providerSessionUnprovisioned).toBe(false);
  });
});

describe('stored tokens under a registered provider', () => {
  afterEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('clears a stale stored token when resolving through a provider', async () => {
    vi.resetModules();
    localStorage.setItem('access_token', 'stale-built-in-token');
    localStorage.setItem('refresh_token', 'stale-refresh-token');
    vi.doMock('../api/auth', () => ({
      getMe: vi.fn(async () => {
        throw httpError(401);
      }),
      login: vi.fn(),
    }));
    const registry = await import('../extensions/registry');
    registry.registerAuthUiProvider(stubProvider('provider-token'));

    const { useAuthStore } = await import('../stores/auth');
    await useAuthStore.getState().loadUser();

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('clears stored tokens on logout under a provider', async () => {
    vi.resetModules();
    localStorage.setItem('access_token', 'stale-built-in-token');
    localStorage.setItem('refresh_token', 'stale-refresh-token');
    vi.doMock('../api/auth', () => ({ getMe: vi.fn(), login: vi.fn() }));
    const registry = await import('../extensions/registry');
    const provider = stubProvider('provider-token');
    registry.registerAuthUiProvider(provider);

    const { useAuthStore } = await import('../stores/auth');
    useAuthStore.getState().logout();

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(provider.logout).toHaveBeenCalled();
  });
});
