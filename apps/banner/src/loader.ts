/**
 * consent-loader.js — Lightweight synchronous bootstrap (~2KB gzipped).
 *
 * Runs before any other scripts on the page. Responsibilities:
 * 1. Read existing consent cookie — if valid, apply consent state immediately
 * 2. Set Google Consent Mode defaults (all denied except security_storage)
 * 3. If no consent: async-load the full banner bundle
 * 4. Fetch site config from CDN/API
 */

import { installBlocker, updateAcceptedCategories } from './blocker';
import { hasConsent, readConsent } from './consent';
import { buildDeniedDefaults, buildGcmStateFromCategories, setGcmDefaults, updateGcm } from './gcm';
import { isGpcEnabled } from './gpc';
import type { GppApiCallback, GppApiFunction, GppQueueEntry } from './gpp-api';
import type { CategorySlug } from './types';

declare global {
  interface Window {
    __consentos: {
      siteId: string;
      apiBase: string;
      cdnBase: string;
      loaded: boolean;
      /** Visitor region from GeoIP (e.g. 'US-CA'), set by loader. */
      visitorRegion?: string;
      /** Whether GPC signal was detected by the loader. */
      gpcDetected?: boolean;
      /**
       * Internal: drives the blocker installed by the loader. The
       * banner bundle is a separate IIFE with its own module scope,
       * so it can't share ``acceptedCategories`` via a direct import
       * — it has to call back through this bridge. See
       * ``apps/banner/src/blocker.ts`` for the state it mutates.
       * Consumers outside the banner bundle should not call this.
       */
      _updateBlocker?: (accepted: CategorySlug[]) => void;
    };
    /** Public ConsentOS API for site integration. */
    ConsentOS: {
      /**
       * Identify a user by providing their third-party JWT.
       * Syncs consent with the server-side profile.
       * Returns categories that still need consent (empty if fully resolved).
       */
      identifyUser: (jwt: string) => Promise<string[]>;
      /** Clear the identified user session (revert to anonymous). */
      clearIdentity: () => void;
      /**
       * Re-open the banner so the visitor can review, change, or
       * withdraw their consent. Pre-fills category toggles from the
       * current stored consent state. Required by GDPR Art. 7(3)
       * ("it shall be as easy to withdraw as to give consent").
       */
      showPreferences: () => void;
    };
  }
}

