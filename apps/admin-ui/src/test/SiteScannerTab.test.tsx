import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import SiteScannerTab from '../components/SiteScannerTab';
import type { ScanDiff, ScanJob, ScanJobDetail } from '../types/api';

// ── Mocks ────────────────────────────────────────────────────────────

const mockListScans = vi.fn<() => Promise<ScanJob[]>>();
const mockTriggerScan = vi.fn<() => Promise<ScanJob>>();
const mockGetScan = vi.fn<() => Promise<ScanJobDetail>>();
const mockGetScanDiff = vi.fn<() => Promise<ScanDiff>>();

vi.mock('../api/scanner', () => ({
  listScans: (...args: unknown[]) => mockListScans(...(args as [])),
  triggerScan: (...args: unknown[]) => mockTriggerScan(...(args as [])),
  getScan: (...args: unknown[]) => mockGetScan(...(args as [])),
  getScanDiff: (...args: unknown[]) => mockGetScanDiff(...(args as [])),
}));

// ── Helpers ──────────────────────────────────────────────────────────

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderTab() {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SiteScannerTab siteId="site-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const TEST_SCAN: ScanJob = {
  id: 'scan-1',
  site_id: 'site-1',
  status: 'completed',
  trigger: 'manual',
  pages_scanned: 5,
  pages_total: 10,
  cookies_found: 3,
  error_message: null,
  started_at: '2026-03-10T10:00:00Z',
  completed_at: '2026-03-10T10:05:00Z',
  created_at: '2026-03-10T10:00:00Z',
  updated_at: '2026-03-10T10:05:00Z',
};

const TEST_SCAN_DETAIL: ScanJobDetail = {
  ...TEST_SCAN,
  results: [
    {
      id: 'r-1',
      scan_job_id: 'scan-1',
      page_url: 'https://example.com/',
      cookie_name: '_ga',
      cookie_domain: '.example.com',
      storage_type: 'cookie',
      attributes: null,
      script_source: 'https://www.googletagmanager.com/gtag/js',
      auto_category: 'analytics',
      initiator_chain: [
        'https://example.com/',
        'https://www.googletagmanager.com/gtm.js',
        'https://www.google-analytics.com/analytics.js',
      ],
      found_at: '2026-03-10T10:03:00Z',
      created_at: '2026-03-10T10:03:00Z',
    },
    {
      id: 'r-2',
      scan_job_id: 'scan-1',
      page_url: 'https://example.com/',
      cookie_name: 'session',
      cookie_domain: 'example.com',
      storage_type: 'cookie',
      attributes: null,
      script_source: null,
      auto_category: null,
      initiator_chain: null,
      found_at: '2026-03-10T10:03:00Z',
      created_at: '2026-03-10T10:03:00Z',
    },
  ],
};

const TEST_DIFF: ScanDiff = {
  current_scan_id: 'scan-1',
  previous_scan_id: null,
  new_cookies: [],
  removed_cookies: [],
  changed_cookies: [],
  total_new: 0,
  total_removed: 0,
  total_changed: 0,
};

// ── Tests ────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SiteScannerTab', () => {
  it('shows empty state when no scans exist', async () => {
    mockListScans.mockResolvedValue([]);
    renderTab();

    await waitFor(() => {
      expect(screen.getByText(/No scans yet/)).toBeInTheDocument();
    });
  });

  it('renders scan history table', async () => {
    mockListScans.mockResolvedValue([TEST_SCAN]);
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('completed')).toBeInTheDocument();
      expect(screen.getByText('Manual')).toBeInTheDocument();
    });
  });

  it('shows View Diff button for completed scans', async () => {
    mockListScans.mockResolvedValue([TEST_SCAN]);
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('View Diff')).toBeInTheDocument();
    });
  });

  it('shows initiator chains when expanding a completed scan', async () => {
    mockListScans.mockResolvedValue([TEST_SCAN]);
    mockGetScanDiff.mockResolvedValue(TEST_DIFF);
    mockGetScan.mockResolvedValue(TEST_SCAN_DETAIL);
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('View Diff')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('View Diff'));

    await waitFor(() => {
      // Should show initiator chains section with 1 cookie (the one with a chain)
      expect(screen.getByText('Initiator Chains (1 cookies)')).toBeInTheDocument();
      // Should show the cookie name
      expect(screen.getByText('_ga')).toBeInTheDocument();
    });
  });

  it('shows no initiator chains message when none detected', async () => {
    mockListScans.mockResolvedValue([TEST_SCAN]);
    mockGetScanDiff.mockResolvedValue(TEST_DIFF);
    mockGetScan.mockResolvedValue({
      ...TEST_SCAN,
      results: [
        {
          id: 'r-2',
          scan_job_id: 'scan-1',
          page_url: 'https://example.com/',
          cookie_name: 'session',
          cookie_domain: 'example.com',
          storage_type: 'cookie',
          attributes: null,
          script_source: null,
          auto_category: null,
          initiator_chain: null,
          found_at: '2026-03-10T10:03:00Z',
          created_at: '2026-03-10T10:03:00Z',
        },
      ],
    });
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('View Diff')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('View Diff'));

    await waitFor(() => {
      expect(screen.getByText('No initiator chains detected in this scan.')).toBeInTheDocument();
    });
  });

  it('shows a running scan\'s progress and disables triggering another', async () => {
    mockListScans.mockResolvedValue([
      {
        ...TEST_SCAN,
        status: 'running',
        trigger: 'initial',
        pages_scanned: 2,
        pages_total: 8,
        cookies_found: 1,
        completed_at: null,
      },
    ]);
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('2 of 8 pages scanned, 1 cookie found so far')).toBeInTheDocument();
    });
    expect(screen.getByText('First scan')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trigger Scan' })).toBeDisabled();
  });
});
