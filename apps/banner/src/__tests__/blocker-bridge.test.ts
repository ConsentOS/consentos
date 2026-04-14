/**
 * Tests for the loader ↔ bundle blocker bridge.
 *
 * ``consent-loader.js`` and ``consent-bundle.js`` are compiled as
 * separate rollup IIFEs, so each one inlines its own copy of
 * ``blocker.ts`` with private module state. The bundle therefore
 * can't reach the loader's ``acceptedCategories`` set via a direct
 * import — it has to call through ``window.__consentos._updateBlocker``,
 * which the loader sets after ``installBlocker()``.
 *
 * We mock the imports the banner module pulls in so importing
 * ``banner.ts`` here doesn't try to hit real network / timers.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

// Seed ``window.__consentos`` before banner.ts's init() IIFE runs at
// import time. Without this, destructuring ``window.__consentos`` at
// the top of init() throws and fills the test output with noise.
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

// Prevent banner.ts's init() IIFE from running against real globals.
vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('mocked'))));

import { updateAcceptedCategories } from '../banner';

describe('loader ↔ bundle blocker bridge', () => {
  beforeEach(() => {
    window.__consentos = {
      siteId: 'test',
      apiBase: 'https://api.example.com',
      cdnBase: 'https://cdn.example.com',
      loaded: false,
    };
  });

  it('calls window.__consentos._updateBlocker when the bridge is present', () => {
    const bridge = vi.fn();
    window.__consentos._updateBlocker = bridge;

    updateAcceptedCategories(['necessary', 'analytics']);

    expect(bridge).toHaveBeenCalledTimes(1);
    expect(bridge).toHaveBeenCalledWith(['necessary', 'analytics']);
  });

  it('forwards the exact array reference so the loader sees every slug', () => {
    const bridge = vi.fn();
    window.__consentos._updateBlocker = bridge;

    const accepted = ['necessary', 'functional', 'marketing'] as const;
    updateAcceptedCategories([...accepted]);

    const args = bridge.mock.calls[0][0];
    expect(args).toEqual(['necessary', 'functional', 'marketing']);
  });

  it('warns and returns cleanly when the bridge is missing', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    delete window.__consentos._updateBlocker;

    expect(() => updateAcceptedCategories(['necessary'])).not.toThrow();
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('blocker bridge missing'),
    );

    warn.mockRestore();
  });

  it('warns when window.__consentos is missing entirely', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    // @ts-expect-error — simulating a pre-init state
    window.__consentos = undefined;

    expect(() => updateAcceptedCategories(['necessary'])).not.toThrow();
    expect(warn).toHaveBeenCalled();

    warn.mockRestore();
  });
});
