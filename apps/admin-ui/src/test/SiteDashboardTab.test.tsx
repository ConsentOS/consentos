import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SiteDashboardTab from '../components/SiteDashboardTab';
import type { ConsentRatesResponse, ConsentTrendsResponse } from '../types/api';

vi.mock('../api/analytics', () => ({
  getConsentRates: vi.fn(),
  getConsentTrends: vi.fn(),
}));

import { getConsentRates, getConsentTrends } from '../api/analytics';

const RATES: ConsentRatesResponse = {
  site_id: 'site-1',
  total_records: 10,
  consent_rate: 0.6,
  action_breakdown: { accept_all: 5, reject_all: 3, custom: 2, withdraw: 1 },
  category_rates: [{ category: 'analytics', accepted: 7, rejected: 3, rate: 0.7 }],
  from_date: '2026-05-17',
  to_date: '2026-06-16',
};

const EMPTY_RATES: ConsentRatesResponse = {
  ...RATES,
  total_records: 0,
  action_breakdown: { accept_all: 0, reject_all: 0, custom: 0, withdraw: 0 },
  category_rates: [],
};

const TRENDS: ConsentTrendsResponse = {
  site_id: 'site-1',
  granularity: 'day',
  data: [
    {
      period: '2026-06-16',
      total: 10,
      accept_all: 5,
      reject_all: 3,
      custom: 2,
      consent_rate: 0.7,
    },
  ],
  from_date: '2026-05-17',
  to_date: '2026-06-16',
};

function renderWithProviders(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('SiteDashboardTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders accept / partial / decline metrics from the API', async () => {
    vi.mocked(getConsentRates).mockResolvedValue(RATES);
    vi.mocked(getConsentTrends).mockResolvedValue(TRENDS);

    renderWithProviders(<SiteDashboardTab siteId="site-1" />);

    // decisions = 5 + 2 + 3 = 10 (withdraw excluded)
    expect(await screen.findByText('Total decisions')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    // accept 5 → 50%, partial 2 → 20%, decline 3 → 30%
    expect(screen.getByText('Accept')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();
    expect(screen.getByText('30%')).toBeInTheDocument();
    // withdrawal footnote
    expect(screen.getByText(/1 withdrawal/)).toBeInTheDocument();
  });

  it('shows an empty state when there are no decisions', async () => {
    vi.mocked(getConsentRates).mockResolvedValue(EMPTY_RATES);
    vi.mocked(getConsentTrends).mockResolvedValue({ ...TRENDS, data: [] });

    renderWithProviders(<SiteDashboardTab siteId="site-1" />);

    expect(
      await screen.findByText(/No consent decisions recorded/i),
    ).toBeInTheDocument();
  });
});
