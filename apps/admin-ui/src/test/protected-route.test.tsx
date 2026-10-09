import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProtectedRoute from '../components/ProtectedRoute';
import { useAuthStore } from '../stores/auth';

vi.mock('../stores/auth', () => ({ useAuthStore: vi.fn() }));

function renderAt(path: string, state: { isAuthenticated: boolean; isLoading: boolean }) {
  vi.mocked(useAuthStore).mockReturnValue(state as ReturnType<typeof useAuthStore>);
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>Login page</p>} />
        <Route
          path="/sites/:siteId"
          element={
            <ProtectedRoute>
              <p>Site page</p>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute', () => {
  afterEach(() => {
    vi.mocked(useAuthStore).mockReset();
  });

  it('renders the page when authenticated', () => {
    renderAt('/sites/abc', { isAuthenticated: true, isLoading: false });
    expect(screen.getByText('Site page')).toBeInTheDocument();
  });

  it('renders the page while an authenticated user is refreshed', () => {
    renderAt('/sites/abc', { isAuthenticated: true, isLoading: true });
    expect(screen.getByText('Site page')).toBeInTheDocument();
  });

  it('waits on the requested page while the user is being resolved', () => {
    renderAt('/sites/abc', { isAuthenticated: false, isLoading: true });
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
    expect(screen.queryByText('Site page')).not.toBeInTheDocument();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('redirects to login when not authenticated', () => {
    renderAt('/sites/abc', { isAuthenticated: false, isLoading: false });
    expect(screen.getByText('Login page')).toBeInTheDocument();
  });
});
