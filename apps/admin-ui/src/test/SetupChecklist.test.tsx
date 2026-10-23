import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SetupChecklist from '../components/SetupChecklist';
import {
  SETUP_POLL_INTERVAL_MS,
  SETUP_SCAN_POLL_INTERVAL_MS,
  setupPollInterval,
} from '../hooks/useSiteSetup';
import { useAuthStore } from '../stores/auth';
import type { SetupStep, Site, SiteSetup } from '../types/api';

vi.mock('../stores/auth', () => ({ useAuthStore: vi.fn() }));

const mockGetSiteSetup = vi.fn<(siteId: string) => Promise<SiteSetup>>();
const mockConfirmBanner = vi.fn<(siteId: string) => Promise<SiteSetup>>();
const mockDismissSetup = vi.fn<(siteId: string) => Promise<SiteSetup>>();
const mockTriggerScan = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../api/setup', () => ({
  getSiteSetup: (siteId: string) => mockGetSiteSetup(siteId),
  confirmBanner: (siteId: string) => mockConfirmBanner(siteId),
  dismissSetup: (siteId: string) => mockDismissSetup(siteId),
}));
vi.mock('../api/scanner', () => ({ triggerScan: () => mockTriggerScan() }));
vi.mock('../components/InstallGuide', () => ({ default: () => <p>Install guide</p> }));
vi.mock('../components/InstallationStatus', () => ({ default: () => <p>Installation status</p> }));
vi.mock('../components/PublishDialog', () => ({ default: () => <p>Publish dialog</p> }));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const SITE: Site = {
  id: 'site-1',
  organisation_id: 'org-1',
  domain: 'example.com',
  name: null,
  display_name: 'Example',
  is_active: true,
  additional_domains: null,
  site_group_id: null,
  live_revision_id: null,
  created_at: '2026-10-18T00:00:00Z',
  updated_at: '2026-10-18T00:00:00Z',
};

const KEYS = ['scan', 'review', 'banner', 'publish', 'install', 'verify'] as const;

function setup(statuses: Partial<Record<(typeof KEYS)[number], SetupStep['status']>>, extra = {}) {
  const steps = KEYS.map((key) => ({
    key,
    status: statuses[key] ?? 'todo',
    detail: `${key} detail`,
  }));
  const done = steps.filter((s) => s.status === 'done').length;
  return { steps, done, total: 6, complete: done === 6, dismissed: false, ...extra } as SiteSetup;
}

function asRole(role: string) {
  vi.mocked(useAuthStore).mockReturnValue({ user: { role } } as ReturnType<typeof useAuthStore>);
}

function renderChecklist() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SetupChecklist site={SITE} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  asRole('owner');
});

describe('setupPollInterval', () => {
  it('polls quickly while the scan is running', () => {
    expect(setupPollInterval(setup({ scan: 'in_progress' }))).toBe(SETUP_SCAN_POLL_INTERVAL_MS);
  });

  it('polls slowly until setup is complete, then stops', () => {
    expect(setupPollInterval(setup({ scan: 'done' }))).toBe(SETUP_POLL_INTERVAL_MS);
    const all = Object.fromEntries(KEYS.map((k) => [k, 'done'])) as Record<string, 'done'>;
    expect(setupPollInterval(setup(all))).toBe(false);
    expect(setupPollInterval(setup({}, { dismissed: true }))).toBe(false);
  });
});

