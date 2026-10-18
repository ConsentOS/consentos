import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import InstallGuide from '../components/InstallGuide';
import type { Site, SiteInstall } from '../types/api';
import { installSnippet, resolveInstallUrls } from '../utils/installSnippet';

const mockGetSiteInstall = vi.fn<(id: string) => Promise<SiteInstall>>();

vi.mock('../api/sites', () => ({
  getSiteInstall: (id: string) => mockGetSiteInstall(id),
}));

const SITE: Site = {
  id: 'site-1',
  organisation_id: 'org-1',
  domain: 'example.com',
  name: null,
  display_name: 'Example',
  is_active: true,
  additional_domains: ['shop.example.org'],
  site_group_id: null,
  live_revision_id: null,
  created_at: '2026-10-18T00:00:00Z',
  updated_at: '2026-10-18T00:00:00Z',
};

function renderGuide() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <InstallGuide site={SITE} />
    </QueryClientProvider>,
  );
}

function snippetText(): string {
  return screen.getByLabelText('Install snippet').textContent ?? '';
}

beforeEach(() => {
  mockGetSiteInstall.mockReset();
});

describe('installSnippet', () => {
  it('leaves out data-cdn-base when the banner is served with the API', () => {
    expect(
      installSnippet('s1', { apiBase: 'https://cmp.example.net', cdnBase: 'https://cmp.example.net' }),
    ).toBe(
      '<script src="https://cmp.example.net/consent-loader.js" data-site-id="s1" data-api-base="https://cmp.example.net"></script>',
    );
  });

  it('includes data-cdn-base when the banner is served from elsewhere', () => {
    expect(
      installSnippet('s1', {
        apiBase: 'https://cmp.example.net',
        cdnBase: 'https://cmp.example.net/banner',
      }),
    ).toBe(
      '<script src="https://cmp.example.net/banner/consent-loader.js" data-site-id="s1" data-api-base="https://cmp.example.net" data-cdn-base="https://cmp.example.net/banner"></script>',
    );
  });
});

describe('resolveInstallUrls', () => {
  it('uses the configured addresses', () => {
    expect(
      resolveInstallUrls(
        { api_base: 'https://api.example.net', cdn_base: 'https://cdn.example.net', domains: [] },
        'https://admin.example.net',
      ),
    ).toEqual({ apiBase: 'https://api.example.net', cdnBase: 'https://cdn.example.net' });
  });

  it("falls back to the admin UI's own address", () => {
    expect(
      resolveInstallUrls({ api_base: null, cdn_base: null, domains: [] }, 'https://admin.example.net'),
    ).toEqual({ apiBase: 'https://admin.example.net', cdnBase: 'https://admin.example.net' });
    expect(resolveInstallUrls(undefined, 'https://admin.example.net').apiBase).toBe(
      'https://admin.example.net',
    );
  });
});

describe('InstallGuide', () => {
  it("builds the snippet from the deployment's addresses", async () => {
    mockGetSiteInstall.mockResolvedValue({
      api_base: 'https://api.example.net',
      cdn_base: 'https://cdn.example.net',
      domains: ['example.com'],
    });
    renderGuide();

    await waitFor(() => {
      expect(snippetText()).toContain('src="https://cdn.example.net/consent-loader.js"');
    });
    expect(snippetText()).toContain('data-api-base="https://api.example.net"');
    expect(snippetText()).toContain('data-cdn-base="https://cdn.example.net"');
    expect(snippetText()).toContain('data-site-id="site-1"');
  });

  it('has instructions for any site, WordPress and Shopify, each with the snippet', async () => {
    mockGetSiteInstall.mockResolvedValue({ api_base: null, cdn_base: null, domains: ['example.com'] });
    renderGuide();

    expect(screen.getByText(/as the first/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'WordPress' }));
    expect(screen.getByText(/WPCode/)).toBeInTheDocument();
    expect(screen.getByLabelText('Install snippet')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Shopify' }));
    expect(screen.getByText('layout/theme.liquid')).toBeInTheDocument();
    expect(screen.getByLabelText('Install snippet')).toBeInTheDocument();
  });

  it('copies the snippet', async () => {
    mockGetSiteInstall.mockResolvedValue({ api_base: null, cdn_base: null, domains: ['example.com'] });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderGuide();

    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));

    expect(writeText).toHaveBeenCalledWith(snippetText());
    expect(await screen.findByRole('button', { name: 'Copied!' })).toBeInTheDocument();
  });

  it("lists the site's domains", async () => {
    mockGetSiteInstall.mockResolvedValue({
      api_base: null,
      cdn_base: null,
      domains: ['example.com', 'shop.example.org'],
    });
    renderGuide();

    expect(await screen.findByText('shop.example.org')).toBeInTheDocument();
    expect(screen.getByText('example.com')).toBeInTheDocument();
  });
});
