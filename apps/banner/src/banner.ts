/**
 * consent-bundle.js — Full consent banner UI with Shadow DOM isolation.
 *
 * Loaded async by consent-loader.js when no existing consent is found.
 * Fetches site config, renders the banner, handles user interaction,
 * records consent via the API.
 *
 * Enterprise features (A/B testing, GPP, GPC, profile sync, Shopify,
 * re-consent) are loaded via the EE banner extension module when present.
 */

import { announce, createLiveRegion, focusFirst, onEscape, prefersReducedMotion, trapFocus } from './a11y';
// NB: intentionally NOT importing from './blocker'. The loader already
// installed the blocker proxies in its own IIFE module scope, and
// the bundle can't share that state via a direct import — rollup
// builds ``consent-loader.js`` and ``consent-bundle.js`` as separate
// IIFEs so each one inlines its own private copy of every module.
// The loader exposes ``_updateBlocker`` on ``window.__consentos``
// for us to drive its proxies — see ``updateAcceptedCategories``
// below and ``apps/banner/src/loader.ts``.
import { buildConsentState, readConsent, writeConsent } from './consent';
import { buildGcmStateFromCategories, updateGcm } from './gcm';
import { type TranslationStrings, DEFAULT_TRANSLATIONS, detectLocale, interpolate, loadTranslations, renderLinks } from './i18n';
import type { BannerConfig, ButtonConfig, CategorySlug, SiteConfig } from './types';

/**
 * Drive the loader's blocker proxies with a new accepted-categories
 * set. Falls back to a ``console.warn`` if the bridge is missing,
 * which would mean the loader hasn't finished ``installBlocker`` yet
 * (shouldn't happen — the bundle only loads after the loader's
 * synchronous init phase). Exported for unit testing only.
 */
export function updateAcceptedCategories(accepted: CategorySlug[]): void {
  const bridge = window.__consentos?._updateBlocker;
  if (typeof bridge === 'function') {
    bridge(accepted);
  } else if (typeof console !== 'undefined') {
    console.warn(
      '[ConsentOS] blocker bridge missing — consent granted but ' +
        'cookie/script blocker state was not updated. The loader ' +
        'may not have initialised correctly.',
    );
  }
}

// -- Preference-centre closure captured during init() ---------------------

/**
 * Holds a closure that re-opens the banner for consent withdrawal.
 * Populated during ``init()`` once config and translations are loaded,
 * and invoked by ``window.ConsentOS.showPreferences()``. The floating
 * "manage cookies" button also calls through this indirection so a
 * single entry point keeps the behaviour consistent.
 */
let _openPreferences: (() => void) | null = null;

// -- EE extension hooks (no-ops in CE mode) ---------------------------------

/** Result from the A/B test assignment. */
interface ABAssignment {
  abTestId: string;
  variantId: string;
  variant: { name: string };
}

/** Result from GPC evaluation. */
interface GpcResult {
  detected: boolean;
  honoured: boolean;
}

/** EE hooks that enterprise code can override at runtime. */
interface EEHooks {
  applyABTest: (config: SiteConfig, visitorId: string) => { config: SiteConfig; assignment: ABAssignment | null };
  needsReconsent: (consent: unknown, config: SiteConfig) => { required: boolean; reasons: string[] };
  evaluateGpc: (config: SiteConfig, region: string | null) => GpcResult;
  getVisitorRegion: () => string | null;
  installGppApi: (cmpId: number, supportedApis: string[]) => void;
  setGppDisplayStatus: (status: string) => void;
  isGppApiInstalled: () => boolean;
  updateGppConsent: (gpp: unknown) => string | undefined;
  buildGppFromConsent: ((accepted: CategorySlug[], config: SiteConfig) => unknown) | null;
  identifyUser: (jwt: string, config: SiteConfig) => Promise<string[]>;
  clearIdentity: () => void;
  isIdentified: () => boolean;
  pushConsentToServer: (accepted: CategorySlug[], rejected: CategorySlug[], tc?: string, gpp?: string, gcm?: Record<string, string>) => void;
  updateShopifyConsent: (accepted: CategorySlug[]) => void;
}

