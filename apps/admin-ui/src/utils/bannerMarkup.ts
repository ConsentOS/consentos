/**
 * Markup helpers for the banner preview. They mirror the banner script's
 * ``html.ts`` and ``renderLinks`` so the preview escapes text, checks
 * colours and fonts, and renders links the same way as the live banner.
 */

export function escapeHtml(value: string): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function unescapeHtml(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

const SCHEME_RE = /^([a-z][a-z0-9+.-]*):/i;
const PROTOCOL_RELATIVE_RE = /^[/\\][/\\]/;

/** True for an absolute http(s) URL or a relative reference. */
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

export function isValidColour(value: unknown): value is string {
  return isSafeCssValue(value, false);
}

export function isValidFontFamily(value: unknown): value is string {
  return isSafeCssValue(value, true);
}

/** ``value`` when it is a valid colour, otherwise ``fallback``. */
export function colourOr(value: unknown, fallback: string): string {
  return isValidColour(value) ? value.trim() : fallback;
}

/** ``value`` when it is a finite, non-negative number, otherwise ``fallback``. */
export function pixelsOr(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback;
}

/** Replace ``{{key}}`` placeholders, leaving unknown keys empty. */
export function interpolate(template: string, values: Record<string, string>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => values[key] ?? '');
}

/**
 * Escape ``text`` and turn ``[label](url)`` into links. Links with an
 * empty URL are removed, and URLs that are not http(s) or relative
 * render as their label only.
 */
export function renderLinks(text: string, linkClass: string = 'consentos-banner__link'): string {
  let result = escapeHtml(text.replace(/\s*\[([^\]]*)\]\(\s*\)\s*/g, ''));
  result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label: string, url: string) => {
    if (!isAllowedLinkUrl(unescapeHtml(url))) {
      return label;
    }
    return `<a href="${url.trim()}" target="_blank" rel="noopener" class="${escapeHtml(linkClass)}">${label}</a>`;
  });
  return result;
}
