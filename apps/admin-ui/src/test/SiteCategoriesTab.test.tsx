import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SiteCategoriesTab from '../components/SiteCategoriesTab';
import type { SiteConfig } from '../types/api';

vi.mock('../api/sites', () => ({
  updateSiteConfig: vi.fn().mockResolvedValue({}),
}));

vi.mock('../services/analytics', () => ({
  trackConfigChange: vi.fn(),
}));

import { updateSiteConfig } from '../api/sites';

function renderWithProviders(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
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
  gpc_jurisdictions: null,
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

describe('SiteCategoriesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all five categories with necessary locked', () => {
    renderWithProviders(<SiteCategoriesTab siteId="site-1" config={BASE_CONFIG} />);

    expect(screen.getByRole('checkbox', { name: /Necessary/i })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Functional/i })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Analytics/i })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Marketing/i })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Personalisation/i })).toBeInTheDocument();

    const necessary = screen.getByRole('checkbox', { name: /Necessary/i });
    expect(necessary).toBeChecked();
    expect(necessary).toBeDisabled();
  });

  it('shows "inheriting" copy when config has no override', () => {
    renderWithProviders(<SiteCategoriesTab siteId="site-1" config={BASE_CONFIG} />);
    expect(screen.getByText(/inheriting/i)).toBeInTheDocument();
  });

  it('pre-fills from existing override', () => {
    renderWithProviders(
      <SiteCategoriesTab
        siteId="site-1"
        config={{ ...BASE_CONFIG, enabled_categories: ['necessary', 'analytics'] }}
      />,
    );

    expect(screen.getByRole('checkbox', { name: /Necessary/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Analytics/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Functional/i })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Marketing/i })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Personalisation/i })).not.toBeChecked();
  });

  it('saves an explicit category list on submit', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SiteCategoriesTab
        siteId="site-1"
        config={{ ...BASE_CONFIG, enabled_categories: ['necessary', 'analytics', 'marketing'] }}
      />,
    );

    // Drop marketing
    await user.click(screen.getByRole('checkbox', { name: /Marketing/i }));
    await user.click(screen.getByRole('button', { name: /Save categories/i }));

    expect(updateSiteConfig).toHaveBeenCalledWith('site-1', {
      enabled_categories: ['necessary', 'analytics'],
    });
  });

  it('refuses to unlock necessary', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SiteCategoriesTab
        siteId="site-1"
        config={{ ...BASE_CONFIG, enabled_categories: ['necessary', 'analytics'] }}
      />,
    );

    // Clicking the locked checkbox is a no-op
    const necessary = screen.getByRole('checkbox', { name: /Necessary/i });
    await user.click(necessary);
    expect(necessary).toBeChecked();
  });

  it('resets to inherited by sending null', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SiteCategoriesTab
        siteId="site-1"
        config={{ ...BASE_CONFIG, enabled_categories: ['necessary'] }}
      />,
    );

    await user.click(screen.getByRole('button', { name: /Reset to inherited/i }));

    expect(updateSiteConfig).toHaveBeenCalledWith('site-1', {
      enabled_categories: null,
    });
  });
});
