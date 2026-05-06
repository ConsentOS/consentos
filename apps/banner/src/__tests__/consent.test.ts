import { describe, it, expect, beforeEach } from 'vitest';
import {
  buildConsentState,
  clearConsent,
  generateVisitorId,
  hasConsent,
  isCategoryAccepted,
  readConsent,
  writeConsent,
  writeTcfCookie,
} from '../consent';

describe('consent', () => {
  beforeEach(() => {
    // Clear all cookies
    document.cookie.split(';').forEach((c) => {
      const name = c.split('=')[0].trim();
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
    });
  });

  describe('generateVisitorId', () => {
    it('should return a UUID-like string', () => {
      const id = generateVisitorId();
      expect(id).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
      );
    });

    it('should generate unique IDs', () => {
      const id1 = generateVisitorId();
      const id2 = generateVisitorId();
      expect(id1).not.toBe(id2);
    });
  });

  describe('buildConsentState', () => {
    it('should build state with accepted and rejected categories', () => {
      const state = buildConsentState(
        ['necessary', 'analytics'],
        ['marketing'],
      );
      expect(state.accepted).toEqual(['necessary', 'analytics']);
      expect(state.rejected).toEqual(['marketing']);
      expect(state.visitorId).toBeTruthy();
      expect(state.bannerVersion).toBe('0.1.0');
      expect(state.consentedAt).toBeTruthy();
    });

    it('should use existing visitor ID if provided', () => {
      const state = buildConsentState(
        ['necessary'],
        [],
        'existing-id-123',
      );
      expect(state.visitorId).toBe('existing-id-123');
    });
  });

  describe('read/write/clear consent', () => {
    it('should return null when no consent cookie exists', () => {
      expect(readConsent()).toBeNull();
      expect(hasConsent()).toBe(false);
    });

    it('should write and read consent state', () => {
      const state = buildConsentState(['necessary', 'analytics'], ['marketing']);
      writeConsent(state);

      const read = readConsent();
      expect(read).not.toBeNull();
      expect(read!.accepted).toEqual(['necessary', 'analytics']);
      expect(read!.rejected).toEqual(['marketing']);
      expect(hasConsent()).toBe(true);
    });

    it('should clear consent', () => {
      const state = buildConsentState(['necessary'], []);
      writeConsent(state);
      expect(hasConsent()).toBe(true);

      clearConsent();
      expect(hasConsent()).toBe(false);
    });
  });

  describe('isCategoryAccepted', () => {
    it('should return true for necessary when no consent exists', () => {
      expect(isCategoryAccepted('necessary')).toBe(true);
    });

    it('should return false for non-necessary when no consent exists', () => {
      expect(isCategoryAccepted('analytics')).toBe(false);
    });

    it('should check accepted categories from cookie', () => {
      const state = buildConsentState(['necessary', 'analytics'], ['marketing']);
      writeConsent(state);

      expect(isCategoryAccepted('necessary')).toBe(true);
      expect(isCategoryAccepted('analytics')).toBe(true);
      expect(isCategoryAccepted('marketing')).toBe(false);
    });
  });

  describe('writeTcfCookie', () => {
    it('writes the euconsent-v2 cookie with the TC string', () => {
      writeTcfCookie('CPXxRAAAA.YAAA');
      expect(document.cookie).toContain('euconsent-v2=CPXxRAAAA.YAAA');
    });

    it('is a no-op when the TC string is empty', () => {
      writeTcfCookie('');
      expect(document.cookie).not.toContain('euconsent-v2=');
    });

    it('clearConsent removes both ConsentOS and TCF cookies', () => {
      writeConsent(buildConsentState(['necessary'], []));
      writeTcfCookie('CPXxRAAAA');
      clearConsent();
      expect(document.cookie).not.toContain('_consentos_consent=eyJ');
      expect(document.cookie).not.toContain('euconsent-v2=CPXxRAAAA');
    });
  });
});
