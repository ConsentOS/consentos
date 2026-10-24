import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import SitesPage from '../pages/SitesPage';
import type { Site } from '../types/api';

function site(overrides: Partial<Site>): Site {
  return {
    id: 'site-1',
    organisation_id: 'org-1',
    domain: 'published.test',
    name: null,
    display_name: 'Published',
    is_active: true,
    additional_domains: null,
    site_group_id: null,
    live_revision_id: 'rev-1',
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}

vi.mock('../api/sites', () => ({
  listSites: () =>
    Promise.resolve([
      site({}),
      site({ id: 'site-2', domain: 'new.test', display_name: 'New', live_revision_id: null }),
      site({ id: 'site-3', domain: 'older.test', display_name: 'Older', live_revision_id: null }),
    ]),
  updateSite: vi.fn(),
}));

vi.mock('../api/installation', () => ({
  listInstallations: () =>
    Promise.resolve([
      { site_id: 'site-1', state: 'installed', last_seen_at: '2026-10-18T10:00:00Z' },
      { site_id: 'site-2', state: 'not_detected', last_seen_at: null },
      { site_id: 'site-3', state: 'not_detected', last_seen_at: null },
    ]),
}));

vi.mock('../api/setup', () => ({
  listSetupSummaries: () =>
    Promise.resolve([
      { site_id: 'site-1', done: 6, total: 6, complete: true, dismissed: true },
      { site_id: 'site-2', done: 2, total: 6, complete: false, dismissed: false },
    ]),
}));

vi.mock('../api/site-groups', () => ({
  listSiteGroups: () => Promise.resolve([]),
  createSiteGroup: vi.fn(),
  deleteSiteGroup: vi.fn(),
}));

describe('SitesPage', () => {
  it('marks sites that have not been published yet', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SitesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findAllByText('Setup 2 of 6');
    // Desktop and mobile layouts each render the badge once.
    const badges = screen.getAllByText('Not yet published');
    expect(badges).toHaveLength(2);
    expect(badges[0].closest('a')).toHaveAttribute('href', '/sites/site-3');
  });

  it('shows whether the banner is installed on each site', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SitesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findAllByText('Installed')).toHaveLength(2);
    expect(screen.getAllByText('Not detected')).toHaveLength(2);
  });

  it('shows setup progress for sites that are not set up yet', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SitesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const progress = await screen.findAllByText('Setup 2 of 6');
    expect(progress).toHaveLength(2);
    expect(progress[0].closest('a')).toHaveAttribute('href', '/sites/site-2');
    expect(screen.queryByText('Setup 6 of 6')).not.toBeInTheDocument();
  });

  it('shows only setup progress while a site is being set up', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SitesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findAllByText('Setup 2 of 6');
    // Only site-3, which has no setup in progress, shows these.
    expect(screen.getAllByText('Not yet published')).toHaveLength(2);
    expect(screen.getAllByText('Not detected')).toHaveLength(2);
  });
});