/** Default no-op hooks for CE mode. */
const _hooks: EEHooks = {
  applyABTest: (config) => ({ config, assignment: null }),
  needsReconsent: () => ({ required: false, reasons: [] }),
  evaluateGpc: () => ({ detected: false, honoured: false }),
  getVisitorRegion: () => null,
  installGppApi: () => {},
  setGppDisplayStatus: () => {},
  isGppApiInstalled: () => false,
  updateGppConsent: () => undefined,
  buildGppFromConsent: null,
  identifyUser: async () => [],
  clearIdentity: () => {},
  isIdentified: () => false,
  pushConsentToServer: () => {},
  updateShopifyConsent: () => {},
};

/**
 * Register EE hooks. Called by the EE banner extension module.
 * Exposed on `window.__consentos_hooks` for the EE bundle to call.
 */
export function registerEEHooks(hooks: Partial<EEHooks>): void {
  Object.assign(_hooks, hooks);
}

// Expose for EE bundle
(window as any).__consentos_register_ee = registerEEHooks;

/**
 * Every known category, in canonical display order. Used as the
 * fallback when ``SiteConfig.enabled_categories`` isn't present in
 * the API response (older deployments) and as the reference order
 * for deduping / sorting runtime subsets.
 */
const ALL_CATEGORIES: CategorySlug[] = [
  'necessary',
  'functional',
  'analytics',
  'marketing',
  'personalisation',
];

/**
 * Return the categories the banner should render for this config.
 * ``necessary`` is always implicit and forced back in if missing;
 * unknown slugs are filtered; the result is sorted into the canonical
 * display order so toggle positions don't jump around based on the
 * cascade's insertion order. When the field is absent we return the
 * full five — matches legacy behaviour and keeps older banner
 * bundles working against an older API.
 */
function resolveEnabledCategories(config: SiteConfig): CategorySlug[] {
  const raw = config.enabled_categories;
  if (!raw || !Array.isArray(raw) || raw.length === 0) {
    return [...ALL_CATEGORIES];
  }
  const picked = new Set<CategorySlug>(
    raw.filter((slug): slug is CategorySlug =>
      (ALL_CATEGORIES as string[]).includes(slug as string),
    ),
  );
  picked.add('necessary');
  return ALL_CATEGORIES.filter((slug) => picked.has(slug));
}

/** Categories the user can toggle — everything except ``necessary``. */
function nonEssentialFor(enabled: CategorySlug[]): CategorySlug[] {
  return enabled.filter((slug) => slug !== 'necessary');
}

/** Initialise the banner. Called when the bundle loads. */
async function init(): Promise<void> {
  const { siteId, apiBase, cdnBase } = window.__consentos;
  if (!siteId) {
    console.warn('[ConsentOS] No site ID configured');
    return;
  }

  // Fetch site config — declared with let as A/B testing may replace it
  let config: SiteConfig;
  try {
    const resp = await fetch(`${apiBase}/api/v1/config/sites/${siteId}`);
    if (!resp.ok) throw new Error(`Config fetch failed: ${resp.status}`);
    config = await resp.json();
  } catch (err) {
    console.error('[ConsentOS] Failed to load site config:', err);
    config = buildDefaultConfig(siteId);
  }

  // Apply A/B test variant assignment (modifies banner_config if applicable)
  const existingConsent = readConsent();
  const visitorId = existingConsent?.visitorId ?? crypto.randomUUID?.() ?? String(Date.now());
  const abResult = _hooks.applyABTest(config, visitorId);
  config = abResult.config;
  const abAssignment = abResult.assignment;

  if (abAssignment) {
    console.info(`[ConsentOS] A/B test assigned: variant "${abAssignment.variant.name}"`);
  }

  // Install the real CMP public API now that we have the config
  installCmpApi(config);

  // Check if existing consent needs re-consent. We still load
  // translations and install the floating button even when no banner
  // needs to show, so the visitor can re-open the preference centre
  // at any time (GDPR Art. 7(3) — withdrawal must be as easy as
  // giving consent).
  let reconsentRequired = false;
  if (existingConsent) {
    const reconsent = _hooks.needsReconsent(existingConsent, config);
    reconsentRequired = reconsent.required;
    if (reconsent.required) {
      console.info('[ConsentOS] Re-consent required:', reconsent.reasons.join(', '));
    }
  }

  // Install GPP API if enabled
  if (config.gpp_enabled) {
    _hooks.installGppApi(0, config.gpp_supported_apis ?? []);
    _hooks.setGppDisplayStatus('visible');
  }

  // Evaluate GPC signal
  const visitorRegion = _hooks.getVisitorRegion();
  const gpcResult = _hooks.evaluateGpc(config, visitorRegion);

  if (gpcResult.detected) {
    console.info(`[ConsentOS] GPC signal detected (honoured: ${gpcResult.honoured})`);
  }

  // Load translations
  const locale = detectLocale();
  const t = await loadTranslations(cdnBase, locale);

  // Capture a closure that re-opens the banner with current consent
  // pre-filled. Called from the floating button and from
  // ``window.ConsentOS.showPreferences()``.
  _openPreferences = () => {
    removePreferencesButton();
    const current = readConsent();
    renderBanner(config, t, gpcResult, abAssignment, {
      prefillCategories: current?.accepted ?? null,
      showCategoriesInitially: true,
    });
  };

  if (existingConsent && !reconsentRequired) {
    // Banner isn't shown; expose the floating button straight away.
    showPreferencesButton(config, t);
    return;
  }

  // First-visit or re-consent: render the banner itself.
  renderBanner(config, t, gpcResult, abAssignment);
}

