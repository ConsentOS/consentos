import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { buildShopifyConsent, isShopifyPrivacyAvailable, updateShopifyConsent } from '../shopify';
import type { ShopifyVisitorConsent } from '../shopify';
import type { CategorySlug } from '../types';

const UNDECIDED: ShopifyVisitorConsent = {
  analytics: '',
  marketing: '',
  preferences: '',
  sale_of_data: '',
};

describe('shopify', () => {
  const mockSetTrackingConsent = vi.fn();
  const mockCurrentVisitorConsent = vi.fn(() => ({ ...UNDECIDED }));

  beforeEach(() => {
    mockCurrentVisitorConsent.mockReturnValue({ ...UNDECIDED });
    (window as any).Shopify = {
      customerPrivacy: {
        setTrackingConsent: mockSetTrackingConsent,
        currentVisitorConsent: mockCurrentVisitorConsent,
        analyticsProcessingAllowed: () => false,
        marketingAllowed: () => false,
        preferencesProcessingAllowed: () => false,
        saleOfDataAllowed: () => false,
        getRegion: () => 'CA',
      },
    };
  });

  afterEach(() => {
    delete (window as any).Shopify;
    vi.restoreAllMocks();
  });

  describe('isShopifyPrivacyAvailable', () => {
    it('returns true when Shopify API is present', () => {
      expect(isShopifyPrivacyAvailable()).toBe(true);
    });

    it('returns false when Shopify is not on window', () => {
      delete (window as any).Shopify;
      expect(isShopifyPrivacyAvailable()).toBe(false);
    });

    it('returns false when customerPrivacy is missing', () => {
      (window as any).Shopify = {};
      expect(isShopifyPrivacyAvailable()).toBe(false);
    });
  });

  describe('buildShopifyConsent', () => {
    it('emits booleans, never strings', () => {
      // setTrackingConsent takes booleans. 'no' is truthy, so a string
      // rejection is read as a grant.
      const result = buildShopifyConsent(['necessary']);
      for (const value of Object.values(result)) {
        expect(typeof value).toBe('boolean');
      }
    });

    it('maps accept all', () => {
      const accepted: CategorySlug[] = [
        'necessary',
        'functional',
        'analytics',
        'marketing',
        'personalisation',
      ];
      expect(buildShopifyConsent(accepted)).toEqual({
        preferences: true,
        analytics: true,
        marketing: true,
        sale_of_data: true,
      });
    });

    it('maps reject all (necessary only)', () => {
      expect(buildShopifyConsent(['necessary'])).toEqual({
        preferences: false,
        analytics: false,
        marketing: false,
        sale_of_data: false,
      });
    });

    it('maps functional to preferences', () => {
      const result = buildShopifyConsent(['necessary', 'functional']);
      expect(result.preferences).toBe(true);
      expect(result.analytics).toBe(false);
      expect(result.marketing).toBe(false);
    });

    it('maps personalisation to sale_of_data', () => {
      const result = buildShopifyConsent(['necessary', 'personalisation']);
      expect(result.sale_of_data).toBe(true);
      expect(result.marketing).toBe(false);
    });

    it('maps marketing to both marketing and sale_of_data', () => {
      const result = buildShopifyConsent(['necessary', 'marketing']);
      expect(result.marketing).toBe(true);
      expect(result.sale_of_data).toBe(true);
    });
  });

  describe('updateShopifyConsent', () => {
    it('calls setTrackingConsent with booleans', () => {
      updateShopifyConsent(['necessary', 'analytics', 'marketing']);

      expect(mockSetTrackingConsent).toHaveBeenCalledWith(
        {
          preferences: false,
          analytics: true,
          marketing: true,
          sale_of_data: true,
        },
        expect.any(Function),
      );
    });

    it('does nothing when Shopify API is not available', () => {
      delete (window as any).Shopify;
      updateShopifyConsent(['necessary', 'analytics']);
      expect(mockSetTrackingConsent).not.toHaveBeenCalled();
    });
  });
});
