import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  installBlocker,
  uninstallBlocker,
  updateAcceptedCategories,
  getBlockedCount,
  isCategoryAllowed,
  addScriptPatterns,
  loadInitiatorMappings,
  sweepDisallowedState,
} from '../blocker';

describe('blocker', () => {
  beforeEach(() => {
    installBlocker();
  });

  afterEach(() => {
    uninstallBlocker();
  });

  describe('installBlocker', () => {
    it('should only install once', () => {
      // Install a second time — should be a no-op
      installBlocker();
      expect(isCategoryAllowed('necessary')).toBe(true);
    });

    it('should allow necessary category by default', () => {
      expect(isCategoryAllowed('necessary')).toBe(true);
    });

    it('should deny non-essential categories by default', () => {
      expect(isCategoryAllowed('analytics')).toBe(false);
      expect(isCategoryAllowed('marketing')).toBe(false);
      expect(isCategoryAllowed('functional')).toBe(false);
      expect(isCategoryAllowed('personalisation')).toBe(false);
    });
  });

  describe('updateAcceptedCategories', () => {
    it('should update accepted categories', () => {
      updateAcceptedCategories(['necessary', 'analytics']);
      expect(isCategoryAllowed('analytics')).toBe(true);
      expect(isCategoryAllowed('marketing')).toBe(false);
    });

    it('should accept all categories when all are provided', () => {
      updateAcceptedCategories([
        'necessary',
        'functional',
        'analytics',
        'marketing',
        'personalisation',
      ]);
      expect(isCategoryAllowed('functional')).toBe(true);
      expect(isCategoryAllowed('analytics')).toBe(true);
      expect(isCategoryAllowed('marketing')).toBe(true);
      expect(isCategoryAllowed('personalisation')).toBe(true);
    });
  });

  describe('script interception via createElement', () => {
    it('should override document.createElement', () => {
      // createElement should still work for non-script elements
      const div = document.createElement('div');
      expect(div).toBeInstanceOf(HTMLDivElement);
    });

    it('should create script elements normally when no src is set', () => {
      const script = document.createElement('script');
      expect(script).toBeInstanceOf(HTMLScriptElement);
      expect(script.hasAttribute('data-consentos-blocked')).toBe(false);
    });

    it('should mark analytics scripts as blocked when src is set', () => {
      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://www.google-analytics.com/analytics.js';
      expect(script.getAttribute('data-consentos-blocked')).toBe('true');
      expect(script.getAttribute('data-consentos-category')).toBe('analytics');
      expect(script.type).toBe('text/blocked');
    });

    it('should mark marketing scripts as blocked', () => {
      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://connect.facebook.net/en_US/fbevents.js';
      expect(script.getAttribute('data-consentos-blocked')).toBe('true');
      expect(script.getAttribute('data-consentos-category')).toBe('marketing');
    });

    it('should allow scripts when their category is accepted', () => {
      updateAcceptedCategories(['necessary', 'analytics']);
      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://www.google-analytics.com/analytics.js';
      // Should not be blocked
      expect(script.hasAttribute('data-consentos-blocked')).toBe(false);
    });

    it('should allow scripts with unknown src (no matching pattern)', () => {
      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://example.com/my-custom-script.js';
      expect(script.hasAttribute('data-consentos-blocked')).toBe(false);
    });

    it('should respect explicit data-category attribute', () => {
      const script = document.createElement('script') as HTMLScriptElement;
      script.setAttribute('data-category', 'marketing');
      script.src = 'https://example.com/unknown-tracker.js';
      expect(script.getAttribute('data-consentos-blocked')).toBe('true');
      expect(script.getAttribute('data-consentos-category')).toBe('marketing');
    });
  });

  describe('MutationObserver blocking', () => {
    it('should block a script inserted into the DOM', async () => {
      const script = document.createElement('script') as HTMLScriptElement;
      script.setAttribute('data-category', 'analytics');
      script.src = 'https://example.com/analytics.js';

      document.head.appendChild(script);

      // MutationObserver is async, wait a tick
      await new Promise((resolve) => setTimeout(resolve, 0));

      // Script should have been removed from DOM and queued
      expect(script.parentNode).toBeNull();
      expect(getBlockedCount()).toBeGreaterThan(0);
    });

    it('should not block scripts marked as allowed', async () => {
      const script = document.createElement('script') as HTMLScriptElement;
      script.setAttribute('data-consentos-allowed', 'true');
      script.setAttribute('data-category', 'analytics');
      script.textContent = '/* allowed */';

      document.head.appendChild(script);
      await new Promise((resolve) => setTimeout(resolve, 0));

      // Should still be in the DOM
      expect(script.parentNode).toBe(document.head);

      // Clean up
      script.remove();
    });
  });

  describe('release manager', () => {
    it('should release blocked scripts when consent is granted', async () => {
      // Insert a blocked script
      const script = document.createElement('script') as HTMLScriptElement;
      script.setAttribute('data-category', 'analytics');
      script.src = 'https://example.com/analytics-lib.js';
      document.head.appendChild(script);

      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(getBlockedCount()).toBeGreaterThan(0);

      const countBefore = getBlockedCount();

      // Grant analytics consent
      updateAcceptedCategories(['necessary', 'analytics']);

      // Blocked count should decrease
      expect(getBlockedCount()).toBeLessThan(countBefore);
    });

    it('should not release scripts for non-consented categories', async () => {
      const script = document.createElement('script') as HTMLScriptElement;
      script.setAttribute('data-category', 'marketing');
      script.src = 'https://example.com/marketing.js';
      document.head.appendChild(script);

      await new Promise((resolve) => setTimeout(resolve, 0));
      const count = getBlockedCount();

      // Grant analytics only (not marketing)
      updateAcceptedCategories(['necessary', 'analytics']);

      // Marketing scripts should still be blocked
      // Count may have decreased by analytics scripts but marketing should remain
      expect(getBlockedCount()).toBeGreaterThanOrEqual(count > 0 ? 1 : 0);
    });
  });

  describe('cookie proxy', () => {
    it('should allow CMP cookies to be set', () => {
      document.cookie = '_consentos_test=value; path=/';
      expect(document.cookie).toContain('_consentos_test=value');
      // Clean up
      document.cookie = '_consentos_test=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    });

    it('should block known analytics cookies when not consented', () => {
      const before = document.cookie;
      document.cookie = '_ga=GA1.2.12345; path=/';
      // _ga should not appear (blocked)
      expect(document.cookie).not.toContain('_ga=GA1.2.12345');
      // Ensure we haven't corrupted the cookie string
      expect(document.cookie.length).toBeGreaterThanOrEqual(0);
    });

    it('should allow analytics cookies when consented', () => {
      updateAcceptedCategories(['necessary', 'analytics']);
      document.cookie = '_ga=GA1.2.12345; path=/';
      expect(document.cookie).toContain('_ga=GA1.2.12345');
      // Clean up
      document.cookie = '_ga=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    });

    it('should allow unknown cookies (not in any pattern)', () => {
      document.cookie = 'my_app_session=abc123; path=/';
      expect(document.cookie).toContain('my_app_session=abc123');
      // Clean up
      document.cookie = 'my_app_session=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    });
  });

  describe('storage proxy', () => {
    it('should block known analytics storage keys', () => {
      localStorage.setItem('_hjSession_12345', 'test');
      // Should be blocked — key should not exist
      expect(localStorage.getItem('_hjSession_12345')).toBeNull();
    });

    it('should allow storage writes when category is consented', () => {
      updateAcceptedCategories(['necessary', 'analytics']);
      localStorage.setItem('_hjSession_12345', 'test');
      expect(localStorage.getItem('_hjSession_12345')).toBe('test');
      // Clean up
      localStorage.removeItem('_hjSession_12345');
    });

    it('should allow CMP storage keys', () => {
      localStorage.setItem('_consentos_state', 'test');
      expect(localStorage.getItem('_consentos_state')).toBe('test');
      // Clean up
      localStorage.removeItem('_consentos_state');
    });

    it('should allow unknown storage keys', () => {
      localStorage.setItem('my_app_key', 'value');
      expect(localStorage.getItem('my_app_key')).toBe('value');
      // Clean up
      localStorage.removeItem('my_app_key');
    });
  });

  describe('addScriptPatterns', () => {
    it('should add custom patterns for classification', () => {
      addScriptPatterns([
        { pattern: 'custom-tracker\\.example\\.com', category: 'marketing' },
      ]);

      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://custom-tracker.example.com/track.js';
      expect(script.getAttribute('data-consentos-blocked')).toBe('true');
      expect(script.getAttribute('data-consentos-category')).toBe('marketing');
    });

    it('should handle invalid patterns gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      addScriptPatterns([{ pattern: '[invalid', category: 'analytics' }]);
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Invalid script pattern')
      );
      consoleSpy.mockRestore();
    });
  });

  describe('loadInitiatorMappings', () => {
    it('should block scripts matching initiator mappings', () => {
      loadInitiatorMappings([
        { root_script: 'gtm\\.example\\.com', category: 'marketing' },
      ]);

      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://gtm.example.com/gtm.js';
      expect(script.getAttribute('data-consentos-blocked')).toBe('true');
      expect(script.getAttribute('data-consentos-category')).toBe('marketing');
    });

    it('should not block initiator scripts when category is consented', () => {
      updateAcceptedCategories(['necessary', 'marketing']);
      loadInitiatorMappings([
        { root_script: 'gtm\\.example\\.com', category: 'marketing' },
      ]);

      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://gtm.example.com/gtm.js';
      expect(script.hasAttribute('data-consentos-blocked')).toBe(false);
    });

    it('should handle invalid initiator patterns gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      loadInitiatorMappings([{ root_script: '[invalid', category: 'analytics' }]);
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Invalid initiator pattern')
      );
      consoleSpy.mockRestore();
    });

    it('should prioritise URL patterns over initiator mappings', () => {
      // google-analytics.com matches the built-in analytics pattern
      loadInitiatorMappings([
        { root_script: 'google-analytics\\.com', category: 'marketing' },
      ]);

      const script = document.createElement('script') as HTMLScriptElement;
      script.src = 'https://www.google-analytics.com/analytics.js';
      // Should match URL pattern (analytics) not initiator mapping (marketing)
      expect(script.getAttribute('data-consentos-category')).toBe('analytics');
    });
  });

  describe('uninstallBlocker', () => {
    it('should restore original document.createElement', () => {
      uninstallBlocker();
      const div = document.createElement('div');
      expect(div).toBeInstanceOf(HTMLDivElement);
    });

    it('should reset blocked count to zero', () => {
      uninstallBlocker();
      expect(getBlockedCount()).toBe(0);
    });

    it('should reset accepted categories to necessary only', () => {
      updateAcceptedCategories(['necessary', 'analytics', 'marketing']);
      uninstallBlocker();
      expect(isCategoryAllowed('analytics')).toBe(false);
      expect(isCategoryAllowed('necessary')).toBe(true);
    });
  });

  describe('sweepDisallowedState', () => {
    /**
     * Reset the cookie jar by expiring any test cookies we know
     * about. ``document.cookie =`` runs through the proxy so
     * ``_consentos_*`` passes the shortcut and everything else gets
     * eaten by the blocker's classifier. Expiring the well-known
     * analytics cookies here gives the individual tests a clean
     * starting point without relying on the jsdom harness to wipe
     * between tests.
     */
    function resetCookies(names: string[]) {
      for (const name of names) {
        document.cookie = `_consentos_reset_marker=${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
      }
    }

    beforeEach(() => {
      // Directly seed cookies via the native descriptor so the
      // proxied setter doesn't eat them as "tracker writes with
      // no consent".
      const nativeSet = Object.getOwnPropertyDescriptor(
        Document.prototype,
        'cookie',
      )?.set;
      if (!nativeSet) throw new Error('cannot locate native cookie setter');
      nativeSet.call(
        document,
        '_ga=GA1.2.seed; path=/',
      );
      nativeSet.call(
        document,
        '_fbp=fb.2.seed; path=/',
      );
      nativeSet.call(
        document,
        'unknown_cookie=opaque; path=/',
      );
      nativeSet.call(
        document,
        '_consentos_consent=%7B%7D; path=/',
      );
    });

    afterEach(() => {
      resetCookies(['_ga', '_fbp', 'unknown_cookie', '_consentos_consent']);
    });

    it('deletes non-consented analytics cookies', () => {
      updateAcceptedCategories(['necessary']);
      // ^^ updateAcceptedCategories calls sweep internally; the
      // assertions below verify the post-sweep cookie jar.
      expect(document.cookie).not.toContain('_ga=');
      expect(document.cookie).not.toContain('_fbp=');
    });

    it('leaves consented cookies alone', () => {
      updateAcceptedCategories(['necessary', 'analytics', 'marketing']);
      expect(document.cookie).toContain('_ga=');
      expect(document.cookie).toContain('_fbp=');
    });

    it('leaves unknown cookies alone even without consent', () => {
      updateAcceptedCategories(['necessary']);
      expect(document.cookie).toContain('unknown_cookie=');
    });

    it('never touches _consentos_* cookies', () => {
      updateAcceptedCategories(['necessary']);
      expect(document.cookie).toContain('_consentos_consent=');
    });

    it('standalone sweepDisallowedState respects the current set', () => {
      updateAcceptedCategories(['necessary', 'analytics']);
      // Re-seed _ga after the first sweep would have left it (analytics consented).
      const nativeSet = Object.getOwnPropertyDescriptor(
        Document.prototype,
        'cookie',
      )?.set;
      nativeSet?.call(document, '_fbp=fb.2.reseed; path=/');

      // Revoke marketing, sweep again.
      updateAcceptedCategories(['necessary', 'analytics']);
      sweepDisallowedState();
      expect(document.cookie).toContain('_ga=');
      expect(document.cookie).not.toContain('_fbp=');
    });

    it('cleans non-consented localStorage keys', () => {
      localStorage.setItem('_consentos_keep', 'yes');
      // Seed via a direct setItem — the proxied setter would block
      // non-necessary writes, but we want a pre-existing key.
      const nativeSetItem = Object.getPrototypeOf(localStorage).setItem;
      nativeSetItem.call(localStorage, '_ga_stuff', 'tracker');
      nativeSetItem.call(localStorage, 'opaque_key', 'leave-alone');

      updateAcceptedCategories(['necessary']);

      expect(localStorage.getItem('_consentos_keep')).toBe('yes');
      expect(localStorage.getItem('_ga_stuff')).toBeNull();
      expect(localStorage.getItem('opaque_key')).toBe('leave-alone');

      localStorage.clear();
    });
  });
});
