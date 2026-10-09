import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import App from '../App';
import * as registry from '../extensions/registry';

// Mock extension discovery to avoid loading EE modules in tests
vi.mock('../extensions/registry', () => ({
  discoverExtensions: vi.fn(() => Promise.resolve()),
  getSiteDetailTabs: vi.fn(() => []),
  getPages: vi.fn(() => []),
  getNavItems: vi.fn(() => []),
  getAuthUiProvider: vi.fn(() => null),
}));

const loadUserMock = vi.fn();

// Mock the auth store to control auth state
vi.mock('../stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    loadUser: loadUserMock,
  })),
}));

describe('App', () => {
  it('renders the login page when not authenticated', async () => {
    render(<App />);
    // ConsentOS wordmark renders Consent + OS as two spans for two-tone colour
    expect(await screen.findByText('Consent')).toBeInTheDocument();
    expect(screen.getByText('OS')).toBeInTheDocument();
    expect(screen.getByText('Sign in to manage your consent platform')).toBeInTheDocument();
  });

  it('renders email and password fields on login page', async () => {
    render(<App />);
    expect(await screen.findByLabelText('Email address')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });

  it('renders the sign in button', async () => {
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('renders no login form until extension discovery settles', async () => {
    let settle: () => void = () => {};
    vi.mocked(registry.discoverExtensions).mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          settle = resolve;
        }),
    );

    render(<App />);

    expect(screen.queryByLabelText('Email address')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument();

    settle();

    await waitFor(() => {
      expect(screen.getByLabelText('Email address')).toBeInTheDocument();
    });
  });

  it('resolves the user only after extension discovery settles', async () => {
    loadUserMock.mockClear();
    let settle: () => void = () => {};
    vi.mocked(registry.discoverExtensions).mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          settle = resolve;
        }),
    );

    render(<App />);

    expect(loadUserMock).not.toHaveBeenCalled();

    settle();

    await waitFor(() => expect(loadUserMock).toHaveBeenCalled());
  });
});
