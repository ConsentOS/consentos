import { describe, it, expect, vi, beforeEach } from 'vitest';

import {
  DEFAULT_TRANSLATIONS,
  detectLocale,
  interpolate,
  normaliseLocale,
  renderLinks,
  selectTranslations,
} from '../i18n';

describe('i18n', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('DEFAULT_TRANSLATIONS', () => {
    it('should have all required keys', () => {
      expect(DEFAULT_TRANSLATIONS.title).toBe('We use cookies');
      expect(DEFAULT_TRANSLATIONS.acceptAll).toBe('Accept all');
      expect(DEFAULT_TRANSLATIONS.rejectAll).toBe('Reject all');
      expect(DEFAULT_TRANSLATIONS.managePreferences).toBe('Manage preferences');
      expect(DEFAULT_TRANSLATIONS.savePreferences).toBe('Save preferences');
      expect(DEFAULT_TRANSLATIONS.privacyPolicyLink).toBe('Privacy Policy');
      expect(DEFAULT_TRANSLATIONS.closeLabel).toBe('Close');
    });

    it('should have all category translations', () => {
      expect(DEFAULT_TRANSLATIONS.categoryNecessary).toBe('Necessary');
      expect(DEFAULT_TRANSLATIONS.categoryFunctional).toBe('Functional');
      expect(DEFAULT_TRANSLATIONS.categoryAnalytics).toBe('Analytics');
      expect(DEFAULT_TRANSLATIONS.categoryMarketing).toBe('Marketing');
      expect(DEFAULT_TRANSLATIONS.categoryPersonalisation).toBe('Personalisation');
    });

    it('should have category descriptions', () => {
      expect(DEFAULT_TRANSLATIONS.categoryNecessaryDesc).toBeTruthy();
      expect(DEFAULT_TRANSLATIONS.categoryFunctionalDesc).toBeTruthy();
      expect(DEFAULT_TRANSLATIONS.categoryAnalyticsDesc).toBeTruthy();
      expect(DEFAULT_TRANSLATIONS.categoryMarketingDesc).toBeTruthy();
      expect(DEFAULT_TRANSLATIONS.categoryPersonalisationDesc).toBeTruthy();
    });

    it('should have cookie count template with placeholder', () => {
      expect(DEFAULT_TRANSLATIONS.cookieCount).toContain('{{count}}');
    });
  });

  describe('normaliseLocale', () => {
    it('should extract language code from locale', () => {
      expect(normaliseLocale('en-GB')).toBe('en');
      expect(normaliseLocale('fr-FR')).toBe('fr');
      expect(normaliseLocale('de-DE')).toBe('de');
    });

    it('should handle simple language codes', () => {
      expect(normaliseLocale('en')).toBe('en');
      expect(normaliseLocale('fr')).toBe('fr');
    });

    it('should lowercase the result', () => {
      expect(normaliseLocale('EN-GB')).toBe('en');
      expect(normaliseLocale('FR')).toBe('fr');
    });
  });

  describe('detectLocale', () => {
    it('should use data-locale attribute when present', () => {
      const script = document.createElement('script');
      script.setAttribute('data-site-id', 'site-1');
      script.setAttribute('data-locale', 'fr-FR');
      document.head.appendChild(script);

      expect(detectLocale()).toBe('fr');

      script.remove();
    });

    it('should fall back to navigator.language', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-DE');
      expect(detectLocale()).toBe('de');
    });

    it('should fall back to document lang', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('');
      document.documentElement.lang = 'es';

      expect(detectLocale()).toBe('es');

      document.documentElement.lang = '';
    });

    it('should default to en', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('');
      document.documentElement.lang = '';

      expect(detectLocale()).toBe('en');
    });
  });

  describe('selectTranslations', () => {
    it('should return defaults when no translations are embedded', () => {
      const t = selectTranslations(undefined, 'de');
      expect(t.title).toBe(DEFAULT_TRANSLATIONS.title);
      expect(t.acceptAll).toBe(DEFAULT_TRANSLATIONS.acceptAll);
    });

    it('should return defaults when the requested locale is absent', () => {
      const t = selectTranslations({ fr: { title: 'Nous utilisons des cookies' } }, 'de');
      expect(t.title).toBe(DEFAULT_TRANSLATIONS.title);
    });

    it('should merge the locale strings over defaults', () => {
      const t = selectTranslations(
        { de: { title: 'Wir verwenden Cookies', acceptAll: 'Alle akzeptieren' } },
        'de',
      );

      expect(t.title).toBe('Wir verwenden Cookies');
      expect(t.acceptAll).toBe('Alle akzeptieren');
      // Missing keys should fall back to English
      expect(t.rejectAll).toBe(DEFAULT_TRANSLATIONS.rejectAll);
    });

    it('should select the matching locale from a multi-locale map', () => {
      const embedded = {
        de: { title: 'Wir verwenden Cookies' },
        fr: { title: 'Nous utilisons des cookies' },
      };
      expect(selectTranslations(embedded, 'fr').title).toBe('Nous utilisons des cookies');
    });
  });

  describe('interpolate', () => {
    it('should replace placeholders with values', () => {
      expect(interpolate('{{count}} cookies', { count: '12' })).toBe('12 cookies');
    });

    it('should handle multiple placeholders', () => {
      expect(interpolate('{{a}} and {{b}}', { a: 'X', b: 'Y' })).toBe('X and Y');
    });

    it('should replace missing keys with empty string', () => {
      expect(interpolate('Hello {{name}}', {})).toBe('Hello ');
    });

    it('should handle templates without placeholders', () => {
      expect(interpolate('No placeholders', { key: 'value' })).toBe('No placeholders');
    });

    it('should handle empty template', () => {
      expect(interpolate('', { key: 'value' })).toBe('');
    });
  });

  describe('renderLinks', () => {
    it('converts markdown links to anchors', () => {
      expect(renderLinks('See [Privacy](https://example.com/p).')).toBe(
        'See <a href="https://example.com/p" target="_blank" rel="noopener" class="consentos-banner__link">Privacy</a>.',
      );
    });

    it('accepts relative URLs', () => {
      expect(renderLinks('[Terms](/terms)', 'x')).toBe(
        '<a href="/terms" target="_blank" rel="noopener" class="x">Terms</a>',
      );
    });

    it('removes links with empty URLs', () => {
      expect(renderLinks('Read more. [Privacy]()')).toBe('Read more.');
    });

    it('escapes surrounding text and link labels', () => {
      expect(renderLinks('<b>Hi</b> [<i>P</i>](https://example.com)')).toBe(
        '&lt;b&gt;Hi&lt;/b&gt; <a href="https://example.com" target="_blank" rel="noopener" class="consentos-banner__link">&lt;i&gt;P&lt;/i&gt;</a>',
      );
    });

    it('escapes quotes and ampersands in the href', () => {
      expect(renderLinks('[P](https://example.com/?a=1&b="2")')).toContain(
        'href="https://example.com/?a=1&amp;b=&quot;2&quot;"',
      );
    });

    it('renders the label as plain text for other URL schemes and protocol-relative URLs', () => {
      expect(renderLinks('[P](javascript:void(0))')).not.toContain('<a');
      expect(renderLinks('[P](data:text/html,hi)')).toBe('P');
      expect(renderLinks('[P](JavaScript:x)')).toBe('P');
      expect(renderLinks('[P](mailto:a@example.com)')).toBe('P');
      expect(renderLinks('[P](//example.com/p)')).toBe('P');
    });
  });
});
