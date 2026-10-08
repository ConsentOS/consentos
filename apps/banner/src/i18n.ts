/**
 * Banner i18n — locale detection and string translation.
 *
 * The banner sends its detected locale as ?locale= on the config request,
 * so the visitor's strings arrive with the config (see
 * ``SiteConfig.translations``) and no separate request is made here — the
 * banner just merges them over the built-in English defaults. Supports
 * string interpolation via {{key}} placeholders.
 */

import { escapeHtml, isAllowedLinkUrl } from './html';

export interface TranslationStrings {
  title: string;
  description: string;
  acceptAll: string;
  rejectAll: string;
  managePreferences: string;
  savePreferences: string;
  privacyPolicyLink: string;
  closeLabel: string;
  categoryNecessary: string;
  categoryNecessaryDesc: string;
  categoryFunctional: string;
  categoryFunctionalDesc: string;
  categoryAnalytics: string;
  categoryAnalyticsDesc: string;
  categoryMarketing: string;
  categoryMarketingDesc: string;
  categoryPersonalisation: string;
  categoryPersonalisationDesc: string;
  cookieCount: string;
}

/** Built-in English (GB) translations — used as fallback. */
export const DEFAULT_TRANSLATIONS: TranslationStrings = {
  title: 'We use cookies',
  description:
    'We use cookies and similar technologies to enhance your browsing experience, analyse site traffic, and personalise content. You can choose which categories to allow. [Privacy Policy]({{privacy_policy}}) [Terms & Conditions]({{terms}})',
  acceptAll: 'Accept all',
  rejectAll: 'Reject all',
  managePreferences: 'Manage preferences',
  savePreferences: 'Save preferences',
  privacyPolicyLink: 'Privacy Policy',
  closeLabel: 'Close',
  categoryNecessary: 'Necessary',
  categoryNecessaryDesc: 'Essential for the website to function. Always active.',
  categoryFunctional: 'Functional',
  categoryFunctionalDesc: 'Enable enhanced functionality and personalisation.',
  categoryAnalytics: 'Analytics',
  categoryAnalyticsDesc: 'Help us understand how visitors interact with the site.',
  categoryMarketing: 'Marketing',
  categoryMarketingDesc: 'Used to deliver personalised advertisements.',
  categoryPersonalisation: 'Personalisation',
  categoryPersonalisationDesc: 'Enable content personalisation based on your profile.',
  cookieCount: '{{count}} cookies used on this site',
};

/**
 * Detect the user's preferred locale.
 *
 * Priority: 1) explicit data-locale attribute, 2) navigator.language,
 * 3) document lang attribute, 4) 'en'.
 */
export function detectLocale(): string {
  // Check for explicit override on the script tag
  const scriptEl = document.querySelector('script[data-site-id]');
  const explicit = scriptEl?.getAttribute('data-locale');
  if (explicit) return normaliseLocale(explicit);

  // Browser language
  if (typeof navigator !== 'undefined' && navigator.language) {
    return normaliseLocale(navigator.language);
  }

  // Document lang attribute
  const docLang = document.documentElement.lang;
  if (docLang) return normaliseLocale(docLang);

  return 'en';
}

/**
 * Normalise a locale string to a two-letter language code.
 * e.g. 'en-GB' → 'en', 'fr-FR' → 'fr'
 */
export function normaliseLocale(locale: string): string {
  return locale.split('-')[0].toLowerCase();
}

/**
 * Select translations for a locale from the map embedded in the site
 * config and merge them over the built-in English defaults.
 *
 * No network request is made — translations arrive inside the config
 * (see ``SiteConfig.translations``). A missing locale, a missing map
 * (older API responses), or missing individual keys all fall back to the
 * English defaults.
 */
export function selectTranslations(
  embedded: Record<string, Partial<TranslationStrings>> | undefined,
  locale: string,
): TranslationStrings {
  const strings = embedded?.[locale];
  if (!strings) {
    return { ...DEFAULT_TRANSLATIONS };
  }

  // Merge over defaults so missing keys fall back to English
  return { ...DEFAULT_TRANSLATIONS, ...strings };
}

/**
 * Interpolate placeholders in a translation string.
 * e.g. interpolate('{{count}} cookies', { count: '12' }) → '12 cookies'
 */
export function interpolate(
  template: string,
  values: Record<string, string>,
): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => values[key] ?? '');
}

/**
 * Render markdown-style links as HTML anchor tags and strip orphaned links.
 *
 * The input is plain text: it is HTML-escaped first, then `[text](url)`
 * is converted to `<a href="url" ...>text</a>`. Only http(s) and relative
 * URLs become links; any other URL renders the link text on its own.
 * If the URL is empty (because the config value wasn't set), the entire
 * `[text]()` fragment is removed so no broken links appear.
 */
export function renderLinks(text: string, linkClass: string = 'consentos-banner__link'): string {
  // Remove links with empty URLs (including surrounding whitespace)
  let result = escapeHtml(text.replace(/\s*\[([^\]]*)\]\(\s*\)\s*/g, ''));
  result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label: string, url: string) => {
    if (!isAllowedLinkUrl(unescapeHtml(url))) {
      return label;
    }
    return `<a href="${url.trim()}" target="_blank" rel="noopener" class="${escapeHtml(linkClass)}">${label}</a>`;
  });
  return result;
}

/** Reverse ``escapeHtml`` so a URL can be checked as written. */
function unescapeHtml(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}
