import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  hasConfigVersionChanged,
  isConsentExpired,
  needsReconsent,
} from '../reconsent';
import type { ConsentState, SiteConfig } from '../types';

/** Helper to build a minimal ConsentState for testing. */
function makeConsent(overrides: Partial<ConsentState> = {}): ConsentState {
  return {
    visitorId: 'test-visitor-id',
    accepted: ['necessary', 'analytics'],
    rejected: ['marketing'],
    consentedAt: new Date().toISOString(),
    bannerVersion: '0.1.0',
    ...overrides,
  };
}

/** Helper to build a minimal SiteConfig for testing. */
function makeConfig(overrides: Partial<SiteConfig> = {}): SiteConfig {
  return {
    id: 'config-v1',
    site_id: 'site-123',
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
    initiator_map: null,
    ...overrides,
  };
}

describe('reconsent', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-15T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('isConsentExpired', () => {
    it('should return false when consent is within expiry period', () => {
      const consent = makeConsent({
        consentedAt: '2026-06-01T12:00:00Z', // 14 days ago
      });
      const config = makeConfig({ consent_expiry_days: 365 });

      expect(isConsentExpired(consent, config)).toBe(false);
    });

    it('should return true when consent has expired', () => {
      const consent = makeConsent({
        consentedAt: '2025-01-01T12:00:00Z', // ~530 days ago
      });
      const config = makeConfig({ consent_expiry_days: 365 });

      expect(isConsentExpired(consent, config)).toBe(true);
    });

    it('should return true for exactly expired consent', () => {
      // Consent given exactly 365 days ago + 1ms
      const consentDate = new Date('2025-06-15T11:59:59.999Z');
      const consent = makeConsent({ consentedAt: consentDate.toISOString() });
      const config = makeConfig({ consent_expiry_days: 365 });

      expect(isConsentExpired(consent, config)).toBe(true);
    });

    it('should return true for invalid consentedAt date', () => {
      const consent = makeConsent({ consentedAt: 'not-a-date' });
      const config = makeConfig();

      expect(isConsentExpired(consent, config)).toBe(true);
    });

    it('should handle short expiry periods', () => {
      const consent = makeConsent({
        consentedAt: '2026-06-10T12:00:00Z', // 5 days ago
      });
      const config = makeConfig({ consent_expiry_days: 3 });

      expect(isConsentExpired(consent, config)).toBe(true);
    });
  });

  describe('hasConfigVersionChanged', () => {
    it('should return false when versions match', () => {
      const consent = makeConsent({ configVersion: 'config-v1' });
      const config = makeConfig({ id: 'config-v1' });

      expect(hasConfigVersionChanged(consent, config)).toBe(false);
    });

    it('should return true when versions differ', () => {
      const consent = makeConsent({ configVersion: 'config-v1' });
      const config = makeConfig({ id: 'config-v2' });

      expect(hasConfigVersionChanged(consent, config)).toBe(true);
    });

    it('should return true when consent has no configVersion and config has an id', () => {
      const consent = makeConsent(); // no configVersion
      const config = makeConfig({ id: 'config-v1' });

      expect(hasConfigVersionChanged(consent, config)).toBe(true);
    });

    it('should return false when consent has no configVersion and config id is empty', () => {
      const consent = makeConsent(); // no configVersion
      const config = makeConfig({ id: '' });

      expect(hasConfigVersionChanged(consent, config)).toBe(false);
    });
  });

  describe('needsReconsent', () => {
    it('should return not required when all checks pass', () => {
      const consent = makeConsent({
        consentedAt: '2026-06-01T12:00:00Z',
        configVersion: 'config-v1',
      });
      const config = makeConfig({
        consent_expiry_days: 365,
        id: 'config-v1',
      });

      const result = needsReconsent(consent, config);
      expect(result.required).toBe(false);
      expect(result.reasons).toEqual([]);
    });

    it('should detect expired consent', () => {
      const consent = makeConsent({
        consentedAt: '2024-01-01T00:00:00Z',
        configVersion: 'config-v1',
      });
      const config = makeConfig({
        consent_expiry_days: 365,
        id: 'config-v1',
      });

      const result = needsReconsent(consent, config);
      expect(result.required).toBe(true);
      expect(result.reasons).toContain('expired');
    });

    it('should detect config version change', () => {
      const consent = makeConsent({
        consentedAt: '2026-06-01T12:00:00Z',
        configVersion: 'config-v1',
      });
      const config = makeConfig({
        consent_expiry_days: 365,
        id: 'config-v2',
      });

      const result = needsReconsent(consent, config);
      expect(result.required).toBe(true);
      expect(result.reasons).toContain('config_changed');
    });

    it('should report multiple reasons', () => {
      const consent = makeConsent({
        consentedAt: '2024-01-01T00:00:00Z', // expired
        configVersion: 'config-v1',
      });
      const config = makeConfig({
        consent_expiry_days: 365,
        id: 'config-v2', // config changed
      });

      const result = needsReconsent(consent, config);
      expect(result.required).toBe(true);
      expect(result.reasons).toContain('expired');
      expect(result.reasons).toContain('config_changed');
      expect(result.reasons).toHaveLength(2);
    });

    it('should not require re-consent for fresh consent with matching config', () => {
      const consent = makeConsent({
        consentedAt: new Date().toISOString(), // just now
        configVersion: 'config-v1',
      });
      const config = makeConfig({
        consent_expiry_days: 365,
        id: 'config-v1',
      });

      const result = needsReconsent(consent, config);
      expect(result.required).toBe(false);
      expect(result.reasons).toEqual([]);
    });
  });
});