(function consentosLoader() {
  // Read data attributes from the script tag, falling back to
  // window.__consentos if attributes are absent (e.g. GTM injectScript).
  const scriptEl = document.currentScript as HTMLScriptElement | null;
  const gtmConfig = (window as any).__consentos;
  const siteId = scriptEl?.getAttribute('data-site-id') ?? gtmConfig?.siteId ?? '';
  const apiBase = scriptEl?.getAttribute('data-api-base') ?? gtmConfig?.apiBase ?? '';

  // Derive cdnBase: explicit attribute > apiBase > same origin as this script
  const scriptSrc = scriptEl?.getAttribute('src') ?? '';
  let scriptOrigin = '';
  try {
    if (scriptSrc) {
      scriptOrigin = new URL(scriptSrc, window.location.href).origin;
    }
  } catch {
    // Invalid URL — fall through to empty string
  }
  const cdnBase = scriptEl?.getAttribute('data-cdn-base') ?? (apiBase || scriptOrigin);

  // Expose global CMP context
  window.__consentos = {
    siteId,
    apiBase,
    cdnBase,
    loaded: false,
  };

  // Expose public CMP API — methods are stubs until the full bundle loads
  // and replaces them with real implementations.
  window.ConsentOS = {
    identifyUser: async () => {
      console.warn('[ConsentOS] identifyUser called before bundle loaded — queuing');
      return [];
    },
    clearIdentity: () => {
      console.warn('[ConsentOS] clearIdentity called before bundle loaded');
    },
    showPreferences: () => {
      console.warn('[ConsentOS] showPreferences called before bundle loaded');
    },
  };

  // Warn if essential attributes are missing
  if (!siteId) {
    console.warn('[ConsentOS] Missing data-site-id attribute on the consent-loader script tag');
  }
  if (!apiBase) {
    console.warn('[ConsentOS] Missing data-api-base attribute — consent recording will not work');
  }

  // 1. Install script/cookie blocker immediately (before any third-party scripts)
  installBlocker();

  // 1a. Bridge the blocker to the full banner bundle. ``consent-bundle.js``
  // is built as a separate rollup IIFE with its own module scope, so it
  // gets its own dead-end copy of ``blocker.ts``. Expose the loader's
  // live ``updateAcceptedCategories`` on ``window.__consentos`` so
  // ``handleConsent`` in the bundle can drive the loader's proxies
  // directly. Without this, consent updates from the bundle would only
  // mutate the bundle's copy and the cookie/storage proxies running in
  // the loader's scope would stay stuck on ``Set(['necessary'])``.
  window.__consentos._updateBlocker = updateAcceptedCategories;

  // 1b. Install __gpp stub — queues calls until the full bundle loads
  installGppStub();

  // 2. Set GCM defaults immediately (must happen before gtag tags fire)
  setGcmDefaults(buildDeniedDefaults());

  // 2b. Detect GPC signal early and store on __cmp for the banner bundle
  window.__consentos.gpcDetected = isGpcEnabled();

  // 3. Check for existing consent
  const existingConsent = readConsent();

  if (existingConsent) {
    // Consent already given — update blocker, GCM, and we're done
    updateAcceptedCategories(existingConsent.accepted as import('./types').CategorySlug[]);
    const gcmState = buildGcmStateFromCategories(existingConsent.accepted);
    updateGcm(gcmState);

    // Fire consent-change event so GTM/other scripts know
    dispatchConsentEvent(existingConsent.accepted);
    return;
  }

  // 4. No consent — async-load the full banner bundle
  loadBannerBundle(cdnBase);
})();

/** Async-load the full consent banner bundle. */
function loadBannerBundle(cdnBase: string): void {
  const script = document.createElement('script');
  // Mark as allowed so the blocker's MutationObserver doesn't intercept it
  script.setAttribute('data-consentos-allowed', 'true');
  script.src = `${cdnBase}/consent-bundle.js`;
  script.async = true;
  script.onload = () => {
    window.__consentos.loaded = true;
  };
  script.onerror = () => {
    console.error(`[ConsentOS] Failed to load consent bundle from ${cdnBase}/consent-bundle.js`);
  };
  document.head.appendChild(script);
}

/**
 * Install a lightweight __gpp() stub that queues calls until the full
 * banner bundle loads and replaces it with the real implementation.
 */
function installGppStub(): void {
  if (typeof window === 'undefined') return;
  if (window.__gpp) return; // Already installed

  const queue: GppQueueEntry[] = [];
  window.__gppQueue = queue;

  const stub: GppApiFunction = function gppStub(
    command: string,
    callback: GppApiCallback,
    parameter?: unknown,
  ) {
    if (command === 'ping') {
      callback(
        {
          gppVersion: '1.1',
          cmpStatus: 'stub',
          cmpDisplayStatus: 'hidden',
          signalStatus: 'not ready',
          supportedAPIs: [],
          cmpId: 0,
          gppString: '',
          applicableSections: [],
        },
        true,
      );
      return;
    }
    queue.push([command, callback, parameter]);
  };

  window.__gpp = stub;
}

/** Dispatch a custom event with accepted categories. */
function dispatchConsentEvent(accepted: string[]): void {
  const event = new CustomEvent('consentos:consent-change', {
    detail: { accepted },
  });
  document.dispatchEvent(event);

  // Also push to dataLayer for GTM
  if (typeof window.dataLayer !== 'undefined') {
    window.dataLayer.push({
      event: 'consentos_consent_change',
      cmp_accepted_categories: accepted,
    });
  }
}
