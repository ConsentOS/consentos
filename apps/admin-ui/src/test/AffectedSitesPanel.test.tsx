import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AffectedSitesPanel from '../components/AffectedSitesPanel';
import { useAuthStore } from '../stores/auth';
import type { AffectedSite } from '../types/api';

const mockListAffected = vi.fn<(groupId?: string) => Promise<AffectedSite[]>>();
const mockBulkPublish = vi.fn();

vi.mock('../api/revisions', async () => {
  const actual = await vi.importActual<typeof import('../api/revisions')>('../api/revisions');
  return {
    apiErrorMessage: actual.apiErrorMessage,
    listAffectedSites: (groupId?: string) => mockListAffected(groupId),
    bulkPublish: (body: unknown) => mockBulkPublish(body),
  };
});

vi.mock('../stores/auth', () => ({ useAuthStore: vi.fn() }));

function signInAs(role: 'owner' | 'admin' | 'editor' | 'viewer') {
  vi.mocked(useAuthStore).mockReturnValue({ user: { role } } as ReturnType<typeof useAuthStore>);
}

const SITES: AffectedSite[] = [
  {
    site_id: 's1',
    name: 'Shop',
    domain: 'shop.test',
    live_number: 4,
    content_hash: 'a'.repeat(64),
    changed_sources: [{ kind: 'site_group_config', id: 'g1' }],
  },
  {
    site_id: 's2',
    name: 'Blog',
    domain: 'blog.test',
    live_number: 1,
    content_hash: 'b'.repeat(64),
    changed_sources: [],
  },
];

function renderPanel(groupId?: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AffectedSitesPanel siteGroupId={groupId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockListAffected.mockReset();
  mockBulkPublish.mockReset();
  signInAs('admin');
});

describe('AffectedSitesPanel', () => {
  it('is hidden when no site is affected', async () => {
    mockListAffected.mockResolvedValue([]);
    const { container } = renderPanel('g1');
    await waitFor(() => expect(mockListAffected).toHaveBeenCalledWith('g1'));
    expect(container).toBeEmptyDOMElement();
  });

  it('lists the affected sites', async () => {
    mockListAffected.mockResolvedValue(SITES);
    renderPanel();
    expect(await screen.findByText('2 sites have unpublished changes')).toBeInTheDocument();
    expect(screen.getByText('Shop')).toBeInTheDocument();
    expect(screen.getByText('(live v4)')).toBeInTheDocument();
  });

  it('publishes them all and reports each result', async () => {
    mockListAffected.mockResolvedValueOnce(SITES).mockResolvedValue([]);
    mockBulkPublish.mockResolvedValue({
      batch_id: 'b1',
      results: [
        { site_id: 's1', status: 'succeeded', revision_number: 5, error_message: null },
        {
          site_id: 's2',
          status: 'failed',
          revision_number: null,
          error_message: 'The draft has changed since you reviewed it.',
        },
      ],
    });
    renderPanel('g1');

    fireEvent.click(await screen.findByRole('button', { name: 'Publish all affected sites' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByPlaceholderText('What changed and why'), {
      target: { value: 'Group terms' },
    });
    fireEvent.click(within(dialog).getByRole('checkbox'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish 2 sites' }));

    expect(await within(dialog).findByText('Published v5')).toBeInTheDocument();
    expect(within(dialog).getByText('Failed')).toBeInTheDocument();
    expect(within(dialog).getByText(/The draft has changed/)).toBeInTheDocument();
    expect(mockBulkPublish).toHaveBeenCalledWith({
      sites: [
        { site_id: 's1', expected_content_hash: 'a'.repeat(64) },
        { site_id: 's2', expected_content_hash: 'b'.repeat(64) },
      ],
      note: 'Group terms',
      ask_visitors_again: true,
    });

    // The list refreshes after publishing; the results stay until closed.
    await waitFor(() => expect(mockListAffected).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByText('2 sites have unpublished changes')).not.toBeInTheDocument(),
    );
    expect(within(dialog).getByText('Shop')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a failed request', async () => {
    mockListAffected.mockResolvedValue(SITES);
    mockBulkPublish.mockRejectedValue(new Error('network'));
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Publish all affected sites' }));
    fireEvent.click(screen.getByRole('button', { name: 'Publish 2 sites' }));

    expect(await screen.findByText('Nothing was published. Try again.')).toBeInTheDocument();
  });

  it('tells editors who can publish', async () => {
    signInAs('editor');
    mockListAffected.mockResolvedValue(SITES.slice(0, 1));
    renderPanel();
    expect(await screen.findByText('1 site has unpublished changes')).toBeInTheDocument();
    expect(screen.getByText('Only owners and admins can publish.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
