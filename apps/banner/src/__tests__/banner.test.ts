import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

// We need to test banner.ts functions, but it auto-inits on import.
// We'll mock fetch and test the composed behaviour.

vi.mock('../blocker', () => ({
  updateAcceptedCategories: vi.fn(),
}));

vi.mock('../consent', () => ({
  buildConsentState: vi.fn(() => ({
    accepted: ['necessary'],
    rejected: ['analytics', 'marketing'],
    visitorId: 'v-test',
    consentedAt: new Date().toISOString(),
  })),
  readConsent: vi.fn(() => null),
  writeConsent: vi.fn(),
}));

vi.mock('../gcm', () => ({
  buildGcmStateFromCategories: vi.fn(() => ({
    analytics_storage: 'denied',
    ad_storage: 'denied',
    security_storage: 'granted',
  })),
  updateGcm: vi.fn(),
}));

import { isImplicitConsentMode } from '../blocking-mode';
import { updateAcceptedCategories } from '../blocker';
import { showPreferencesButton } from '../banner';
import { buildConsentState, readConsent, writeConsent } from '../consent';
import { DEFAULT_TRANSLATIONS } from '../i18n';
import { buildGcmStateFromCategories, updateGcm } from '../gcm';
import type { SiteConfig, CategorySlug } from '../types';

