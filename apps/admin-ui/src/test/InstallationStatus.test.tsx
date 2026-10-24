import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import InstallationStatus from '../components/InstallationStatus';
import { useAuthStore } from '../stores/auth';
import type { Installation, InstallationCheckItem } from '../types/api';

vi.mock('../stores/auth', () => ({ useAuthStore: vi.fn() }));

const mockGetInstallation = vi.fn<(siteId: string) => Promise<Installation>>();
const mockCheckInstallation = vi.fn<(siteId: string) => Promise<Installation>>();

vi.mock('../api/installation', () => ({
  getInstallation: (siteId: string) => mockGetInstallation(siteId),
  checkInstallation: (siteId: string) => mockCheckInstallation(siteId),
}));

function asRole(role: string) {
  vi.mocked(useAuthStore).mockReturnValue({ user: { role } } as ReturnType<typeof useAuthStore>);
}

const NOT_DETECTED: Installation = {
  state: 'not_detected',
  first_seen_at: null,
  last_seen_at: null,
  last_seen_url: null,
  last_check_at: null,
  last_check: null,
};

function item(overrides: Partial<InstallationCheckItem>): InstallationCheckItem {
  return {
    key: 'reachable',
    label: 'The page loads',
    status: 'passed',
    severity: 'error',
    detail: null,
    fix: null,
    ...overrides,
  };
}

function renderStatus() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <InstallationStatus siteId="site-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockGetInstallation.mockReset();
  mockCheckInstallation.mockReset();
  asRole('editor');
});

describe('InstallationStatus', () => {
  it('explains that the banner has not been seen yet', async () => {
    mockGetInstallation.mockResolvedValue(NOT_DETECTED);
    renderStatus();

    expect(await screen.findByText('Not detected')).toBeInTheDocument();
    expect(screen.getByText(/haven't seen the banner on your site yet/)).toBeInTheDocument();
  });

  it('shows where and when the banner was last seen', async () => {
    mockGetInstallation.mockResolvedValue({
      ...NOT_DETECTED,
      state: 'installed',
      first_seen_at: '2026-10-18T10:00:00Z',
      last_seen_at: '2026-10-18T10:00:00Z',
      last_seen_url: 'https://example.com/pricing',
    });
    renderStatus();

    expect(await screen.findByText('Installed')).toBeInTheDocument();
    expect(screen.getByText(/on https:\/\/example.com\/pricing/)).toBeInTheDocument();
  });

  it('runs a check and shows each problem with its fix', async () => {
    mockGetInstallation.mockResolvedValue(NOT_DETECTED);
    mockCheckInstallation.mockResolvedValue({
      ...NOT_DETECTED,
      state: 'problem',
      last_check_at: '2026-10-18T10:00:00Z',
      last_check: {
        url: 'https://example.com/',
        checked_at: '2026-10-18T10:00:00Z',
        ok: false,
        checks: [
          item({}),
          item({
            key: 'synchronous',
            label: "The script isn't loaded asynchronously",
            status: 'failed',
            fix: 'Remove async and defer from the script tag.',
          }),
          item({ key: 'banner_shown', label: 'The banner appeared', status: 'skipped' }),
          item({
            key: 'published',
            label: "This site's configuration is published",
            status: 'failed',
            severity: 'warning',
            fix: 'Visitors see the built-in banner until you publish.',
          }),
        ],
      },
    });
    renderStatus();

    fireEvent.click(await screen.findByRole('button', { name: 'Check now' }));

    expect(await screen.findByText('Problem found')).toBeInTheDocument();
    expect(mockCheckInstallation).toHaveBeenCalledWith('site-1');
    expect(screen.getByText('Remove async and defer from the script tag.')).toBeInTheDocument();
    expect(screen.getByLabelText('Failed')).toBeInTheDocument();
    expect(screen.getByLabelText('Warning')).toBeInTheDocument();
    expect(screen.getByLabelText('Not checked')).toBeInTheDocument();
    expect(screen.getByLabelText('Passed')).toBeInTheDocument();
  });

  it('shows why a check could not run', async () => {
    mockGetInstallation.mockResolvedValue(NOT_DETECTED);
    mockCheckInstallation.mockRejectedValue({
      response: { status: 503, data: { detail: "The scanner isn't available at the moment." } },
    });
    renderStatus();

    fireEvent.click(await screen.findByRole('button', { name: 'Check now' }));

    await waitFor(() => {
      expect(screen.getByText("The scanner isn't available at the moment.")).toBeInTheDocument();
    });
  });

  it('tells viewers who can run a check', async () => {
    asRole('viewer');
    mockGetInstallation.mockResolvedValue(NOT_DETECTED);
    renderStatus();

    expect(await screen.findByText('Editors, admins and owners can run a check.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check now' })).not.toBeInTheDocument();
  });
});
