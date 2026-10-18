import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import LiveRevisionCard from '../components/LiveRevisionCard';
import SiteHistoryTab from '../components/SiteHistoryTab';
import { useAuthStore } from '../stores/auth';
import type {
  DraftStatus,
  RevisionDetail,
  RevisionList,
  RevisionListItem,
  RevisionSummary,
} from '../types/api';

const mockListRevisions = vi.fn<(siteId: string, params: unknown) => Promise<RevisionList>>();
const mockGetDraftStatus = vi.fn<(siteId: string) => Promise<DraftStatus>>();
const mockGetRevision = vi.fn<(siteId: string, revisionId: string) => Promise<RevisionDetail>>();
const mockGetDiff = vi.fn();
const mockRollback =
  vi.fn<(siteId: string, revisionId: string, askAgain: boolean) => Promise<RevisionSummary>>();

vi.mock('../api/revisions', async () => {
  const actual = await vi.importActual<typeof import('../api/revisions')>('../api/revisions');
  return {
    apiErrorMessage: actual.apiErrorMessage,
    publishErrorMessage: actual.publishErrorMessage,
    listRevisions: (siteId: string, params: unknown) => mockListRevisions(siteId, params),
    getDraftStatus: (siteId: string) => mockGetDraftStatus(siteId),
    getRevision: (siteId: string, revisionId: string) => mockGetRevision(siteId, revisionId),
    rollbackToRevision: (siteId: string, revisionId: string, askAgain: boolean) =>
      mockRollback(siteId, revisionId, askAgain),
    getDiff: (siteId: string, params: unknown) => mockGetDiff(siteId, params),
  };
});

vi.mock('../stores/auth', () => ({ useAuthStore: vi.fn() }));

function signInAs(role: 'owner' | 'admin' | 'editor' | 'viewer') {
  vi.mocked(useAuthStore).mockReturnValue({ user: { role } } as ReturnType<typeof useAuthStore>);
}

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
    signInAs('owner');
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

    const table = await screen.findByRole('table');
    expect(within(table).getByText('v2')).toBeInTheDocument();
    expect(within(table).getByText('v1')).toBeInTheDocument();
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