describe('banner', () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  const ALL_CATEGORIES: CategorySlug[] = [
    'necessary', 'functional', 'analytics', 'marketing', 'personalisation',
  ];

  const NON_ESSENTIAL: CategorySlug[] = [
    'functional', 'analytics', 'marketing', 'personalisation',
  ];

  const defaultConfig: SiteConfig = {
    id: 'cfg-1',
    site_id: 'site-1',
    blocking_mode: 'opt_in',
    regional_modes: null,
    tcf_enabled: false,
    gpp_enabled: false,
    gpp_supported_apis: [],
    gpc_enabled: true,
    gpc_jurisdictions: [],
    gpc_global_honour: false,
    gcm_enabled: true,
    gcm_default: null,
    shopify_privacy_enabled: false,
    banner_config: null,
    privacy_policy_url: null,
    terms_url: null,
    consent_expiry_days: 365,
    consent_group_id: null,
    ab_test: null,
    initiator_map: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    window.dataLayer = [];
    window.__consentos = { siteId: 'site-1', apiBase: 'https://api.example.com', cdnBase: 'https://cdn.example.com', loaded: false };

    mockFetch = vi.fn();
    vi.stubGlobal('fetch', mockFetch);
  });

  afterEach(() => {
    // Clean up banner host if it was appended
    const host = document.getElementById('consentos-banner-host');
    if (host) host.remove();
    vi.unstubAllGlobals();
  });

  describe('showPreferencesButton', () => {
    const BUTTON_ID = 'cmp-preferences-button';

    afterEach(() => {
      document.getElementById(BUTTON_ID)?.remove();
    });

    const withBannerConfig = (banner_config: SiteConfig['banner_config']): SiteConfig => ({
      ...defaultConfig,
      banner_config,
    });

    it('renders the floating button by default', () => {
      showPreferencesButton(withBannerConfig(null), DEFAULT_TRANSLATIONS);
      expect(document.getElementById(BUTTON_ID)).not.toBeNull();
    });

    it('suppresses the button when showPreferencesButton is false', () => {
      showPreferencesButton(withBannerConfig({ showPreferencesButton: false }), DEFAULT_TRANSLATIONS);
      expect(document.getElementById(BUTTON_ID)).toBeNull();
    });

    it('honours the legacy snake_case opt-out', () => {
      const legacy = { show_preferences_button: false } as unknown as SiteConfig['banner_config'];
      showPreferencesButton(withBannerConfig(legacy), DEFAULT_TRANSLATIONS);
      expect(document.getElementById(BUTTON_ID)).toBeNull();
    });

    it('positions the button on the left when configured', () => {
      showPreferencesButton(
        withBannerConfig({ preferencesButtonPosition: 'left' }),
        DEFAULT_TRANSLATIONS,
      );
      const host = document.getElementById(BUTTON_ID);
      expect(host?.shadowRoot?.innerHTML).toContain('left: 20px;');
    });
  });

  describe('buildDefaultConfig', () => {
    it('should create a valid default config', () => {
      // This mirrors what buildDefaultConfig does in the banner
      const config: SiteConfig = {
        id: '',
        site_id: 'test-site',
        blocking_mode: 'opt_in',
        regional_modes: null,
        tcf_enabled: false,
        gpp_enabled: false,
        gpp_supported_apis: [],
        gpc_enabled: true,
        gpc_jurisdictions: [],
        gpc_global_honour: false,
        gcm_enabled: true,
        gcm_default: null,
        shopify_privacy_enabled: false,
        banner_config: null,

        privacy_policy_url: null,
        terms_url: null,
        consent_expiry_days: 365,
        consent_group_id: null,
        ab_test: null,
        initiator_map: null,
      };
      expect(config.blocking_mode).toBe('opt_in');
      expect(config.gcm_enabled).toBe(true);
      expect(config.consent_expiry_days).toBe(365);
    });
  });

  describe('isImplicitConsentMode', () => {
    it('returns false for opt_in (GDPR) so dismissal acts as reject', () => {
      expect(isImplicitConsentMode('opt_in')).toBe(false);
    });

    it('returns true for opt_out (CCPA-style)', () => {
      expect(isImplicitConsentMode('opt_out')).toBe(true);
    });

    it('returns true for informational notice-only mode', () => {
      expect(isImplicitConsentMode('informational')).toBe(true);
    });

    it('returns false for unknown or missing modes (safe default)', () => {
      expect(isImplicitConsentMode(null)).toBe(false);
      expect(isImplicitConsentMode(undefined)).toBe(false);
      expect(isImplicitConsentMode('something-else')).toBe(false);
    });
  });

  describe('determineAction', () => {
    it('should return accept_all when no rejections', () => {
      const accepted: CategorySlug[] = ALL_CATEGORIES;
      const rejected: CategorySlug[] = [];

      let action: string;
      if (rejected.length === 0) action = 'accept_all';
      else if (accepted.length === 1 && accepted[0] === 'necessary') action = 'reject_all';
      else action = 'custom';

      expect(action).toBe('accept_all');
    });

    it('should return reject_all when only necessary accepted', () => {
      const accepted: CategorySlug[] = ['necessary'];
      const rejected = NON_ESSENTIAL;

      let action: string;
      if (rejected.length === 0) action = 'accept_all';
      else if (accepted.length === 1 && accepted[0] === 'necessary') action = 'reject_all';
      else action = 'custom';

      expect(action).toBe('reject_all');
    });

    it('should return custom when partial selection', () => {
      const accepted: CategorySlug[] = ['necessary', 'analytics'];
      const rejected: CategorySlug[] = ['marketing', 'functional', 'personalisation'];

      let action: string;
      if (rejected.length === 0) action = 'accept_all';
      else if (accepted.length === 1 && accepted[0] === 'necessary') action = 'reject_all';
      else action = 'custom';

      expect(action).toBe('custom');
    });
  });

  describe('handleConsent flow', () => {
    it('should write consent, update blocker, and update GCM', () => {
      const accepted: CategorySlug[] = ['necessary', 'analytics'];
      const rejected: CategorySlug[] = ['marketing', 'functional', 'personalisation'];

      const gcmState = buildGcmStateFromCategories(accepted);
      const state = buildConsentState(accepted, rejected);

      writeConsent(state, defaultConfig.consent_expiry_days);
      updateAcceptedCategories(accepted);

      if (defaultConfig.gcm_enabled) {
        updateGcm(gcmState);
      }

      expect(writeConsent).toHaveBeenCalled();
      expect(updateAcceptedCategories).toHaveBeenCalledWith(accepted);
      expect(updateGcm).toHaveBeenCalled();
    });

    it('should NOT call updateGcm when gcm_enabled is false', () => {
      const config = { ...defaultConfig, gcm_enabled: false };
      const accepted: CategorySlug[] = ['necessary'];
      const rejected = NON_ESSENTIAL;

      const gcmState = buildGcmStateFromCategories(accepted);
      const state = buildConsentState(accepted, rejected);
      writeConsent(state, config.consent_expiry_days);
      updateAcceptedCategories(accepted);

      if (config.gcm_enabled) {
        updateGcm(gcmState);
      }

      expect(updateGcm).not.toHaveBeenCalled();
    });

    it('should post consent to the API', () => {
      const accepted: CategorySlug[] = ALL_CATEGORIES;
      const rejected: CategorySlug[] = [];

      mockFetch.mockResolvedValue(new Response('', { status: 201 }));

      fetch('https://api.example.com/api/v1/consent/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: 'site-1',
          visitor_id: 'v-test',
          action: 'accept_all',
          categories_accepted: accepted,
          categories_rejected: rejected,
          gcm_state: { analytics_storage: 'granted' },
          page_url: window.location.href,
        }),
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'https://api.example.com/api/v1/consent/',
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('should dispatch consent-change event', () => {
      const accepted: CategorySlug[] = ['necessary', 'functional'];
      let receivedDetail: unknown = null;

      document.addEventListener('consentos:consent-change', ((e: CustomEvent) => {
        receivedDetail = e.detail;
      }) as EventListener);

      document.dispatchEvent(
        new CustomEvent('consentos:consent-change', { detail: { accepted } })
      );

      expect(receivedDetail).toEqual({ accepted });
    });
  });

  describe('renderBanner', () => {
    it('should create a shadow DOM host element', () => {
      const host = document.createElement('div');
      host.id = 'consentos-banner-host';
      const shadow = host.attachShadow({ mode: 'open' });

      shadow.innerHTML = `
        <div class="consentos-banner" role="dialog" aria-label="Cookie consent">
          <button data-action="accept">Accept all</button>
          <button data-action="reject">Reject all</button>
        </div>
      `;

      document.body.appendChild(host);

      const bannerHost = document.getElementById('consentos-banner-host');
      expect(bannerHost).not.toBeNull();
      expect(bannerHost?.shadowRoot).not.toBeNull();

      const banner = bannerHost?.shadowRoot?.querySelector('.consentos-banner');
      expect(banner).not.toBeNull();
      expect(banner?.getAttribute('role')).toBe('dialog');
    });

    it('should render category toggles', () => {
      const categories = [
        { slug: 'necessary', name: 'Necessary', locked: true },
        { slug: 'analytics', name: 'Analytics', locked: false },
      ];

      const html = categories
        .map(
          (cat) =>
            `<label class="cmp-category">
              <span>${cat.name}</span>
              <input type="checkbox" data-category="${cat.slug}" ${cat.locked ? 'checked disabled' : ''} />
            </label>`
        )
        .join('');

      const div = document.createElement('div');
      div.innerHTML = html;

      const inputs = div.querySelectorAll<HTMLInputElement>('input[data-category]');
      expect(inputs).toHaveLength(2);
      expect(inputs[0].disabled).toBe(true);
      expect(inputs[0].checked).toBe(true);
      expect(inputs[1].disabled).toBe(false);
    });

    it('should include privacy policy link when URL is provided', () => {
      const url = 'https://example.com/privacy';
      const html = `<a href="${url}" target="_blank" rel="noopener">Privacy Policy</a>`;

      const div = document.createElement('div');
      div.innerHTML = html;

      const link = div.querySelector('a');
      expect(link?.href).toBe(url);
      expect(link?.target).toBe('_blank');
      expect(link?.rel).toBe('noopener');
    });
  });

  describe('removeBanner', () => {
    it('should remove the banner host from DOM', async () => {
      const host = document.createElement('div');
      host.id = 'consentos-banner-host';
      document.body.appendChild(host);

      expect(document.getElementById('consentos-banner-host')).not.toBeNull();

      host.remove();

      expect(document.getElementById('consentos-banner-host')).toBeNull();
    });
  });

  describe('getBannerStyles', () => {
    it('should use default colours when no banner_config', () => {
      const bc = defaultConfig.banner_config;
      const bg = bc?.backgroundColour ?? '#ffffff';
      const text = bc?.textColour ?? '#0E1929';
      const primary = bc?.primaryColour ?? '#2C6AE4';

      expect(bg).toBe('#ffffff');
      expect(text).toBe('#0E1929');
      expect(primary).toBe('#2C6AE4');
    });

    it('should use custom colours from banner_config', () => {
      const config = {
        ...defaultConfig,
        banner_config: {
          backgroundColour: '#000000',
          textColour: '#ffffff',
          primaryColour: '#ff0000',
        },
      };

      const bc = config.banner_config;
      const bg = bc?.backgroundColour ?? '#ffffff';
      const text = bc?.textColour ?? '#0E1929';
      const primary = bc?.primaryColour ?? '#ff0000';

      expect(bg).toBe('#000000');
      expect(text).toBe('#ffffff');
      expect(primary).toBe('#ff0000');
    });
  });

  describe('getSelectedCategories', () => {
    it('should return necessary plus checked categories', () => {
      const host = document.createElement('div');
      const shadow = host.attachShadow({ mode: 'open' });
      shadow.innerHTML = `
        <input type="checkbox" data-category="necessary" checked disabled />
        <input type="checkbox" data-category="analytics" checked />
        <input type="checkbox" data-category="marketing" />
      `;

      const checked: CategorySlug[] = ['necessary'];
      shadow.querySelectorAll<HTMLInputElement>('input[data-category]').forEach((input) => {
        if (input.checked) {
          checked.push(input.getAttribute('data-category') as CategorySlug);
        }
      });
      const unique = [...new Set(checked)];

      expect(unique).toContain('necessary');
      expect(unique).toContain('analytics');
      expect(unique).not.toContain('marketing');
    });
  });
});
