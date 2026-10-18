/**
 * The banner bundle drives GPC, GPP, re-consent and Shopify through the
 * modules in this package. These tests boot the real ``init()`` against
 * a mocked config endpoint and check each one takes effect.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ConsentState, SiteConfig } from '../types';

vi.mock('../shopify', () => ({ updateShopifyConsent: vi.fn() }));
vi.mock('../consent', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../consent')>();
  return { ...actual, readConsent: vi.fn(() => null) };
});

const baseConfig: SiteConfig = {
  id: 'cfg-1',
  site_id: 'site-1',
  blocking_mode: 'opt_in',
  regional_modes: null,
  tcf_enabled: false,
  gpp_enabled: false,
  gpp_supported_apis: [],
  gpc_enabled: false,
  gpc_jurisdictions: [],
  gpc_global_honour: false,
  gcm_enabled: false,
  gcm_default: null,
  shopify_privacy_enabled: false,
  banner_config: null,
  privacy_policy_url: null,
  terms_url: null,
  consent_expiry_days: 365,
  consent_group_id: null,
  initiator_map: null,
};

let fetchMock: ReturnType<typeof vi.fn>;

async function boot(config: Partial<SiteConfig>): Promise<void> {
  fetchMock = vi.fn(async (url: string) => {
    if (String(url).includes('/geo-resolved')) {
      return { ok: true, json: async () => ({ ...baseConfig, ...config }) };
    }
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  window.__consentos = {
    siteId: 'site-1',
    apiBase: 'https://api.example.com',
    cdnBase: 'https://cdn.example.com',
    loaded: false,
  } as typeof window.__consentos;
  vi.resetModules();
  await import('../banner');
  await vi.waitFor(() => {
    if (!fetchMock.mock.calls.some(([u]) => String(u).includes('/geo-resolved'))) {
      throw new Error('config not fetched yet');
    }
  });
  // Let init() finish rendering after the config resolves.
  await new Promise((r) => setTimeout(r, 0));
}

function bannerShown(): boolean {
  return document.querySelector('#consentos-banner-host')?.shadowRoot?.querySelector('.consentos-banner') != null;
}

function click(action: string): void {
  const root = document.querySelector('#consentos-banner-host')!.shadowRoot!;
  (root.querySelector(`[data-action="${action}"]`) as HTMLElement).click();
}

function consentPost(): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith('/api/v1/consent/'));
  expect(call).toBeDefined();
  return JSON.parse(call![1].body as string);
}

describe('banner wiring', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.cookie.split(';').forEach((c) => {
      document.cookie = `${c.split('=')[0].trim()}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
    });
    delete (window as { __gpp?: unknown }).__gpp;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(navigator, 'globalPrivacyControl', { value: undefined, configurable: true });
  });

  it('honours GPC for a visitor in a listed jurisdiction', async () => {
    Object.defineProperty(navigator, 'globalPrivacyControl', { value: true, configurable: true });
    await boot({ gpc_enabled: true, gpc_jurisdictions: ['US-CA'], detected_region: 'US-CA' });
    click('reject');
    expect(consentPost()).toMatchObject({ gpc_detected: true, gpc_honoured: true });
  });

  it('records GPC as detected but not honoured outside the listed jurisdictions', async () => {
    Object.defineProperty(navigator, 'globalPrivacyControl', { value: true, configurable: true });
    await boot({ gpc_enabled: true, gpc_jurisdictions: ['US-CA'], detected_region: 'GB' });
    click('reject');
    expect(consentPost()).toMatchObject({ gpc_detected: true, gpc_honoured: false });
  });

  it('installs __gpp and records the GPP string with the consent', async () => {
    await boot({ gpp_enabled: true, gpp_supported_apis: ['usnat'] });
    expect(typeof (window as { __gpp?: unknown }).__gpp).toBe('function');
    click('accept');
    const body = consentPost();
    expect(typeof body.gpp_string).toBe('string');
    expect((body.gpp_string as string).length).toBeGreaterThan(0);
  });

  it('sends no GPP string when GPP is off', async () => {
    await boot({});
    click('accept');
    expect(consentPost().gpp_string).toBeNull();
  });

  it('passes the decision to Shopify when the integration is on', async () => {
    const { updateShopifyConsent } = await import('../shopify');
    await boot({ shopify_privacy_enabled: true });
    click('reject');
    expect(updateShopifyConsent).toHaveBeenCalledWith(['necessary']);
  });

  it('shows the banner again when stored consent has expired', async () => {
    const { readConsent } = await import('../consent');
    const twoYearsAgo = new Date(Date.now() - 2 * 365 * 24 * 3600 * 1000).toISOString();
    vi.mocked(readConsent).mockReturnValue({
      accepted: ['necessary'],
      rejected: [],
      visitorId: 'v1',
      consentedAt: twoYearsAgo,
      bannerVersion: '1',
    } as ConsentState);
    await boot({ consent_expiry_days: 365 });
    expect(bannerShown()).toBe(true);
  });

  it('keeps the banner hidden while stored consent is current', async () => {
    const { readConsent } = await import('../consent');
    vi.mocked(readConsent).mockReturnValue({
      accepted: ['necessary'],
      rejected: [],
      visitorId: 'v1',
      consentedAt: new Date().toISOString(),
      bannerVersion: '1',
      configVersion: 'cfg-1',
    } as ConsentState);
    await boot({});
    expect(bannerShown()).toBe(false);
  });
});
