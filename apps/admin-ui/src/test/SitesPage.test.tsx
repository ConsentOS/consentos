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
    ]),
  updateSite: vi.fn(),
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

    // Desktop and mobile layouts each render the badge once.
    const badges = await screen.findAllByText('Not yet published');
    expect(badges).toHaveLength(2);
    expect(badges[0].closest('a')).toHaveAttribute('href', '/sites/site-2');
  });
});