/**
 * Install the real window.ConsentOS API, replacing the loader stubs.
 *
 * `identifyUser(jwt)` syncs consent with the server. If the server profile
 * fully covers all categories, the banner is suppressed. If categories are
 * missing, only those categories need consent from the user.
 */
function installCmpApi(config: SiteConfig): void {
  window.ConsentOS = {
    identifyUser: async (jwt: string): Promise<string[]> => {
      const missing = await _hooks.identifyUser(jwt, config);
      return missing;
    },
    clearIdentity: (): void => {
      _hooks.clearIdentity();
    },
    showPreferences: (): void => {
      if (_openPreferences) {
        _openPreferences();
      } else {
        console.warn('[ConsentOS] showPreferences called before init complete');
      }
    },
  };
}

/** Build a default config when the API is unreachable. */
function buildDefaultConfig(siteId: string): SiteConfig {
  return {
    id: '',
    site_id: siteId,
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
    enabled_categories: [...ALL_CATEGORIES],
  };
}

/** Options for re-opening the banner from the preferences button. */
interface OpenOptions {
  /** Pre-check these category slugs (skips strict-necessary which is always on). */
  prefillCategories: CategorySlug[] | null;
  /** Open the banner with the category toggles visible. */
  showCategoriesInitially: boolean;
}

