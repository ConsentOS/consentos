import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import SitesPage from '../pages/SitesPage';

const mockCreateSite = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../api/sites', () => ({
  listSites: () => Promise.resolve([]),
  updateSite: vi.fn(),
  createSite: (body: unknown) => mockCreateSite(body),
}));
vi.mock('../api/site-groups', () => ({
  listSiteGroups: () => Promise.resolve([]),
  createSiteGroup: vi.fn(),
  deleteSiteGroup: vi.fn(),
}));
vi.mock('../api/installation', () => ({ listInstallations: () => Promise.resolve([]) }));
vi.mock('../api/setup', () => ({ listSetupSummaries: () => Promise.resolve([]) }));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

describe('adding the first site', () => {
  it('offers to add a site, then opens it', async () => {
    mockCreateSite.mockResolvedValue({ id: 'new-site' });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SitesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Add your first site' }));
    fireEvent.change(screen.getByPlaceholderText('example.com'), {
      target: { value: 'shop.example' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create site' }));

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/sites/new-site'));
    expect(mockCreateSite).toHaveBeenCalledWith(expect.objectContaining({ domain: 'shop.example' }));
  });
});
