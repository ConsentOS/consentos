import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import ScanProgress from '../components/ScanProgress';
import { SCAN_POLL_INTERVAL_MS, scanPollInterval, useSiteScans } from '../hooks/useSiteScans';
import type { ScanJob } from '../types/api';

const mockListScans = vi.fn<() => Promise<ScanJob[]>>();

vi.mock('../api/scanner', () => ({
  listScans: (...args: unknown[]) => mockListScans(...(args as [])),
}));

function scan(overrides: Partial<ScanJob> = {}): ScanJob {
  return {
    id: 'scan-1',
    site_id: 'site-1',
    status: 'completed',
    trigger: 'initial',
    pages_scanned: 0,
    pages_total: 50,
    cookies_found: 0,
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: '2026-10-18T10:00:00Z',
    updated_at: '2026-10-18T10:00:00Z',
    ...overrides,
  };
}

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockListScans.mockReset();
});

describe('scanPollInterval', () => {
  it('polls while a scan is pending or running', () => {
    expect(scanPollInterval([scan({ status: 'pending' })])).toBe(SCAN_POLL_INTERVAL_MS);
    expect(scanPollInterval([scan(), scan({ id: 'scan-2', status: 'running' })])).toBe(
      SCAN_POLL_INTERVAL_MS,
    );
  });

  it('does not poll when no scan is in progress', () => {
    expect(scanPollInterval(undefined)).toBe(false);
    expect(scanPollInterval([])).toBe(false);
    expect(scanPollInterval([scan(), scan({ id: 'scan-2', status: 'failed' })])).toBe(false);
  });
});

describe('useSiteScans', () => {
  it('re-checks a running scan without a reload', async () => {
    mockListScans.mockResolvedValue([scan({ status: 'running' })]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    renderHook(() => useSiteScans('site-1'), { wrapper: wrapperFor(queryClient) });

    await waitFor(() => expect(mockListScans).toHaveBeenCalledTimes(2), {
      timeout: SCAN_POLL_INTERVAL_MS + 2000,
    });
  });

  it('refreshes the cookie list and draft when a scan finishes', async () => {
    mockListScans
      .mockResolvedValueOnce([scan({ status: 'running' })])
      .mockResolvedValueOnce([scan({ status: 'completed' })]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useSiteScans('site-1'), {
      wrapper: wrapperFor(queryClient),
    });
    await waitFor(() => expect(result.current.data?.[0].status).toBe('running'));
    expect(invalidate).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.refetch();
    });

    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['cookies', 'site-1'] });
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['sites', 'site-1', 'draft'] });
  });

  it('does not refresh cookies for scans that had already finished', async () => {
    mockListScans.mockResolvedValue([scan({ status: 'completed' })]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useSiteScans('site-1'), {
      wrapper: wrapperFor(queryClient),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await act(async () => {
      await result.current.refetch();
    });

    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe('ScanProgress', () => {
  it('shows pages crawled and cookies found so far', () => {
    render(
      <ScanProgress
        scan={scan({ status: 'running', pages_scanned: 3, pages_total: 12, cookies_found: 7 })}
      />,
    );
    expect(screen.getByText('3 of 12 pages scanned, 7 cookies found so far')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '25');
  });

  it('explains a scan that has not started yet', () => {
    render(<ScanProgress scan={scan({ status: 'pending' })} />);
    expect(screen.getByText('Waiting for the scanner to start…')).toBeInTheDocument();
  });

  it('explains a running scan that is still finding pages', () => {
    render(<ScanProgress scan={scan({ status: 'running' })} />);
    expect(screen.getByText('Finding pages to scan…')).toBeInTheDocument();
  });
});