/** Create a Shadow DOM host and render the banner inside it. */
function renderBanner(
  config: SiteConfig,
  t: TranslationStrings,
  gpcResult?: GpcResult,
  abAssignment?: ABAssignment | null,
  openOptions?: OpenOptions,
): void {
  const host = document.createElement('div');
  host.id = 'consentos-banner-host';
  const shadow = host.attachShadow({ mode: 'open' });

  const titleId = 'cmp-title';
  const descId = 'cmp-desc';

  const enabledCategories = resolveEnabledCategories(config);
  const nonEssential = nonEssentialFor(enabledCategories);

  shadow.innerHTML = `
    <style>${getBannerStyles(config)}</style>
    <div class="consentos-banner" role="dialog" aria-label="${t.title}" aria-labelledby="${titleId}" aria-describedby="${descId}" aria-modal="true">
      <div class="consentos-banner__content">
        <div class="consentos-banner__text">
          <p class="consentos-banner__title" id="${titleId}">${t.title}</p>
          <p class="consentos-banner__description" id="${descId}">
            ${renderDescription(t.description, config)}
          </p>
        </div>
        <div class="consentos-banner__categories" id="consentos-categories" role="group" aria-label="${t.managePreferences}">
          ${renderCategories(t, enabledCategories)}
        </div>
        <div class="consentos-banner__actions" role="group" aria-label="Consent actions">
          <button class="cmp-btn cmp-btn--secondary" data-action="reject" type="button">
            ${t.rejectAll}
          </button>
          <button class="cmp-btn cmp-btn--secondary" data-action="settings" type="button" aria-expanded="false" aria-controls="consentos-categories">
            ${t.managePreferences}
          </button>
          <button class="cmp-btn cmp-btn--primary" data-action="accept" type="button">
            ${t.acceptAll}
          </button>
        </div>
      </div>
    </div>
  `;

  // Attach event listeners
  const banner = shadow.querySelector('.consentos-banner') as HTMLElement;
  const categoriesDiv = shadow.querySelector('#consentos-categories') as HTMLElement;
  const settingsBtn = shadow.querySelector('[data-action="settings"]') as HTMLElement;

  // Hide or show the category toggles depending on entry mode.
  // Opening via ``showPreferences`` lands directly on the toggles.
  const startWithCategories = openOptions?.showCategoriesInitially === true;
  categoriesDiv.style.display = startWithCategories ? 'block' : 'none';
  settingsBtn.setAttribute('aria-expanded', startWithCategories ? 'true' : 'false');

  // Pre-fill category checkboxes from existing consent when re-opened.
  if (openOptions?.prefillCategories) {
    const prefill = new Set(openOptions.prefillCategories);
    shadow.querySelectorAll<HTMLInputElement>('input[data-category]').forEach((input) => {
      const slug = input.getAttribute('data-category') as CategorySlug;
      if (slug === 'necessary') return; // always on + disabled
      input.checked = prefill.has(slug);
    });
  }

  // Create live region for screen reader announcements
  const liveRegion = createLiveRegion(shadow);

  // Set up keyboard navigation
  const cleanupFocusTrap = trapFocus(banner);
  const cleanupEscape = onEscape(banner, () => {
    handleConsent(['necessary'], nonEssential, config, gpcResult, abAssignment, t);
    removeBanner(host, cleanupFocusTrap, cleanupEscape);
  });

  shadow.querySelectorAll('[data-action]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const action = (e.currentTarget as HTMLElement).getAttribute('data-action');
      if (action === 'accept') {
        // Explicit Accept All overrides GPC — user choice takes precedence.
        // "All" only includes the categories the operator has enabled.
        handleConsent([...enabledCategories], [], config, gpcResult, abAssignment, t);
        removeBanner(host, cleanupFocusTrap, cleanupEscape);
      } else if (action === 'reject') {
        handleConsent(['necessary'], nonEssential, config, gpcResult, abAssignment, t);
        removeBanner(host, cleanupFocusTrap, cleanupEscape);
      } else if (action === 'settings') {
        const isHidden = categoriesDiv.style.display === 'none';
        categoriesDiv.style.display = isHidden ? 'block' : 'none';
        settingsBtn.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
        announce(liveRegion, isHidden ? t.managePreferences : t.title);
      } else if (action === 'save') {
        const accepted = getSelectedCategories(shadow);
        const rejected = nonEssential.filter((c) => !accepted.includes(c));
        handleConsent(accepted, rejected, config, gpcResult, abAssignment, t);
        removeBanner(host, cleanupFocusTrap, cleanupEscape);
      }
    });
  });

  document.body.appendChild(host);

  // Move focus into the banner for keyboard users
  focusFirst(banner);
}

/** Render category toggles HTML. Only renders the categories the
 *  config has enabled — ``necessary`` is always present and locked. */
function renderCategories(t: TranslationStrings, enabled: CategorySlug[]): string {
  const all = [
    { slug: 'necessary' as const, name: t.categoryNecessary, desc: t.categoryNecessaryDesc, locked: true },
    { slug: 'functional' as const, name: t.categoryFunctional, desc: t.categoryFunctionalDesc, locked: false },
    { slug: 'analytics' as const, name: t.categoryAnalytics, desc: t.categoryAnalyticsDesc, locked: false },
    { slug: 'marketing' as const, name: t.categoryMarketing, desc: t.categoryMarketingDesc, locked: false },
    { slug: 'personalisation' as const, name: t.categoryPersonalisation, desc: t.categoryPersonalisationDesc, locked: false },
  ];

  const enabledSet = new Set(enabled);
  const categories = all.filter((cat) => enabledSet.has(cat.slug));

  return (
    categories
      .map(
        (cat) => `
      <label class="cmp-category">
        <div class="cmp-category__info">
          <span class="cmp-category__name" id="cmp-cat-${cat.slug}">${cat.name}</span>
          <span class="cmp-category__desc" id="cmp-cat-${cat.slug}-desc">${cat.desc}</span>
        </div>
        <input type="checkbox" data-category="${cat.slug}"
          aria-labelledby="cmp-cat-${cat.slug}"
          aria-describedby="cmp-cat-${cat.slug}-desc"
          ${cat.locked ? 'checked disabled' : ''}
        />
      </label>
    `
      )
      .join('') +
    `<button class="cmp-btn cmp-btn--primary cmp-btn--save" data-action="save" type="button">
      ${t.savePreferences}
    </button>`
  );
}

