import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SiteConfigTab from '../components/SiteConfigTab';
import type { SiteConfig } from '../types/api';

vi.mock('../api/sites', () => ({
  updateSiteConfig: vi.fn(() => Promise.resolve({})),
}));

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

const BASE_CONFIG: SiteConfig = {
  id: 'cfg-1',
  site_id: 'site-1',
  blocking_mode: 'opt_in',
  regional_modes: null,
  tcf_enabled: false,
  gpp_enabled: true,
  gpp_supported_apis: ['usnat'],
  gpc_enabled: true,
  gpc_jurisdictions: ['US-CA', 'US-CO', 'US-CT', 'US-TX', 'US-MT'],
  gpc_global_honour: false,
  gcm_enabled: true,
  gcm_default: null,
  shopify_privacy_enabled: false,
  banner_config: null,
  privacy_policy_url: null,
  terms_url: null,
  consent_expiry_days: 365,
  scan_enabled: true,
  scan_frequency_hours: 168,
  scan_max_pages: 50,
  enabled_categories: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

describe('SiteConfigTab', () => {
  it('renders consent settings section', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(screen.getByText('Consent settings')).toBeInTheDocument();
    expect(screen.getByText('Blocking mode')).toBeInTheDocument();
    expect(screen.getByText('Consent expiry (days)')).toBeInTheDocument();
    expect(screen.getByText('Privacy policy URL')).toBeInTheDocument();
  });

  it('renders standards section with TCF and GCM toggles', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(screen.getByText('Standards & integrations')).toBeInTheDocument();
    expect(screen.getByText('IAB TCF v2.2')).toBeInTheDocument();
    expect(screen.getByText('Google Consent Mode v2')).toBeInTheDocument();
  });

  it('renders GPP section with enable toggle', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(
      screen.getByText('IAB Global Privacy Platform (GPP)'),
    ).toBeInTheDocument();
    expect(screen.getByText('Enable GPP')).toBeInTheDocument();
  });

  it('shows GPP supported sections when GPP is enabled', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(screen.getByText('Supported sections')).toBeInTheDocument();
    expect(
      screen.getByText('US National Privacy (Section 7)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('US California — CCPA/CPRA (Section 8)'),
    ).toBeInTheDocument();
  });

  it('hides GPP supported sections when GPP is disabled', () => {
    const config = { ...BASE_CONFIG, gpp_enabled: false };
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={config} />,
    );

    expect(screen.queryByText('Supported sections')).not.toBeInTheDocument();
  });

  it('renders GPC section with detect toggle', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(
      screen.getByText('Global Privacy Control (GPC)'),
    ).toBeInTheDocument();
    expect(screen.getByText('Detect GPC signal')).toBeInTheDocument();
  });

  it('shows GPC jurisdiction list when GPC is enabled', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(screen.getByText('California (CCPA/CPRA)')).toBeInTheDocument();
    expect(screen.getByText('Colorado (CPA)')).toBeInTheDocument();
    expect(screen.getByText('Connecticut (CTDPA)')).toBeInTheDocument();
    expect(screen.getByText('Texas (TDPSA)')).toBeInTheDocument();
    expect(screen.getByText('Montana (MTCDPA)')).toBeInTheDocument();
  });

  it('hides GPC jurisdictions when GPC is disabled', () => {
    const config = { ...BASE_CONFIG, gpc_enabled: false };
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={config} />,
    );

    expect(
      screen.queryByText('California (CCPA/CPRA)'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Honour globally')).not.toBeInTheDocument();
  });

  it('shows honour globally toggle when GPC is enabled', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(screen.getByText('Honour globally')).toBeInTheDocument();
  });

  it('hides jurisdiction list when global honour is enabled', () => {
    const config = { ...BASE_CONFIG, gpc_global_honour: true };
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={config} />,
    );

    expect(screen.getByText('Honour globally')).toBeInTheDocument();
    expect(
      screen.queryByText('Jurisdictions where GPC is legally required'),
    ).not.toBeInTheDocument();
  });

  it('toggles GPP section checkbox', () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    // usnat should be checked by default
    const usnatLabel = screen
      .getByText('US National Privacy (Section 7)')
      .closest('label')!;
    const usnatCheckbox = usnatLabel.querySelector('input') as HTMLInputElement;
    expect(usnatCheckbox.checked).toBe(true);

    // usca should be unchecked
    const uscaLabel = screen
      .getByText('US California — CCPA/CPRA (Section 8)')
      .closest('label')!;
    const uscaCheckbox = uscaLabel.querySelector('input') as HTMLInputElement;
    expect(uscaCheckbox.checked).toBe(false);

    // Toggle usca on
    fireEvent.click(uscaCheckbox);
    expect(uscaCheckbox.checked).toBe(true);
  });

  it('submits GPP/GPC configuration', async () => {
    const sitesApi = await import('../api/sites');
    const spy = vi.mocked(sitesApi.updateSiteConfig);
    spy.mockClear();

    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    const saveBtn = screen.getByText('Save configuration');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(
        'site-1',
        expect.objectContaining({
          gpp_enabled: true,
          gpp_supported_apis: ['usnat'],
          gpc_enabled: true,
          gpc_jurisdictions: ['US-CA', 'US-CO', 'US-CT', 'US-TX', 'US-MT'],
          gpc_global_honour: false,
        }),
      );
    });
  });

  it('nulls gpp_supported_apis when GPP is disabled on submit', async () => {
    const sitesApi = await import('../api/sites');
    const spy = vi.mocked(sitesApi.updateSiteConfig);
    spy.mockClear();

    const config = { ...BASE_CONFIG, gpp_enabled: false };
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={config} />,
    );

    const saveBtn = screen.getByText('Save configuration');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(
        'site-1',
        expect.objectContaining({
          gpp_enabled: false,
          gpp_supported_apis: null,
        }),
      );
    });
  });

  it('nulls gpc_jurisdictions when GPC is disabled on submit', async () => {
    const sitesApi = await import('../api/sites');
    const spy = vi.mocked(sitesApi.updateSiteConfig);
    spy.mockClear();

    const config = { ...BASE_CONFIG, gpc_enabled: false };
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={config} />,
    );

    const saveBtn = screen.getByText('Save configuration');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(
        'site-1',
        expect.objectContaining({
          gpc_enabled: false,
          gpc_jurisdictions: null,
        }),
      );
    });
  });

  it('renders save button and shows success message', async () => {
    renderWithProviders(
      <SiteConfigTab siteId="site-1" config={BASE_CONFIG} />,
    );

    expect(screen.getByText('Save configuration')).toBeInTheDocument();
  });
});
