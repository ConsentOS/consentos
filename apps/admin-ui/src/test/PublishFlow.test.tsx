import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ConfigDiffView from '../components/ConfigDiffView';
import { changeLabel, formatValue } from '../components/configDiff';
import PublishDialog from '../components/PublishDialog';
import UnpublishedChangesBar from '../components/UnpublishedChangesBar';
import { useAuthStore } from '../stores/auth';
import type { ConfigDiff, DiffChange, DraftStatus } from '../types/api';

const mockGetDraftStatus = vi.fn<(siteId: string) => Promise<DraftStatus>>();
const mockGetDiff = vi.fn<(siteId: string, params?: unknown) => Promise<ConfigDiff>>();
const mockPublish = vi.fn();
const mockDiscard = vi.fn();

vi.mock('../api/revisions', async () => {
  const actual = await vi.importActual<typeof import('../api/revisions')>('../api/revisions');
  return {
    apiErrorMessage: actual.apiErrorMessage,
    publishErrorMessage: actual.publishErrorMessage,
    getDraftStatus: (siteId: string) => mockGetDraftStatus(siteId),
    getDiff: (siteId: string, params?: unknown) => mockGetDiff(siteId, params),
    publishDraft: (...args: unknown[]) => mockPublish(...args),
    discardDraft: (siteId: string) => mockDiscard(siteId),
  };
});

vi.mock('../stores/auth', () => ({ useAuthStore: vi.fn() }));

function signInAs(role: 'owner' | 'admin' | 'editor' | 'viewer') {
  vi.mocked(useAuthStore).mockReturnValue({ user: { role } } as ReturnType<typeof useAuthStore>);
}

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function draft(overrides: Partial<DraftStatus> = {}): DraftStatus {
  return {
    live_revision: {
      id: 'rev-3',
      number: 3,
      content_hash: 'a'.repeat(64),
      consent_version: 'cv',
      requires_reconsent: false,
      note: null,
      published_by: null,
      published_at: '2026-10-18T12:00:00Z',
    },
    content_hash: 'b'.repeat(64),
    has_unpublished_changes: true,
    changed_sources: [],
    reconsent_reasons: [],
    last_attempt: null,
    ...overrides,
  };
}

function change(overrides: Partial<DiffChange> = {}): DiffChange {
  return {
    area: 'settings',
    key: 'terms_url',
    before: null,
    after: 'https://x.test/t',
    source: 'site',
    ...overrides,
  };
}

function diff(overrides: Partial<ConfigDiff> = {}): ConfigDiff {
  return {
    from: { revision_id: 'rev-3', number: 3, content_hash: 'a'.repeat(64) },
    to: { revision_id: null, number: null, content_hash: 'c'.repeat(64) },
    changes: [change()],
    reconsent_reasons: [],
    ...overrides,
  };
}

beforeEach(() => {
  mockGetDraftStatus.mockReset();
  mockGetDiff.mockReset();
  mockPublish.mockReset();
  mockDiscard.mockReset();
  signInAs('owner');
});

