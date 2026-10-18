import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SiteCookiesTab from '../components/SiteCookiesTab';
import type { Cookie } from '../types/api';

const mockUpdateCookie = vi.fn();

vi.mock('../api/cookies', () => ({
  listCookies: () =>
    Promise.resolve([
      { id: 'c1', name: '_ga', domain: '.x.test', category_id: null, review_status: 'pending' },
    ] as Partial<Cookie>[]),
  listCategories: () => Promise.resolve([{ id: 'cat-1', name: 'Analytics', slug: 'analytics' }]),
  getCookieSummary: () =>
    Promise.resolve({ total: 1, by_status: { pending: 1 }, uncategorised: 1 }),
  updateCookie: (...args: unknown[]) => mockUpdateCookie(...args),
}));

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SiteCookiesTab siteId="site-1" />
    </QueryClientProvider>,
  );
}

describe('SiteCookiesTab save feedback', () => {
  beforeEach(() => {
    mockUpdateCookie.mockReset();
  });

  it('confirms a change and says it needs publishing', async () => {
    mockUpdateCookie.mockResolvedValue({});
    renderTab();

    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Saved. Publish to apply.')).toBeInTheDocument();
    expect(mockUpdateCookie).toHaveBeenCalledWith('site-1', 'c1', { review_status: 'approved' });
  });

  it('shows why a change failed', async () => {
    mockUpdateCookie.mockRejectedValue({ response: { data: { detail: 'Invalid category_id' } } });
    renderTab();

    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'cat-1' } });

    expect(await screen.findByText('Invalid category_id')).toBeInTheDocument();
  });

  it('falls back to a generic message', async () => {
    mockUpdateCookie.mockRejectedValue(new Error('network'));
    renderTab();

    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));

    expect(await screen.findByText('Not saved. Try again.')).toBeInTheDocument();
  });
});
