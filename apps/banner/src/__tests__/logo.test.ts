/**
 * Tests for the runtime banner logo rendering (``renderLogo``).
 *
 * Regression guard: the logo config (``showLogo`` / ``logoUrl`` /
 * ``logoHeight``) was previously honoured by the admin preview but
 * silently ignored by the real banner, so a configured logo never
 * appeared on the live site.
 *
 * ``banner.ts`` runs ``init()`` at import time, so — following the
 * ``blocker-bridge`` test — we seed ``window.__consentos`` and mock the
 * modules ``banner.ts`` pulls in so importing it here is side-effect free.
 */

import { describe, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  (globalThis as any).window = (globalThis as any).window || globalThis;
  (globalThis as any).window.__consentos = {
    siteId: '',
    apiBase: '',
    cdnBase: '',
    loaded: false,
  };
});

vi.mock('../consent', () => ({
  buildConsentState: vi.fn(() => ({ accepted: [], rejected: [] })),
  readConsent: vi.fn(() => null),
  writeConsent: vi.fn(),
}));

vi.mock('../gcm', () => ({
  buildGcmStateFromCategories: vi.fn(() => ({})),
  updateGcm: vi.fn(),
}));

vi.mock('../i18n', () => ({
  DEFAULT_TRANSLATIONS: {},
  detectLocale: vi.fn(() => 'en'),
  interpolate: vi.fn((s: string) => s),
  loadTranslations: vi.fn(async () => ({})),
  renderLinks: vi.fn((s: string) => s),
}));

vi.mock('../a11y', () => ({
  announce: vi.fn(),
  createLiveRegion: vi.fn(),
  focusFirst: vi.fn(),
  onEscape: vi.fn(() => () => {}),
  prefersReducedMotion: vi.fn(() => false),
  trapFocus: vi.fn(() => () => {}),
}));

vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('mocked'))));

import { getBannerStyles, renderLogo } from '../banner';
import type { BannerConfig, SiteConfig } from '../types';

function configWith(banner: Partial<BannerConfig> | null): SiteConfig {
  return { banner_config: banner as BannerConfig | null } as SiteConfig;
}

describe('renderLogo', () => {
  it('renders nothing when there is no banner config', () => {
    expect(renderLogo(configWith(null))).toBe('');
  });

  it('renders nothing when showLogo is false', () => {
    expect(renderLogo(configWith({ showLogo: false, logoUrl: 'https://x.test/l.svg' }))).toBe('');
  });

  it('renders nothing when showLogo is true but logoUrl is missing', () => {
    expect(renderLogo(configWith({ showLogo: true }))).toBe('');
  });

  it('renders an img when enabled with a URL', () => {
    const html = renderLogo(configWith({ showLogo: true, logoUrl: 'https://x.test/l.svg' }));
    expect(html).toContain('<img');
    expect(html).toContain('src="https://x.test/l.svg"');
    expect(html).toContain('class="cmp-logo"');
  });

  it('defaults to a 28px height when none is configured', () => {
    const html = renderLogo(configWith({ showLogo: true, logoUrl: 'https://x.test/l.svg' }));
    expect(html).toContain('height:28px');
  });

  it('honours a configured logo height', () => {
    const html = renderLogo(configWith({ showLogo: true, logoUrl: 'https://x.test/l.svg', logoHeight: 64 }));
    expect(html).toContain('height:64px');
  });

  it('clamps the height to the allowed range', () => {
    const tooSmall = renderLogo(configWith({ showLogo: true, logoUrl: 'https://x.test/l.svg', logoHeight: 1 }));
    const tooLarge = renderLogo(configWith({ showLogo: true, logoUrl: 'https://x.test/l.svg', logoHeight: 9999 }));
    expect(tooSmall).toContain('height:12px');
    expect(tooLarge).toContain('height:120px');
  });

  it('escapes HTML in the logo URL', () => {
    const html = renderLogo(
      configWith({ showLogo: true, logoUrl: 'https://x.test/l.svg?a=1&b="><script>' }),
    );
    expect(html).not.toContain('"><script>');
    expect(html).toContain('&amp;');
    expect(html).toContain('&quot;');
    expect(html).toContain('&lt;');
  });
});

describe('overlay backdrop', () => {
  it('shows the backdrop scrim in overlay mode', () => {
    const css = getBannerStyles(configWith({ displayMode: 'overlay' }));
    expect(css).toContain('.cmp-overlay-bg');
    // The scrim must be visible (block) and dim the page behind the modal.
    expect(css).toMatch(/\.cmp-overlay-bg\s*\{[^}]*display:\s*block/);
    expect(css).toContain('rgba(0, 0, 0, 0.4)');
  });

  it('hides the backdrop scrim in non-overlay modes', () => {
    for (const mode of ['bottom_banner', 'top_banner', 'corner_popup'] as const) {
      const css = getBannerStyles(configWith({ displayMode: mode }));
      expect(css).toMatch(/\.cmp-overlay-bg\s*\{[^}]*display:\s*none/);
    }
  });

  it('hides the backdrop when explicitly disabled in overlay mode', () => {
    const css = getBannerStyles(configWith({ displayMode: 'overlay', showOverlayBackdrop: false }));
    expect(css).toMatch(/\.cmp-overlay-bg\s*\{[^}]*display:\s*none/);
  });

  it('keeps the backdrop when the flag is left unset (defaults on)', () => {
    const css = getBannerStyles(configWith({ displayMode: 'overlay', showOverlayBackdrop: true }));
    expect(css).toMatch(/\.cmp-overlay-bg\s*\{[^}]*display:\s*block/);
  });
});

describe('banner width', () => {
  it('defaults the overlay modal to 600px when unset', () => {
    const css = getBannerStyles(configWith({ displayMode: 'overlay' }));
    expect(css).toContain('max-width: 600px');
  });

  it('honours a configured width on the overlay modal', () => {
    const css = getBannerStyles(configWith({ displayMode: 'overlay', bannerWidth: 480 }));
    expect(css).toContain('max-width: 480px');
  });

  it('leaves the corner popup at its own fixed width', () => {
    const css = getBannerStyles(configWith({ displayMode: 'corner_popup', bannerWidth: 360 }));
    expect(css).toContain('width: 380px');
    expect(css).not.toContain('360px');
  });

  it('clamps the width to the allowed range', () => {
    const tooSmall = getBannerStyles(configWith({ displayMode: 'overlay', bannerWidth: 10 }));
    const tooLarge = getBannerStyles(configWith({ displayMode: 'overlay', bannerWidth: 9999 }));
    expect(tooSmall).toContain('max-width: 280px');
    expect(tooLarge).toContain('max-width: 960px');
  });
});