describe('SetupChecklist', () => {
  it('lists every step in order with its status', async () => {
    mockGetSiteSetup.mockResolvedValue(setup({ scan: 'in_progress' }));
    renderChecklist();

    expect(await screen.findByText('Set up your site')).toBeInTheDocument();
    expect(screen.getByText('0 of 6 steps done')).toBeInTheDocument();
    const titles = screen.getAllByRole('button', { expanded: false }).map((b) => b.textContent);
    expect(titles.join(' ')).toContain('Review cookies');
    expect(screen.getByLabelText('In progress')).toBeInTheDocument();
    expect(screen.getByText('scan detail')).toBeInTheDocument();
  });

  it('opens the first step that is not done', async () => {
    mockGetSiteSetup.mockResolvedValue(setup({ scan: 'done', review: 'done' }));
    renderChecklist();

    const banner = await screen.findByRole('button', { name: /Set up your banner/ });
    expect(banner).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Looks good' })).toBeInTheDocument();
  });

  it('confirms the banner', async () => {
    mockGetSiteSetup.mockResolvedValue(setup({ scan: 'done', review: 'done' }));
    const confirmed = setup({ scan: 'done', review: 'done', banner: 'done' });
    mockConfirmBanner.mockResolvedValue(confirmed);
    renderChecklist();

    // Saving refreshes the checklist, which the server then answers with.
    mockGetSiteSetup.mockResolvedValue(confirmed);
    fireEvent.click(await screen.findByRole('button', { name: 'Looks good' }));

    await waitFor(() => expect(screen.getByText('3 of 6 steps done')).toBeInTheDocument());
    expect(mockConfirmBanner).toHaveBeenCalledWith('site-1');
  });

  it('takes the owner to the right tab', async () => {
    mockGetSiteSetup.mockResolvedValue(setup({ scan: 'done' }));
    renderChecklist();

    fireEvent.click(await screen.findByRole('button', { name: 'Review cookies' }));
    expect(mockNavigate).toHaveBeenCalledWith({ hash: 'cookies' });
  });

  it('offers to start a scan that has not run', async () => {
    mockGetSiteSetup.mockResolvedValue(setup({}));
    mockTriggerScan.mockResolvedValue({});
    renderChecklist();

    fireEvent.click(await screen.findByRole('button', { name: 'Start scan' }));
    await waitFor(() => expect(mockTriggerScan).toHaveBeenCalled());
  });

  it('opens publishing for owners and admins', async () => {
    mockGetSiteSetup.mockResolvedValue(
      setup({ scan: 'done', review: 'done', banner: 'done' }),
    );
    renderChecklist();

    fireEvent.click(await screen.findByRole('button', { name: 'Review and publish' }));
    expect(screen.getByText('Publish dialog')).toBeInTheDocument();
  });

  it('tells editors who can publish', async () => {
    asRole('editor');
    mockGetSiteSetup.mockResolvedValue(
      setup({ scan: 'done', review: 'done', banner: 'done' }),
    );
    renderChecklist();

    expect(await screen.findByText(/Ask an owner or admin to publish/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Review and publish' })).not.toBeInTheDocument();
  });

  it('shows the install guide and the check in their steps', async () => {
    mockGetSiteSetup.mockResolvedValue(
      setup({ scan: 'done', review: 'done', banner: 'done', publish: 'done' }),
    );
    renderChecklist();

    expect(await screen.findByText('Install guide')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Check it's working/ }));
    expect(screen.getByText('Installation status')).toBeInTheDocument();
  });

  it('can be dismissed once complete', async () => {
    const all = Object.fromEntries(KEYS.map((k) => [k, 'done'])) as Record<string, 'done'>;
    mockGetSiteSetup.mockResolvedValue(setup(all));
    mockDismissSetup.mockResolvedValue(setup(all, { dismissed: true }));
    renderChecklist();

    expect(await screen.findByText("You're all set")).toBeInTheDocument();
    mockGetSiteSetup.mockResolvedValue(setup(all, { dismissed: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    await waitFor(() => expect(screen.queryByText("You're all set")).not.toBeInTheDocument());
    expect(mockDismissSetup).toHaveBeenCalledWith('site-1');
  });

  it('has no dismiss button until complete', async () => {
    mockGetSiteSetup.mockResolvedValue(setup({ scan: 'done' }));
    renderChecklist();

    await screen.findByText('Set up your site');
    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument();
  });

  it('shows nothing once dismissed', async () => {
    mockGetSiteSetup.mockResolvedValue(setup({}, { dismissed: true }));
    const { container } = renderChecklist();

    await waitFor(() => expect(mockGetSiteSetup).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