describe('Discarding', () => {
  it('confirms, then discards', async () => {
    mockGetDraftStatus.mockResolvedValue(draft());
    mockDiscard.mockResolvedValue(draft({ has_unpublished_changes: false }));
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Discard changes' }));
    expect(screen.getByText(/go back to how they were in v3/)).toBeInTheDocument();
    expect(screen.getByText(/inherited from organisation or site group/)).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Discard changes' }));

    await waitFor(() => expect(mockDiscard).toHaveBeenCalledWith('site-1'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows why a discard failed', async () => {
    mockGetDraftStatus.mockResolvedValue(draft());
    mockDiscard.mockRejectedValue({ response: { data: { detail: 'Site not found' } } });
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Discard changes' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Discard changes' }));

    expect(await screen.findByText('Site not found')).toBeInTheDocument();
  });

  it('explains a refusal for lack of permission', async () => {
    mockGetDraftStatus.mockResolvedValue(draft());
    mockDiscard.mockRejectedValue({ response: { status: 403, data: { detail: "Role 'editor' is not permitted for this action" } } });
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Discard changes' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Discard changes' }));

    expect(await screen.findByText('Only owners and admins can publish, roll back or discard changes.')).toBeInTheDocument();
  });

  it('is not offered to editors or before the first publish', async () => {
    signInAs('editor');
    mockGetDraftStatus.mockResolvedValue(draft());
    const { unmount } = renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);
    await screen.findByText('Unpublished changes since v3');
    expect(screen.queryByRole('button', { name: 'Discard changes' })).not.toBeInTheDocument();
    unmount();

    signInAs('owner');
    mockGetDraftStatus.mockResolvedValue(draft({ live_revision: null }));
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);
    await screen.findByText('Not yet published');
    expect(screen.queryByRole('button', { name: 'Discard changes' })).not.toBeInTheDocument();
  });
});

describe('UnpublishedChangesBar', () => {
  it('is hidden when the draft is published', async () => {
    mockGetDraftStatus.mockResolvedValue(draft({ has_unpublished_changes: false }));
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);
    await waitFor(() => expect(mockGetDraftStatus).toHaveBeenCalled());
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('names the live version and inherited changes', async () => {
    mockGetDraftStatus.mockResolvedValue(
      draft({ changed_sources: [{ kind: 'organisation_config', id: 'org' }] }),
    );
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);
    expect(await screen.findByText('Unpublished changes since v3')).toBeInTheDocument();
    expect(screen.getByText('Defaults have changed since this revision.')).toBeInTheDocument();
  });

  it('says when nothing is published', async () => {
    mockGetDraftStatus.mockResolvedValue(draft({ live_revision: null }));
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);
    expect(await screen.findByText('Not yet published')).toBeInTheDocument();
  });

  it('re-checks after any save', async () => {
    mockGetDraftStatus.mockResolvedValue(draft({ has_unpublished_changes: false }));
    function SaveButton() {
      const save = useMutation({ mutationFn: () => Promise.resolve('saved') });
      return <button onClick={() => save.mutate()}>Save</button>;
    }
    renderWithQuery(
      <>
        <UnpublishedChangesBar siteId="site-1" />
        <SaveButton />
      </>,
    );
    await waitFor(() => expect(mockGetDraftStatus).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mockGetDraftStatus).toHaveBeenCalledTimes(2));
  });

  it('opens the review', async () => {
    mockGetDraftStatus.mockResolvedValue(draft());
    mockGetDiff.mockResolvedValue(diff());
    renderWithQuery(<UnpublishedChangesBar siteId="site-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Review and publish' }));

    expect(await screen.findByText('Changes since v3:')).toBeInTheDocument();
    expect(screen.getByText('Terms link')).toBeInTheDocument();
  });
});

