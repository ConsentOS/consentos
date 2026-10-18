import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import LiveRevisionCard from '../components/LiveRevisionCard';
import SiteHistoryTab from '../components/SiteHistoryTab';
import type { DraftStatus, RevisionList, RevisionListItem } from '../types/api';

const mockListRevisions = vi.fn<(siteId: string, params: unknown) => Promise<RevisionList>>();
const mockGetDraftStatus = vi.fn<(siteId: string) => Promise<DraftStatus>>();

vi.mock('../api/revisions', () => ({
  listRevisions: (siteId: string, params: unknown) => mockListRevisions(siteId, params),
  getDraftStatus: (siteId: string) => mockGetDraftStatus(siteId),
}));

function revision(overrides: Partial<RevisionListItem> = {}): RevisionListItem {
  return {
    id: 'rev-1',
    number: 1,
    content_hash: 'a'.repeat(64),
    consent_version: 'cv-1',
    requires_reconsent: false,
    note: null,
    published_by: 'user-1',
    published_at: '2026-10-18T12:00:00Z',
    is_live: false,
    published_by_name: 'Ada Lovelace',
    rolled_back_from_id: null,
    rolled_back_from_number: null,
    ...overrides,
  };
}

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('SiteHistoryTab', () => {
  beforeEach(() => {
    mockListRevisions.mockReset();
  });

  it('lists revisions with the live one marked', async () => {
    mockListRevisions.mockResolvedValue({
      total: 2,
      items: [
        revision({ id: 'rev-2', number: 2, is_live: true, requires_reconsent: true }),
        revision({ note: 'Launch' }),
      ],
    });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    expect(await screen.findByText('v2')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getAllByText('Live')).toHaveLength(1);
    expect(screen.getByText('Asked visitors again')).toBeInTheDocument();
    expect(screen.getByText('Launch')).toBeInTheDocument();
    expect(screen.getAllByText('Ada Lovelace')).toHaveLength(2);
    expect(mockListRevisions).toHaveBeenCalledWith('site-1', { limit: 25, offset: 0 });
  });

  it('names the source of a rollback and a deleted publisher', async () => {
    mockListRevisions.mockResolvedValue({
      total: 1,
      items: [
        revision({
          number: 3,
          rolled_back_from_id: 'rev-1',
          rolled_back_from_number: 1,
          published_by_name: null,
        }),
      ],
    });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    expect(await screen.findByText('Copy of v1.')).toBeInTheDocument();
    expect(screen.getByText('Deleted user')).toBeInTheDocument();
  });

  it('says when nothing is published', async () => {
    mockListRevisions.mockResolvedValue({ total: 0, items: [] });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);
    expect(await screen.findByText(/Nothing has been published yet/)).toBeInTheDocument();
  });

  it('pages through older revisions', async () => {
    mockListRevisions.mockResolvedValue({ total: 30, items: [revision()] });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Older' }));

    await waitFor(() =>
      expect(mockListRevisions).toHaveBeenLastCalledWith('site-1', { limit: 25, offset: 25 }),
    );
  });

  it('shows an error when history fails to load', async () => {
    mockListRevisions.mockRejectedValue(new Error('boom'));
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);
    expect(await screen.findByText("Couldn't load the publish history.")).toBeInTheDocument();
  });
});

describe('LiveRevisionCard', () => {
  const draft = (overrides: Partial<DraftStatus> = {}): DraftStatus => ({
    live_revision: null,
    content_hash: 'b'.repeat(64),
    has_unpublished_changes: true,
    changed_sources: [],
    reconsent_reasons: [],
    ...overrides,
  });

  it('shows the live revision and unpublished changes', async () => {
    mockGetDraftStatus.mockResolvedValue(draft({ live_revision: revision({ number: 4 }) }));
    renderWithQuery(<LiveRevisionCard siteId="site-1" />);

    expect(await screen.findByText('v4')).toBeInTheDocument();
    expect(screen.getByText('Unpublished changes')).toBeInTheDocument();
  });

  it('hides the badge when the draft is published', async () => {
    mockGetDraftStatus.mockResolvedValue(
      draft({ live_revision: revision(), has_unpublished_changes: false }),
    );
    renderWithQuery(<LiveRevisionCard siteId="site-1" />);

    expect(await screen.findByText('v1')).toBeInTheDocument();
    expect(screen.queryByText('Unpublished changes')).not.toBeInTheDocument();
  });

  it('shows when the site is not yet published', async () => {
    mockGetDraftStatus.mockResolvedValue(draft());
    renderWithQuery(<LiveRevisionCard siteId="site-1" />);
    expect(await screen.findByText('Not yet published')).toBeInTheDocument();
  });
});
