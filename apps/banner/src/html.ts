/**
 * Helpers for building banner markup from translated text and site
 * config values.
 */

/** Escape a string for use in HTML text or a quoted attribute value. */
export function escapeHtml(value: string): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const SCHEME_RE = /^([a-z][a-z0-9+.-]*):/i;
const PROTOCOL_RELATIVE_RE = /^[/\\][/\\]/;

/**
 * Return ``true`` when ``url`` is an absolute http(s) URL or a relative
 * reference (no scheme). Anything else, such as ``mailto:``, ``data:``
 * or a protocol-relative ``//host`` URL, is not used as a link target.
 */
export function isAllowedLinkUrl(url: string): boolean {
  const trimmed = url.trim();
  if (trimmed === '' || /[\s\u0000-\u001f\u007f]/.test(trimmed)) {
    return false;
  }
  const scheme = SCHEME_RE.exec(trimmed);
  if (!scheme) {
    return !PROTOCOL_RELATIVE_RE.test(trimmed);
  }
  const name = scheme[1].toLowerCase();
  return name === 'http' || name === 'https';
}

const MAX_CSS_VALUE_LENGTH = 200;
const CONTROL_CHAR_RE = /\p{Cc}/u;
const FORBIDDEN_CSS_RE = /[;{}<>\\]|\/\*|\*\/|url\(/i;
const QUOTE_RE = /["']/;

/**
 * Return ``true`` for a CSS value that cannot end its declaration or rule.
 *
 * Rejects characters that would close the declaration, block or style
 * element, CSS comments and escapes, ``url()`` and control characters.
 * Quotes are only accepted when ``allowQuotes`` is set and every quoted
 * string is closed. Matches the API's banner config validation.
 */
function isSafeCssValue(value: unknown, allowQuotes: boolean): value is string {
  if (typeof value !== 'string') return false;
  const v = value.trim();
  const codePoints = Array.from(v).length;
  if (codePoints === 0 || codePoints > MAX_CSS_VALUE_LENGTH) return false;
  if (CONTROL_CHAR_RE.test(v) || FORBIDDEN_CSS_RE.test(v)) return false;
  if (!allowQuotes) return !QUOTE_RE.test(v);
  return quotesBalanced(v);
}

function quotesBalanced(value: string): boolean {
  let openQuote: string | null = null;
  for (const ch of value) {
    if (openQuote === null && (ch === '"' || ch === "'")) {
      openQuote = ch;
    } else if (ch === openQuote) {
      openQuote = null;
    }
  }
  return openQuote === null;
}

/** Return ``true`` for a colour value such as a hex, ``rgb()``, ``var()`` or ``color-mix()``. */
export function isValidColour(value: unknown): value is string {
  return isSafeCssValue(value, false);
}

/** Return ``true`` for a font-family list; quoted family names are allowed. */
export function isValidFontFamily(value: unknown): value is string {
  return isSafeCssValue(value, true);
}
