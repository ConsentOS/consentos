/**
 * Shopify Customer Privacy API integration.
 *
 * Bridges CMP consent decisions to Shopify's Customer Privacy API
 * (`window.Shopify.customerPrivacy`). When enabled, the CMP calls
 * `setTrackingConsent()` with the mapped consent state whenever
 * the visitor makes a consent choice.
 *
 * The API is asymmetric and this is the source of most integration
 * bugs: `setTrackingConsent()` accepts booleans, while
 * `currentVisitorConsent()` returns `'yes' | 'no' | ''` strings. Passing
 * a string to the setter is not a type error at runtime and not a
 * validation failure either, because `'no'` is truthy, so a rejection is
 * recorded as a grant.
 *
 * @see https://shopify.dev/docs/api/customer-privacy
 */

import type { CategorySlug } from './types';

/** Values `currentVisitorConsent()` reports: '' = undecided. */
export type ShopifyConsentValue = '' | 'yes' | 'no';

/** What `setTrackingConsent()` accepts. Booleans, not strings. */
export interface ShopifyTrackingConsent {
  analytics: boolean;
  marketing: boolean;
  preferences: boolean;
  sale_of_data: boolean;
}

/** What `currentVisitorConsent()` returns. */
export interface ShopifyVisitorConsent {
  analytics: ShopifyConsentValue;
  marketing: ShopifyConsentValue;
  preferences: ShopifyConsentValue;
  sale_of_data: ShopifyConsentValue;
}

/** Shape of window.Shopify.customerPrivacy when loaded. */
interface ShopifyCustomerPrivacy {
  setTrackingConsent: (consent: ShopifyTrackingConsent, callback?: () => void) => void;
  currentVisitorConsent: () => ShopifyVisitorConsent;
  analyticsProcessingAllowed: () => boolean;
  marketingAllowed: () => boolean;
  preferencesProcessingAllowed: () => boolean;
  saleOfDataAllowed: () => boolean;
  getRegion: () => string;
}

declare global {
  interface Window {
    Shopify?: {
      customerPrivacy?: ShopifyCustomerPrivacy;
      loadFeatures?: (
        features: Array<{ name: string; version: string }>,
        callback: (error?: Error) => void,
      ) => void;
    };
  }
}

/** Check whether the Shopify Customer Privacy API is available. */
export function isShopifyPrivacyAvailable(): boolean {
  return typeof window.Shopify?.customerPrivacy?.setTrackingConsent === 'function';
}

/**
 * Map CMP accepted categories to Shopify consent signals.
 *
 * Category mapping:
 *   functional    → preferences
 *   analytics     → analytics
 *   marketing     → marketing + sale_of_data
 *   personalisation → sale_of_data (if marketing not already accepted)
 *
 * The sale_of_data mapping is under review: deriving a CPRA opt-out flag
 * from an opt-in category can reverse an opt-out made elsewhere.
 */
export function buildShopifyConsent(accepted: CategorySlug[]): ShopifyTrackingConsent {
  return {
    preferences: accepted.includes('functional'),
    analytics: accepted.includes('analytics'),
    marketing: accepted.includes('marketing'),
    sale_of_data: accepted.includes('marketing') || accepted.includes('personalisation'),
  };
}

/**
 * Push consent state to the Shopify Customer Privacy API.
 *
 * This should be called after the user makes a consent choice, only
 * when `shopify_privacy_enabled` is true in the site config.
 *
 * If the API is not yet loaded, the call is silently skipped — Shopify's
 * own consent tracking will pick up the state on next page load.
 */
export function updateShopifyConsent(accepted: CategorySlug[]): void {
  if (!isShopifyPrivacyAvailable()) return;

  const consent = buildShopifyConsent(accepted);
  window.Shopify!.customerPrivacy!.setTrackingConsent(consent, () => {
    /* Consent registered with Shopify */
  });
}
