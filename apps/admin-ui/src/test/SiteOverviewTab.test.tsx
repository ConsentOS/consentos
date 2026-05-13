import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SiteOverviewTab from '../components/SiteOverviewTab';
import type { Site } from '../types/api';

const mockDeleteSite = vi.fn<(id: string) => Promise<void>>();
const mockNavigate = vi.fn();

vi.mock('../api/sites', () => ({
  deleteSite: (id: string) => mockDeleteSite(id),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

const TEST_SITE: Site = {
  id: 'site-1',
  organisation_id: 'org-1',
  domain: 'example.com',
  name: 'Example',
  display_name: 'Example',
  is_active: true,
  site_group_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SiteOverviewTab site={TEST_SITE} config={null} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SiteOverviewTab danger zone', () => {
  beforeEach(() => {
    mockDeleteSite.mockReset();
    mockNavigate.mockReset();
  });

  it('renders the delete button in the danger zone', () => {
    renderTab();
    expect(screen.getByText('Danger zone')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Delete site' }),
    ).toBeInTheDocument();
  });

  it('opens the confirm modal when clicking delete', () => {
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Delete site' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(
      screen.getByLabelText('Type the domain to confirm deletion'),
    ).toBeInTheDocument();
  });

  it('disables confirm until the domain is typed exactly', () => {
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Delete site' }));

    const confirmButton = screen
      .getAllByRole('button', { name: 'Delete site' })
      .at(-1)!;
    expect(confirmButton).toBeDisabled();

    const input = screen.getByLabelText('Type the domain to confirm deletion');
    fireEvent.change(input, { target: { value: 'wrong.com' } });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(input, { target: { value: 'example.com' } });
    expect(confirmButton).toBeEnabled();
  });

  it('calls deleteSite and navigates to /sites on success', async () => {
    mockDeleteSite.mockResolvedValueOnce();
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Delete site' }));
    fireEvent.change(
      screen.getByLabelText('Type the domain to confirm deletion'),
      { target: { value: 'example.com' } },
    );
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Delete site' }).at(-1)!,
    );

    await waitFor(() => expect(mockDeleteSite).toHaveBeenCalledWith('site-1'));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/sites'));
  });

  it('shows an error message when deletion fails', async () => {
    mockDeleteSite.mockRejectedValueOnce(new Error('Network down'));
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: 'Delete site' }));
    fireEvent.change(
      screen.getByLabelText('Type the domain to confirm deletion'),
      { target: { value: 'example.com' } },
    );
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Delete site' }).at(-1)!,
    );

    await waitFor(() =>
      expect(screen.getByText(/Network down/)).toBeInTheDocument(),
    );
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
