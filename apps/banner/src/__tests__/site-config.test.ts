import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchSiteConfig, previewToken } from '../site-config';
import type { SiteConfig } from '../types';

const DEFAULTS = { id: '', site_id: 'site-1' } as SiteConfig;
const fallback = () => DEFAULTS;

function stubFetch(response: Partial<Response> | Error) {
  const fetchMock = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function visit(search: string) {
  window.history.replaceState(null, '', `/${search}`);
}

describe('fetchSiteConfig', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
    visit('');
  });

  it('returns the published config', async () => {
    const published = { id: 'consent-v1', site_id: 'site-1' };
    const fetchMock = stubFetch({ ok: true, status: 200, json: async () => published });

    const config = await fetchSiteConfig('https://api.test', 'site-1', 'en-GB', fallback);

    expect(config).toEqual(published);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.test/api/v1/config/sites/site-1/geo-resolved?locale=en-GB',
    );
  });

  it('uses the defaults quietly when the site is not published yet', async () => {
    stubFetch({ ok: false, status: 404 });
    const info = vi.spyOn(console, 'info').mockImplementation(() => {});
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(await fetchSiteConfig('', 'site-1', 'en', fallback)).toBe(DEFAULTS);
    expect(info).toHaveBeenCalledWith(expect.stringContaining('has not been published yet'));
    expect(error).not.toHaveBeenCalled();
  });

  it('reports other failures as errors', async () => {
    stubFetch({ ok: false, status: 500 });
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(await fetchSiteConfig('', 'site-1', 'en', fallback)).toBe(DEFAULTS);
    expect(error).toHaveBeenCalled();
  });

  it('survives a network failure', async () => {
    stubFetch(new Error('offline'));
    vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(await fetchSiteConfig('', 'site-1', 'en', fallback)).toBe(DEFAULTS);
  });

  it('asks for the draft while a preview link is in use', async () => {
    visit('?consentos_preview=tok-1');
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      json: async () => ({ id: 'preview', preview: true }),
    });
    vi.spyOn(console, 'info').mockImplementation(() => {});

    const config = await fetchSiteConfig('', 'site-1', 'en', fallback);

    expect(config.preview).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/config/sites/site-1/geo-resolved?locale=en&preview=tok-1',
    );
    // The preview carries on as the holder moves around the site.
    visit('');
    expect(previewToken()).toBe('tok-1');
  });

  it('ends the preview when the link has expired', async () => {
    visit('?consentos_preview=old');
    stubFetch({ ok: true, status: 200, json: async () => ({ id: 'live' }) });

    await fetchSiteConfig('', 'site-1', 'en', fallback);

    visit('');
    expect(previewToken()).toBeNull();
  });
});

describe('previewToken', () => {
  afterEach(() => {
    sessionStorage.clear();
    visit('');
  });

  it('is empty without a link', () => {
    expect(previewToken()).toBeNull();
  });

  it('can be turned off', () => {
    visit('?consentos_preview=tok-1');
    previewToken();
    visit('?consentos_preview=off');
    expect(previewToken()).toBeNull();
    visit('');
    expect(previewToken()).toBeNull();
  });
});