describe('Rolling back', () => {
  const live = revision({ id: 'rev-2', number: 2, is_live: true });
  const earlier = revision({ id: 'rev-1', number: 1 });

  function detail(reasons: RevisionDetail['rollback_reconsent_reasons']): RevisionDetail {
    return { ...earlier, snapshot: {}, sources: [], rollback_reconsent_reasons: reasons };
  }

  beforeEach(() => {
    mockListRevisions.mockReset().mockResolvedValue({ total: 2, items: [live, earlier] });
    mockGetRevision.mockReset();
    mockRollback.mockReset();
    signInAs('admin');
  });

  it('offers rollback only on earlier revisions', async () => {
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);
    expect(await screen.findAllByRole('button', { name: 'Roll back' })).toHaveLength(1);
  });

  it('is disabled for editors with an explanation', async () => {
    signInAs('editor');
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);
    const button = await screen.findByRole('button', { name: 'Roll back' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Only owners and admins can roll back');
  });

  it('pre-ticks asking again when consent scope changes', async () => {
    mockGetRevision.mockResolvedValue(detail(['categories', 'vendors']));
    mockRollback.mockResolvedValue({ ...earlier, id: 'rev-3', number: 3 });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Roll back' }));

    const checkbox = await screen.findByRole('checkbox', { name: /Ask visitors to consent again/ });
    await waitFor(() => expect(checkbox).toBeChecked());
    expect(screen.getByText(/cookie categories and disclosed vendors/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Roll back to v1' }));
    await waitFor(() => expect(mockRollback).toHaveBeenCalledWith('site-1', 'rev-1', true));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('leaves the option unticked otherwise', async () => {
    mockGetRevision.mockResolvedValue(detail([]));
    mockRollback.mockResolvedValue({ ...earlier, id: 'rev-3', number: 3 });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Roll back' }));
    const confirm = await screen.findByRole('button', { name: 'Roll back to v1' });
    await waitFor(() => expect(confirm).toBeEnabled());

    expect(screen.getByRole('checkbox')).not.toBeChecked();
    fireEvent.click(confirm);
    await waitFor(() => expect(mockRollback).toHaveBeenCalledWith('site-1', 'rev-1', false));
  });

  it('explains a refusal for lack of permission', async () => {
    mockGetRevision.mockResolvedValue(detail([]));
    mockRollback.mockRejectedValue({ response: { status: 403, data: { detail: "Role 'editor' is not permitted for this action" } } });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Roll back' }));
    const confirm = await screen.findByRole('button', { name: 'Roll back to v1' });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);

    expect(await screen.findByText('Only owners and admins can publish, roll back or discard changes.')).toBeInTheDocument();
  });

  it('shows why a rollback failed', async () => {
    mockGetRevision.mockResolvedValue(detail([]));
    mockRollback.mockRejectedValue({ response: { data: { detail: 'That revision is already live' } } });
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Roll back' }));
    const confirm = await screen.findByRole('button', { name: 'Roll back to v1' });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);

    expect(await screen.findByText('That revision is already live')).toBeInTheDocument();
  });
});

describe('Comparing revisions', () => {
  beforeEach(() => {
    signInAs('viewer');
    mockGetDiff.mockReset().mockResolvedValue({
      from: { revision_id: 'rev-1', number: 1, content_hash: 'a' },
      to: { revision_id: 'rev-2', number: 2, content_hash: 'b' },
      changes: [
        { area: 'settings', key: 'terms_url', before: null, after: 'https://t', source: 'site' },
      ],
      reconsent_reasons: [],
    });
    mockListRevisions.mockReset().mockResolvedValue({
      total: 2,
      items: [revision({ id: 'rev-2', number: 2, is_live: true }), revision()],
    });
  });

  it('shows the differences between two revisions', async () => {
    renderWithQuery(<SiteHistoryTab siteId="site-1" />);

    const compare = await screen.findByRole('button', { name: 'Compare' });
    expect(compare).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Compare from'), { target: { value: 'rev-1' } });
    fireEvent.change(screen.getByLabelText('Compare to'), { target: { value: 'rev-2' } });
    fireEvent.click(compare);

    expect(await screen.findByText('Terms link')).toBeInTheDocument();
    expect(mockGetDiff).toHaveBeenCalledWith('site-1', {
      from_revision: 'rev-1',
      to_revision: 'rev-2',
    });
  });
});

describe('LiveRevisionCard', () => {
  const draft = (overrides: Partial<DraftStatus> = {}): DraftStatus => ({
    live_revision: null,
    content_hash: 'b'.repeat(64),
    has_unpublished_changes: true,
    changed_sources: [],
    reconsent_reasons: [],
    last_attempt: null,
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

  it('shows why the last publish failed', async () => {
    mockGetDraftStatus.mockResolvedValue(
      draft({
        live_revision: revision(),
        last_attempt: {
          action: 'publish',
          status: 'failed',
          error_code: 'stale_draft',
          error_message: 'The draft has changed since you reviewed it.',
          attempted_at: '2026-10-18T13:00:00Z',
          attempted_by_name: 'Ada Lovelace',
          revision_number: null,
        },
      }),
    );
    renderWithQuery(<LiveRevisionCard siteId="site-1" />);

    expect(
      await screen.findByText(/Last publish failed by Ada Lovelace.*The draft has changed/),
    ).toBeInTheDocument();
  });

  it('notes a successful last attempt quietly', async () => {
    mockGetDraftStatus.mockResolvedValue(
      draft({
        live_revision: revision({ number: 2 }),
        has_unpublished_changes: false,
        last_attempt: {
          action: 'rollback',
          status: 'succeeded',
          error_code: null,
          error_message: null,
          attempted_at: '2026-10-18T13:00:00Z',
          attempted_by_name: null,
          revision_number: 2,
        },
      }),
    );
    renderWithQuery(<LiveRevisionCard siteId="site-1" />);

    expect(await screen.findByText(/Last rollback succeeded,/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows when the site is not yet published', async () => {
    mockGetDraftStatus.mockResolvedValue(draft());
    renderWithQuery(<LiveRevisionCard siteId="site-1" />);
    expect(await screen.findByText('Not yet published')).toBeInTheDocument();
  });
});
