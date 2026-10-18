import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SiteConsentTab from '../components/SiteConsentTab';
import type { ConsentRecord } from '../types/api';

function record(overrides: Partial<ConsentRecord>): ConsentRecord {
  return {
    id: 'c1',
    site_id: 'site-1',
    visitor_id: 'visitor-1',
    action: 'accept_all',
    categories_accepted: ['necessary'],
    categories_rejected: [],
    tc_string: null,
    gcm_state: null,
    gpp_string: null,
    gpc_detected: null,
    gpc_honoured: null,
    page_url: null,
    country_code: null,
    region_code: null,
    config_revision_id: null,
    consent_version: null,
    config_revision_number: null,
    consented_at: '2026-10-18T12:00:00Z',
    ...overrides,
  } as ConsentRecord;
}

const mockList = vi.fn();
vi.mock('../api/consent', () => ({
  listConsentRecords: (...args: unknown[]) => mockList(...args),
}));

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SiteConsentTab siteId="site-1" />
    </QueryClientProvider>,
  );
}

describe('SiteConsentTab revision', () => {
  it('shows the version the visitor consented against', async () => {
    mockList.mockResolvedValue({
      items: [
        record({
          visitor_id: 'with-revision',
          config_revision_id: 'rev-3',
          consent_version: 'cv-1',
          config_revision_number: 3,
        }),
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
    renderTab();

    fireEvent.click(await screen.findByText('with-revision'));

    expect(screen.getByText('v3')).toBeInTheDocument();
    expect(screen.getByText('Consent version cv-1')).toBeInTheDocument();
  });

  it('says when no revision was recorded', async () => {
    mockList.mockResolvedValue({
      items: [record({ visitor_id: 'older-record' })],
      total: 1,
      page: 1,
      page_size: 50,
    });
    renderTab();

    fireEvent.click(await screen.findByText('older-record'));

    expect(screen.getByText('Not recorded')).toBeInTheDocument();
  });
});
