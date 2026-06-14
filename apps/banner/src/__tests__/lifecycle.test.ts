/**
 * Tests for the banner lifecycle events and cross-tab consent sync.
 *
 * Covers:
 *   - ``consentos:banner-shown`` fires with the right ``detail.trigger``
 *     when ``renderBanner`` is invoked.
 *   - ``consentos:banner-closed`` fires with the right ``detail.reason``
 *     when ``removeBanner`` runs.
 *   - ``broadcastConsentChange`` posts a properly-shaped message on the
 *     ``consentos`` BroadcastChannel.
 *   - A remote message dispatches ``consentos:consent-synced`` and does
 *     NOT fire ``consent-change`` or push to ``dataLayer``.
 *   - Loopback messages (same tab) and cross-site messages are ignored.
 *
 * Mirrors the dependency-mock layout used by ``logo.test.ts`` so the
 * top-level ``init()`` in ``banner.ts`` is side-effect free at import.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  (globalThis as any).window = (globalThis as any).window || globalThis;
  (globalThis as any).window.__consentos = {
    siteId: 'site-A',
    apiBase: '',
    cdnBase: '',
    loaded: false,
    _updateBlocker: () => {},
  };
});

vi.mock('../blocker', () => ({
  updateAcceptedCategories: vi.fn(),
}));

vi.mock('../consent', () => ({
  buildConsentState: vi.fn(() => ({ accepted: [], rejected: [] })),
  readConsent: vi.fn(() => ({ accepted: ['necessary'] })),
  writeConsent: vi.fn(),
}));

vi.mock('../gcm', () => ({
  buildGcmStateFromCategories: vi.fn((cats: string[]) => ({ cats })),
  updateGcm: vi.fn(),
}));

vi.mock('../i18n', () => ({
  DEFAULT_TRANSLATIONS: {},
  detectLocale: vi.fn(() => 'en'),
  interpolate: vi.fn((s: string) => s),
  selectTranslations: vi.fn(() => ({})),
  renderLinks: vi.fn((s: string) => s),
}));

vi.mock('../a11y', () => ({
  announce: vi.fn(),
  createLiveRegion: vi.fn(),
  focusFirst: vi.fn(),
  onEscape: vi.fn(() => () => {}),
  prefersReducedMotion: vi.fn(() => true),
  trapFocus: vi.fn(() => () => {}),
}));

vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('mocked'))));

interface MockBroadcastInstance {
  name: string;
  postMessage: ReturnType<typeof vi.fn>;
  listeners: Array<(e: MessageEvent) => void>;
  close: () => void;
}

const mockChannels: MockBroadcastInstance[] = [];

class MockBroadcastChannel {
  name: string;
  postMessage = vi.fn();
  listeners: Array<(e: MessageEvent) => void> = [];
  constructor(name: string) {
    this.name = name;
    mockChannels.push(this as unknown as MockBroadcastInstance);
  }
  addEventListener(_type: string, listener: (e: MessageEvent) => void): void {
    this.listeners.push(listener);
  }
  removeEventListener(): void {}
  close(): void {}
}

vi.stubGlobal('BroadcastChannel', MockBroadcastChannel);

import { updateGcm } from '../gcm';
import {
  applyRemoteConsent,
  broadcastConsentChange,
  initCrossTabSync,
  removeBanner,
  renderBanner,
  showPreferencesButton,
} from '../banner';
import type { TranslationStrings } from '../i18n';
import type { BannerConfig, SiteConfig } from '../types';

const mockUpdateGcm = vi.mocked(updateGcm);
let mockBlockerBridge: ReturnType<typeof vi.fn>;

function makeConfig(overrides?: Partial<SiteConfig>): SiteConfig {
  return {
    banner_config: {} as BannerConfig,
    gcm_enabled: true,
    enabled_categories: ['necessary', 'analytics'],
    ...overrides,
  } as SiteConfig;
}

const T = {
  title: 't',
  description: 'd',
  acceptAll: 'a',
  rejectAll: 'r',
  managePreferences: 'm',
  savePreferences: 's',
  categoryNecessary: 'n',
  categoryNecessaryDesc: 'nd',
  categoryAnalytics: 'an',
  categoryAnalyticsDesc: 'ad',
  cookieCount: '{{count}}',
} as unknown as TranslationStrings;

function withListener<T>(eventName: string, fn: () => T): { result: T; events: CustomEvent[] } {
  const events: CustomEvent[] = [];
  const handler = (e: Event) => events.push(e as CustomEvent);
  document.addEventListener(eventName, handler);
  try {
    return { result: fn(), events };
  } finally {
    document.removeEventListener(eventName, handler);
  }
}

describe('banner-shown event', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('defaults the trigger to "initial"', () => {
    const { events } = withListener('consentos:banner-shown', () => {
      renderBanner(makeConfig(), T);
    });
    expect(events).toHaveLength(1);
    expect(events[0].detail).toEqual({ trigger: 'initial' });
  });

  it('passes "sdk" when re-opened via the preferences flow', () => {
    const { events } = withListener('consentos:banner-shown', () => {
      renderBanner(makeConfig(), T, undefined, null, undefined, 'sdk');
    });
    expect(events[0].detail).toEqual({ trigger: 'sdk' });
  });

  it('passes "implicit" for opt-out / informational auto-render', () => {
    const { events } = withListener('consentos:banner-shown', () => {
      renderBanner(makeConfig(), T, undefined, null, undefined, 'implicit');
    });
    expect(events[0].detail).toEqual({ trigger: 'implicit' });
  });
});

describe('banner-closed event', () => {
  let host: HTMLElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it.each<['accept-all' | 'reject-all' | 'save-preferences' | 'dismissed']>([
    ['accept-all'],
    ['reject-all'],
    ['save-preferences'],
    ['dismissed'],
  ])('emits reason %s', (reason) => {
    const { events } = withListener('consentos:banner-closed', () => {
      removeBanner(host, reason);
    });
    expect(events).toHaveLength(1);
    expect(events[0].detail).toEqual({ reason });
  });
});

describe('floating preferences button', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('mounts a host element with the conventional id', () => {
    showPreferencesButton(makeConfig(), T);
    expect(document.getElementById('cmp-preferences-button')).not.toBeNull();
  });

  it('replaces the existing host on re-invocation', () => {
    showPreferencesButton(makeConfig(), T);
    const first = document.getElementById('cmp-preferences-button');
    showPreferencesButton(makeConfig(), T);
    const second = document.getElementById('cmp-preferences-button');
    expect(second).not.toBeNull();
    expect(second).not.toBe(first);
    expect(document.querySelectorAll('#cmp-preferences-button')).toHaveLength(1);
  });

  it('renders nothing when banner_config.show_preferences_button is false', () => {
    const config = makeConfig({
      banner_config: { show_preferences_button: false } as unknown as BannerConfig,
    });
    showPreferencesButton(config, T);
    expect(document.getElementById('cmp-preferences-button')).toBeNull();
  });
});

describe('cross-tab consent sync', () => {
  beforeEach(() => {
    mockChannels.length = 0;
    mockUpdateGcm.mockClear();
    mockBlockerBridge = vi.fn();
    (window as any).__consentos._updateBlocker = mockBlockerBridge;
    (window as unknown as { dataLayer?: unknown[] }).dataLayer = [];
  });

  afterEach(() => {
    delete (window as unknown as { dataLayer?: unknown[] }).dataLayer;
  });

  it('opens a "consentos" BroadcastChannel on init', () => {
    initCrossTabSync(makeConfig());
    expect(mockChannels).toHaveLength(1);
    expect(mockChannels[0].name).toBe('consentos');
    expect(mockChannels[0].listeners).toHaveLength(1);
  });

  it('broadcastConsentChange posts a typed message with the site id', () => {
    initCrossTabSync(makeConfig());
    broadcastConsentChange(['necessary', 'analytics']);
    expect(mockChannels[0].postMessage).toHaveBeenCalledTimes(1);
    const message = mockChannels[0].postMessage.mock.calls[0][0];
    expect(message).toMatchObject({
      type: 'consentos:cross-tab-sync',
      accepted: ['necessary', 'analytics'],
      siteId: 'site-A',
    });
    expect(typeof message.source).toBe('string');
    expect(message.source.length).toBeGreaterThan(0);
  });

  it('a remote message dispatches consent-synced and never consent-change or dataLayer', () => {
    initCrossTabSync(makeConfig());
    const synced: CustomEvent[] = [];
    const local: CustomEvent[] = [];
    const onSynced = (e: Event) => synced.push(e as CustomEvent);
    const onLocal = (e: Event) => local.push(e as CustomEvent);
    document.addEventListener('consentos:consent-synced', onSynced);
    document.addEventListener('consentos:consent-change', onLocal);

    const listener = mockChannels[0].listeners[0];
    listener({
      data: {
        type: 'consentos:cross-tab-sync',
        accepted: ['necessary', 'analytics'],
        source: 'other-tab',
        siteId: 'site-A',
      },
    } as MessageEvent);

    expect(synced).toHaveLength(1);
    expect(synced[0].detail).toEqual({ accepted: ['necessary', 'analytics'] });
    expect(local).toHaveLength(0);
    expect((window as unknown as { dataLayer: unknown[] }).dataLayer).toHaveLength(0);
    expect(mockBlockerBridge).toHaveBeenCalledWith(['necessary', 'analytics']);
    expect(mockUpdateGcm).toHaveBeenCalled();

    document.removeEventListener('consentos:consent-synced', onSynced);
    document.removeEventListener('consentos:consent-change', onLocal);
  });

  it('ignores messages echoed back to the originating tab', () => {
    initCrossTabSync(makeConfig());
    broadcastConsentChange(['necessary']);
    const ownMessage = mockChannels[0].postMessage.mock.calls[0][0];

    const synced: CustomEvent[] = [];
    const onSynced = (e: Event) => synced.push(e as CustomEvent);
    document.addEventListener('consentos:consent-synced', onSynced);

    mockChannels[0].listeners[0]({ data: ownMessage } as MessageEvent);

    expect(synced).toHaveLength(0);
    expect(mockBlockerBridge).not.toHaveBeenCalled();

    document.removeEventListener('consentos:consent-synced', onSynced);
  });

  it('ignores messages from a different site', () => {
    initCrossTabSync(makeConfig());
    const synced: CustomEvent[] = [];
    const onSynced = (e: Event) => synced.push(e as CustomEvent);
    document.addEventListener('consentos:consent-synced', onSynced);

    mockChannels[0].listeners[0]({
      data: {
        type: 'consentos:cross-tab-sync',
        accepted: ['necessary', 'marketing'],
        source: 'other-tab',
        siteId: 'site-B',
      },
    } as MessageEvent);

    expect(synced).toHaveLength(0);
    expect(mockBlockerBridge).not.toHaveBeenCalled();

    document.removeEventListener('consentos:consent-synced', onSynced);
  });

  it('skips dispatch and state updates when the remote set matches local', () => {
    initCrossTabSync(makeConfig());
    const synced: CustomEvent[] = [];
    const onSynced = (e: Event) => synced.push(e as CustomEvent);
    document.addEventListener('consentos:consent-synced', onSynced);

    applyRemoteConsent(['necessary'], makeConfig());

    expect(synced).toHaveLength(0);
    expect(mockBlockerBridge).not.toHaveBeenCalled();
    expect(mockUpdateGcm).not.toHaveBeenCalled();

    document.removeEventListener('consentos:consent-synced', onSynced);
  });
});
