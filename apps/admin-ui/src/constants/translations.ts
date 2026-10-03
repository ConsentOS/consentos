/** The translation keys that the banner script expects.
 *
 * Shared across the org, site-group, and site translation editors so
 * an operator sees the exact same field set at every level of the
 * cascade. Kept in sync with apps/banner/src/i18n.ts's
 * TranslationStrings interface and the API's
 * src/services/translation_resolver.py's TRANSLATION_KEYS.
 */
interface TranslationKeyDef {
  key: string;
  label: string;
  placeholder: string;
  multiline?: boolean;
}

export const TRANSLATION_KEYS: TranslationKeyDef[] = [
  { key: 'title', label: 'Banner title', placeholder: 'We use cookies' },
  {
    key: 'description',
    label: 'Banner description',
    placeholder: 'We use cookies and similar technologies...',
    multiline: true,
  },
  { key: 'acceptAll', label: 'Accept all button', placeholder: 'Accept all' },
  { key: 'rejectAll', label: 'Reject all button', placeholder: 'Reject all' },
  {
    key: 'managePreferences',
    label: 'Manage preferences button',
    placeholder: 'Manage preferences',
  },
  { key: 'savePreferences', label: 'Save preferences button', placeholder: 'Save preferences' },
  { key: 'privacyPolicyLink', label: 'Privacy policy link text', placeholder: 'Privacy Policy' },
  { key: 'closeLabel', label: 'Close button label', placeholder: 'Close' },
  { key: 'categoryNecessary', label: 'Necessary category', placeholder: 'Necessary' },
  {
    key: 'categoryNecessaryDesc',
    label: 'Necessary description',
    placeholder: 'Essential for the website to function.',
  },
  { key: 'categoryFunctional', label: 'Functional category', placeholder: 'Functional' },
  {
    key: 'categoryFunctionalDesc',
    label: 'Functional description',
    placeholder: 'Enable enhanced functionality.',
  },
  { key: 'categoryAnalytics', label: 'Analytics category', placeholder: 'Analytics' },
  {
    key: 'categoryAnalyticsDesc',
    label: 'Analytics description',
    placeholder: 'Help us understand how visitors interact.',
  },
  { key: 'categoryMarketing', label: 'Marketing category', placeholder: 'Marketing' },
  {
    key: 'categoryMarketingDesc',
    label: 'Marketing description',
    placeholder: 'Used to deliver personalised advertisements.',
  },
  {
    key: 'categoryPersonalisation',
    label: 'Personalisation category',
    placeholder: 'Personalisation',
  },
  {
    key: 'categoryPersonalisationDesc',
    label: 'Personalisation description',
    placeholder: 'Enable content personalisation.',
  },
  {
    key: 'cookieCount',
    label: 'Cookie count text',
    placeholder: '{{count}} cookies used on this site',
  },
];

export const COMMON_LOCALES = [
  { code: 'en', name: 'English' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'es', name: 'Spanish' },
  { code: 'it', name: 'Italian' },
  { code: 'nl', name: 'Dutch' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'pl', name: 'Polish' },
  { code: 'sv', name: 'Swedish' },
  { code: 'da', name: 'Danish' },
  { code: 'fi', name: 'Finnish' },
  { code: 'no', name: 'Norwegian' },
  { code: 'cs', name: 'Czech' },
  { code: 'ro', name: 'Romanian' },
  { code: 'hu', name: 'Hungarian' },
  { code: 'bg', name: 'Bulgarian' },
  { code: 'hr', name: 'Croatian' },
  { code: 'sk', name: 'Slovak' },
  { code: 'sl', name: 'Slovenian' },
  { code: 'el', name: 'Greek' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'zh', name: 'Chinese' },
  { code: 'ar', name: 'Arabic' },
] as const;

export function localeName(code: string): string {
  const match = COMMON_LOCALES.find((l) => l.code === code);
  return match?.name ?? code.toUpperCase();
}