describe('PublishDialog', () => {
  it('publishes exactly what was reviewed', async () => {
    mockGetDiff.mockResolvedValue(diff());
    mockPublish.mockResolvedValue({});
    const onClose = vi.fn();
    renderWithQuery(<PublishDialog siteId="site-1" onClose={onClose} />);

    await screen.findByText('Terms link');
    fireEvent.change(screen.getByPlaceholderText('What changed and why'), {
      target: { value: 'New terms' },
    });
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    await waitFor(() =>
      expect(mockPublish).toHaveBeenCalledWith('site-1', {
        expected_content_hash: 'c'.repeat(64),
        note: 'New terms',
        ask_visitors_again: false,
      }),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('pre-ticks asking again when consent scope changed', async () => {
    mockGetDiff.mockResolvedValue(diff({ reconsent_reasons: ['purposes'] }));
    renderWithQuery(<PublishDialog siteId="site-1" onClose={() => {}} />);

    await waitFor(() => expect(screen.getByRole('checkbox')).toBeChecked());
    expect(screen.getByText(/changes the TCF purposes visitors/)).toBeInTheDocument();
  });

  it('offers a fresh review when the draft changed', async () => {
    mockGetDiff.mockResolvedValue(diff());
    mockPublish.mockRejectedValue({
      response: { status: 409, data: { detail: 'The draft has changed since you reviewed it.' } },
    });
    renderWithQuery(<PublishDialog siteId="site-1" onClose={() => {}} />);

    await screen.findByText('Terms link');
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    expect(await screen.findByText(/The draft has changed/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Review the latest changes' }));
    await waitFor(() => expect(mockGetDiff).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Publish' })).toBeEnabled());
  });

  it('explains a refusal for lack of permission', async () => {
    mockGetDiff.mockResolvedValue(diff());
    mockPublish.mockRejectedValue({ response: { status: 403, data: { detail: "Role 'editor' is not permitted for this action" } } });
    renderWithQuery(<PublishDialog siteId="site-1" onClose={() => {}} />);

    await screen.findByText('Terms link');
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));

    expect(await screen.findByText('Only owners and admins can publish, roll back or discard changes.')).toBeInTheDocument();
  });

  it('lets editors review but not publish', async () => {
    signInAs('editor');
    mockGetDiff.mockResolvedValue(diff());
    renderWithQuery(<PublishDialog siteId="site-1" onClose={() => {}} />);

    await screen.findByText('Terms link');
    expect(screen.getByText('Only owners and admins can publish.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
  });
});

describe('ConfigDiffView', () => {
  it('groups by area and labels inherited changes', () => {
    render(
      <ConfigDiffView
        changes={[
          change({ key: 'consent_expiry_days', before: 365, after: 200, source: 'organisation' }),
          change({
            area: 'banner',
            key: 'banner_config.primaryColour',
            before: '#000',
            after: '#fff',
            source: 'site_group',
          }),
          change({ area: 'translations', key: 'fr.title', before: 'A', after: 'B' }),
        ]}
      />,
    );
    const headings = screen.getAllByRole('heading').map((h) => h.textContent);
    expect(headings).toEqual(['Settings', 'Banner', 'Translations']);
    expect(screen.getByText('From organisation defaults')).toBeInTheDocument();
    expect(screen.getByText('From site group defaults')).toBeInTheDocument();
    expect(screen.getByText('fr: title')).toBeInTheDocument();
  });

  it('says when there are no differences', () => {
    render(<ConfigDiffView changes={[]} />);
    expect(screen.getByText('No differences.')).toBeInTheDocument();
  });

  it('describes cookie and allow-list changes', () => {
    const cookie = change({
      area: 'cookies',
      key: 'cookies._ga@.x.test#cookie',
      before: { category: null },
      after: { category: 'analytics' },
    });
    expect(changeLabel(cookie)).toBe('Cookie _ga on .x.test');
    expect(formatValue(cookie, cookie.before)).toBe('Uncategorised');
    expect(formatValue(cookie, cookie.after)).toBe('analytics');
    expect(formatValue(cookie, null)).toBe('Not listed');

    const entry = change({ area: 'cookies', key: 'allow_list._ga@*' });
    expect(changeLabel(entry)).toBe('Allow-list entry _ga on *');
    expect(formatValue(entry, { name_pattern: '_ga' })).toBe('Listed');
  });

  it('formats plain values', () => {
    const setting = change();
    expect(formatValue(setting, true)).toBe('On');
    expect(formatValue(setting, [])).toBe('None');
    expect(formatValue(setting, ['a', 'b'])).toBe('a, b');
    expect(formatValue(setting, { a: 1 })).toBe('{"a":1}');
    expect(formatValue(setting, undefined)).toBe('Not set');
    expect(changeLabel(change({ key: 'category_tcf_purposes.analytics' }))).toBe(
      'TCF purposes for analytics',
    );
  });
});
