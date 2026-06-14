/**
 * Tests for the embedded cookies management widget. Verifies the
 * fetch -> render -> save round trip without spinning up the full
 * banner init flow.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderCookiesWidget } from '../cookies-widget';
import type { TranslationStrings } from '../i18n';
import type { CategorySlug } from '../types';

const SAMPLE_PAYLOAD = {
  site_id: 'site-A',
  site_name: 'Example',
  domain: 'example.com',
  privacy_policy_url: 'https://example.com/privacy',
  consent_expiry_days: 365,
  categories: [
    {
      slug: 'necessary',
      name: 'Strictly necessary',
      description: 'Required for the site to work.',
      locked: true,
      cookies: [
        { name: '_session', domain: 'example.com', type: 'cookie', description: 'Session', vendor: 'Example' },
      ],
    },
    {
      slug: 'analytics',
      name: 'Analytics',
      description: 'Help us improve.',
      locked: false,
      cookies: [
        { name: '_ga', domain: '.example.com', type: 'cookie', description: 'GA', vendor: 'Google' },
        { name: '_gid', domain: '.example.com', type: 'cookie', description: 'GA', vendor: 'Google' },
      ],
    },
    {
      slug: 'marketing',
      name: 'Marketing',
      description: 'Ads.',
      locked: false,
      cookies: [],
    },
  ],
};

const T = {
  rejectAll: 'Reject all',
  acceptAll: 'Accept all',
  savePreferences: 'Save preferences',
} as unknown as TranslationStrings;

function stubFetchOk(payload: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => payload })),
  );
}

describe('renderCookiesWidget', () => {
  let host: HTMLElement;
  let onSave: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    onSave = vi.fn();
    stubFetchOk(SAMPLE_PAYLOAD);
    document.getElementById('consentos-cookies-widget-styles')?.remove();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.querySelectorAll('style#consentos-cookies-widget-styles').forEach((s) => s.remove());
    vi.unstubAllGlobals();
  });

  it('mounts a category card per enabled category', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    expect(host.querySelectorAll('.cmp-category')).toHaveLength(3);
    expect(host.querySelector('[data-category-row="necessary"]')).not.toBeNull();
    expect(host.querySelector('[data-category-row="analytics"]')).not.toBeNull();
    expect(host.querySelector('[data-category-row="marketing"]')).not.toBeNull();
  });

  it('renders the cookie count in the summary and skips empty categories', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    const analyticsCard = host.querySelector('[data-category-row="analytics"]')!;
    expect(analyticsCard.querySelector('summary')!.textContent).toContain('2 cookies in this category');
    const marketingCard = host.querySelector('[data-category-row="marketing"]')!;
    expect(marketingCard.querySelector('details')).toBeNull();
  });

  it('shows "Always active" for locked categories instead of a toggle', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    const necessary = host.querySelector('[data-category-row="necessary"]')!;
    expect(necessary.querySelector('.cmp-category__always')!.textContent).toContain('Always active');
    expect(necessary.querySelector('input[type="checkbox"]')).toBeNull();
  });

  it('pre-checks the toggle for currently-accepted categories', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary', 'analytics'] as CategorySlug[],
      onSave,
    });
    const analyticsCheckbox = host.querySelector<HTMLInputElement>(
      'input[data-category="analytics"]',
    )!;
    const marketingCheckbox = host.querySelector<HTMLInputElement>(
      'input[data-category="marketing"]',
    )!;
    expect(analyticsCheckbox.checked).toBe(true);
    expect(marketingCheckbox.checked).toBe(false);
  });

  it('Accept all calls onSave with every non-essential slug', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    host.querySelector<HTMLButtonElement>('button[data-action="accept"]')!.click();
    expect(onSave).toHaveBeenCalledTimes(1);
    const [accepted, rejected] = onSave.mock.calls[0];
    expect(accepted).toEqual(expect.arrayContaining(['necessary', 'analytics', 'marketing']));
    expect(rejected).toEqual([]);
  });

  it('Reject all calls onSave with necessary only and all others rejected', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary', 'analytics'] as CategorySlug[],
      onSave,
    });
    host.querySelector<HTMLButtonElement>('button[data-action="reject"]')!.click();
    const [accepted, rejected] = onSave.mock.calls[0];
    expect(accepted).toEqual(['necessary']);
    expect(rejected).toEqual(expect.arrayContaining(['analytics', 'marketing']));
  });

  it('Save preferences reflects the toggle state at click time', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    const analyticsCheckbox = host.querySelector<HTMLInputElement>(
      'input[data-category="analytics"]',
    )!;
    analyticsCheckbox.checked = true;
    host.querySelector<HTMLButtonElement>('button[data-action="save"]')!.click();
    const [accepted, rejected] = onSave.mock.calls[0];
    expect(accepted).toEqual(expect.arrayContaining(['necessary', 'analytics']));
    expect(rejected).toEqual(['marketing']);
  });

  it('auto-discovers a [data-consentos-cookies] target when none is passed', async () => {
    host.setAttribute('data-consentos-cookies', '');
    await renderCookiesWidget({
      target: undefined,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    expect(host.querySelectorAll('.cmp-category')).toHaveLength(3);
  });

  it('injects styles once even across multiple renders', async () => {
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    expect(document.head.querySelectorAll('style#consentos-cookies-widget-styles')).toHaveLength(1);
  });

  it('logs and bails when the fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    await renderCookiesWidget({
      target: host,
      apiBase: 'http://api',
      siteId: 'site-A',
      t: T,
      currentAccepted: ['necessary'] as CategorySlug[],
      onSave,
    });
    expect(host.querySelectorAll('.cmp-category')).toHaveLength(0);
    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