/** Read which categories are checked in the shadow DOM. */
function getSelectedCategories(shadow: ShadowRoot): CategorySlug[] {
  const checked: CategorySlug[] = ['necessary'];
  shadow.querySelectorAll<HTMLInputElement>('input[data-category]').forEach((input) => {
    if (input.checked) {
      checked.push(input.getAttribute('data-category') as CategorySlug);
    }
  });
  return [...new Set(checked)];
}

/** Handle a consent decision: write cookie, update GCM, GPP, post to API, dispatch event. */
function handleConsent(
  accepted: CategorySlug[],
  rejected: CategorySlug[],
  config: SiteConfig,
  gpcResult?: GpcResult,
  abAssignment?: ABAssignment | null,
  t?: TranslationStrings,
): void {
  const existing = readConsent();
  const gcmState = buildGcmStateFromCategories(accepted);

  // Generate GPP string if GPP is enabled
  let gppString: string | undefined;
  if (config.gpp_enabled && _hooks.isGppApiInstalled() && _hooks.buildGppFromConsent) {
    const gpp = _hooks.buildGppFromConsent(accepted, config);
    gppString = _hooks.updateGppConsent(gpp);
    _hooks.setGppDisplayStatus('hidden');
  }

  const state = buildConsentState(
    accepted,
    rejected,
    existing?.visitorId,
    undefined,
    gcmState,
    config.id,
    gppString,
    gpcResult?.detected,
    gpcResult?.honoured,
  );

  // Write first-party cookie
  writeConsent(state, config.consent_expiry_days);

  // Release blocked scripts for accepted categories
  updateAcceptedCategories(accepted);

  // Update Google Consent Mode
  if (config.gcm_enabled) {
    updateGcm(gcmState);
  }

  // Update Shopify Customer Privacy API
  if (config.shopify_privacy_enabled) {
    _hooks.updateShopifyConsent(accepted);
  }

  // Post consent to API (fire and forget)
  const { siteId, apiBase } = window.__consentos;
  fetch(`${apiBase}/api/v1/consent/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      site_id: siteId,
      visitor_id: state.visitorId,
      action: determineAction(accepted, rejected),
      categories_accepted: accepted,
      categories_rejected: rejected,
      gcm_state: gcmState,
      gpc_detected: gpcResult?.detected ?? false,
      gpc_honoured: gpcResult?.honoured ?? false,
      page_url: window.location.href,
      ab_test_id: abAssignment?.abTestId ?? null,
      ab_variant_id: abAssignment?.variantId ?? null,
    }),
  }).catch((err) => console.warn('[ConsentOS] Failed to record consent:', err));

  // Push to server if user is identified (non-blocking background sync)
  if (_hooks.isIdentified()) {
    _hooks.pushConsentToServer(accepted, rejected, undefined, gppString, gcmState);
  }

  // Dispatch event
  document.dispatchEvent(
    new CustomEvent('consentos:consent-change', { detail: { accepted } })
  );

  if (typeof window.dataLayer !== 'undefined') {
    window.dataLayer.push({
      event: 'consentos_consent_change',
      cmp_accepted_categories: accepted,
    });
  }

  // Bridge for the standalone ConsentOS GTM template — when the
  // template is loaded on the page it registers a global callback so
  // it can react to consent changes. Lives in its own repo.
  if (typeof (window as any).__consentos_gtm_consent_update === 'function') {
    (window as any).__consentos_gtm_consent_update({ accepted });
  }

  // Re-expose the floating preferences button so the visitor can
  // withdraw or change their decision later.
  if (t) {
    showPreferencesButton(config, t);
  }
}

/**
 * Render the banner description with template variables and markdown links.
 *
 * Replaces `{{privacy_policy}}` and `{{terms}}` with their URLs from config,
 * then converts `[text](url)` markdown links to `<a>` tags.
 * Links with empty URLs (because the config field is unset) are removed.
 */
function renderDescription(description: string, config: SiteConfig): string {
  const rendered = interpolate(description, {
    privacy_policy: config.privacy_policy_url ?? '',
    terms: config.terms_url ?? '',
  });
  return renderLinks(rendered);
}

/** Determine the consent action string. */
function determineAction(
  accepted: CategorySlug[],
  rejected: CategorySlug[]
): string {
  if (rejected.length === 0) return 'accept_all';
  if (accepted.length === 1 && accepted[0] === 'necessary') return 'reject_all';
  return 'custom';
}

/** Remove the banner from the DOM. */
function removeBanner(
  host: HTMLElement,
  ...cleanups: Array<() => void>
): void {
  cleanups.forEach((fn) => fn());
  const useMotion = !prefersReducedMotion();
  if (useMotion) {
    host.style.opacity = '0';
    host.style.transition = 'opacity 0.3s ease';
    setTimeout(() => host.remove(), 300);
  } else {
    host.remove();
  }
}

// -- Floating "manage preferences" button ---------------------------------

const _PREFERENCES_BUTTON_ID = 'cmp-preferences-button';

/** Remove the floating preferences button if present. */
function removePreferencesButton(): void {
  const existing = document.getElementById(_PREFERENCES_BUTTON_ID);
  if (existing) {
    existing.remove();
  }
}

/**
 * Render a persistent floating button that re-opens the banner.
 *
 * Required by GDPR Art. 7(3) — withdrawing consent must be as easy
 * as giving it. Positioned opposite the banner's corner by default
 * so it doesn't sit behind the initial banner if displayed together.
 */
function showPreferencesButton(config: SiteConfig, t: TranslationStrings): void {
  removePreferencesButton();

  // Honour the site's opt-out: operators can disable the floating
  // button via ``banner_config.show_preferences_button = false``.
  const bc = config.banner_config ?? null;
  if (bc && (bc as Record<string, unknown>).show_preferences_button === false) {
    return;
  }

  const position =
    (bc as Record<string, unknown> | null)?.preferences_button_position === 'left'
      ? 'left: 20px;'
      : 'right: 20px;';

  const host = document.createElement('div');
  host.id = _PREFERENCES_BUTTON_ID;
  const shadow = host.attachShadow({ mode: 'open' });

  const label =
    t.managePreferences || 'Cookie preferences';

  shadow.innerHTML = `
    <style>
      :host {
        position: fixed;
        bottom: 20px;
        ${position}
        z-index: 2147483646;
      }
      button {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.6rem 0.9rem;
        background: #111;
        color: #fff;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 999px;
        font: 500 0.85rem system-ui, -apple-system, sans-serif;
        cursor: pointer;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
      }
      button:hover { opacity: 0.92; }
      button:focus-visible {
        outline: 2px solid #4a90e2;
        outline-offset: 2px;
      }
      svg { width: 1rem; height: 1rem; flex-shrink: 0; }
      @media (prefers-reduced-motion: no-preference) {
        button { transition: transform 0.15s ease; }
        button:hover { transform: translateY(-1px); }
      }
    </style>
    <button type="button" aria-label="${label}" title="${label}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10"/>
        <path d="M8.5 8.5v.01"/>
        <path d="M16 15.5v.01"/>
        <path d="M12 12v.01"/>
        <path d="M11 17v.01"/>
        <path d="M7 14v.01"/>
      </svg>
      <span>${label}</span>
    </button>
  `;

  const btn = shadow.querySelector('button') as HTMLButtonElement;
  btn.addEventListener('click', () => {
    if (_openPreferences) {
      _openPreferences();
    }
  });

  document.body.appendChild(host);
}

/** Resolve position CSS for the banner based on display mode. */
function getPositionCss(bc: BannerConfig | null): string {
  const mode = bc?.displayMode ?? 'bottom_banner';
  const radius = bc?.borderRadius ?? 6;
  const cornerPos = bc?.cornerPosition ?? 'right';

  switch (mode) {
    case 'top_banner':
      return 'position: fixed; top: 0; left: 0; right: 0; z-index: 2147483647;';
    case 'overlay':
      return `position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2147483647; width: 90%; max-width: 600px; border-radius: ${radius}px;`;
    case 'corner_popup': {
      const side = cornerPos === 'left' ? 'left: 20px;' : 'right: 20px;';
      return `position: fixed; bottom: 20px; ${side} z-index: 2147483647; width: 380px; max-width: calc(100% - 40px); border-radius: ${radius}px;`;
    }
    case 'bottom_banner':
    default:
      return 'position: fixed; bottom: 0; left: 0; right: 0; z-index: 2147483647;';
  }
}

/** Resolve per-button inline style from ButtonConfig. */
function getButtonCss(
  btnCfg: ButtonConfig | undefined,
  fallbackBg: string,
  fallbackColor: string,
  fallbackBorder: string,
  radius: number,
): string {
  const style = btnCfg?.style;
  const bg = style === 'text' || style === 'outline'
    ? 'transparent'
    : btnCfg?.backgroundColour ?? fallbackBg;
  const color = btnCfg?.textColour ?? fallbackColor;
  const border = btnCfg?.borderColour
    ? `1px solid ${btnCfg.borderColour}`
    : style === 'outline'
      ? `1px solid ${color}`
      : style === 'text'
        ? 'none'
        : fallbackBorder;

  return `background: ${bg}; color: ${color}; border: ${border}; border-radius: ${radius}px;`;
}

/** Banner CSS — isolated inside Shadow DOM. */
function getBannerStyles(config: SiteConfig): string {
  const bc = config.banner_config;
  const bg = bc?.backgroundColour ?? '#ffffff';
  const text = bc?.textColour ?? '#0E1929';        // ConsentOS Ink
  const primary = bc?.primaryColour ?? '#2C6AE4';  // ConsentOS Action Blue
  const font = bc?.fontFamily ?? '-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif';
  const radius = bc?.borderRadius ?? 6;
  const mode = bc?.displayMode ?? 'bottom_banner';

  const acceptCss = getButtonCss(bc?.acceptButton, primary, '#ffffff', 'none', radius);
  const rejectCss = getButtonCss(bc?.rejectButton, 'transparent', text, '1px solid rgba(0,0,0,0.2)', radius);
  const manageCss = getButtonCss(bc?.manageButton, 'transparent', text, '1px solid rgba(0,0,0,0.2)', radius);

  return `
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    .consentos-banner {
      ${getPositionCss(bc)}
      background: ${bg};
      color: ${text};
      font-family: ${font}, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.15);
      border: 1px solid rgba(0, 0, 0, 0.1);
      border-radius: ${mode === 'overlay' || mode === 'corner_popup' ? radius + 'px' : '0'};
    }

    .consentos-banner__content {
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px 24px;
    }

    .consentos-banner__title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 8px;
    }

    .consentos-banner__description {
      margin-bottom: 16px;
      opacity: 0.85;
    }

    .consentos-banner__link {
      color: ${primary};
      text-decoration: underline;
    }

    .consentos-banner__actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .cmp-btn {
      padding: 10px 20px;
      border-radius: ${radius}px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      border: none;
      transition: opacity 0.2s;
      font-family: inherit;
    }

    .cmp-btn:hover { opacity: 0.9; }
    .cmp-btn:focus-visible {
      outline: 2px solid ${primary};
      outline-offset: 2px;
    }

    .cmp-btn--primary { ${acceptCss} }
    .cmp-btn--secondary[data-action="reject"] { ${rejectCss} }
    .cmp-btn--secondary[data-action="settings"] { ${manageCss} }
    .cmp-btn--secondary { ${rejectCss} }

    .consentos-banner__categories {
      margin-bottom: 16px;
    }

    .cmp-category {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 0;
      border-bottom: 1px solid rgba(0, 0, 0, 0.08);
      cursor: pointer;
    }

    .cmp-category__info {
      display: flex;
      flex-direction: column;
      flex: 1;
      margin-right: 12px;
    }

    .cmp-category__name {
      font-weight: 500;
    }

    .cmp-category__desc {
      font-size: 12px;
      opacity: 0.7;
    }

    .cmp-category input[type="checkbox"] {
      width: 18px;
      height: 18px;
      accent-color: ${primary};
    }

    .cmp-btn--save {
      margin-top: 12px;
      width: 100%;
    }

    /* Visually hidden but accessible to screen readers */
    .cmp-sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }

    @media (max-width: 640px) {
      .consentos-banner__actions {
        flex-direction: column;
      }
      .cmp-btn {
        width: 100%;
        text-align: center;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        transition-duration: 0s !important;
        animation-duration: 0s !important;
      }
    }
  `;
}

// Auto-init on load
init();
