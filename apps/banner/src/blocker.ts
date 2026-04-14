/**
 * blocker.ts — Script interceptor, cookie blocker, and release manager.
 *
 * Installs before any third-party scripts run. Intercepts script creation,
 * proxies document.cookie and Storage writes, and maintains a queue of
 * blocked resources that are released per-category when consent is granted.
 */

import type { CategorySlug, InitiatorMapping } from './types';

/** A script element that was blocked, along with its assigned category. */
interface BlockedScript {
  /** The original script element or a clone of it. */
  element: HTMLScriptElement;
  /** The consent category this script belongs to. */
  category: CategorySlug;
}

/** Pattern-to-category mapping for URL-based script classification. */
interface ScriptPattern {
  pattern: RegExp;
  category: CategorySlug;
}

/** Categories that have been consented to. */
let acceptedCategories: Set<CategorySlug> = new Set(['necessary']);

/** Queue of blocked scripts awaiting consent. */
const blockedScripts: BlockedScript[] = [];

/** URL patterns for classifying scripts by category. */
const scriptPatterns: ScriptPattern[] = [];

/** Root initiator URL → category mappings for root-level blocking. */
const initiatorMappings: Array<{ pattern: RegExp; category: CategorySlug }> = [];

/** Whether the blocker has been installed. */
let installed = false;

/** Original document.createElement reference. */
let originalCreateElement: typeof document.createElement;

/** Original document.cookie descriptor. */
let originalCookieDescriptor: PropertyDescriptor | undefined;

/** Original Storage.prototype.setItem reference. */
let originalLocalStorageSetItem: typeof Storage.prototype.setItem;

// ─── Well-known script patterns (built-in defaults) ───

const BUILTIN_PATTERNS: ScriptPattern[] = [
  // Analytics
  { pattern: /google-analytics\.com/i, category: 'analytics' },
  { pattern: /googletagmanager\.com/i, category: 'analytics' },
  { pattern: /gtag\/js/i, category: 'analytics' },
  { pattern: /analytics\./i, category: 'analytics' },
  { pattern: /hotjar\.com/i, category: 'analytics' },
  { pattern: /clarity\.ms/i, category: 'analytics' },
  { pattern: /plausible\.io/i, category: 'analytics' },
  { pattern: /matomo\./i, category: 'analytics' },

  // Marketing
  { pattern: /doubleclick\.net/i, category: 'marketing' },
  { pattern: /facebook\.net/i, category: 'marketing' },
  { pattern: /fbevents\.js/i, category: 'marketing' },
  { pattern: /connect\.facebook/i, category: 'marketing' },
  { pattern: /ads-twitter\.com/i, category: 'marketing' },
  { pattern: /linkedin\.com\/insight/i, category: 'marketing' },
  { pattern: /snap\.licdn\.com/i, category: 'marketing' },
  { pattern: /tiktok\.com\/i18n/i, category: 'marketing' },
  { pattern: /googlesyndication\.com/i, category: 'marketing' },
  { pattern: /adservice\.google/i, category: 'marketing' },

  // Functional
  { pattern: /intercom\.com/i, category: 'functional' },
  { pattern: /crisp\.chat/i, category: 'functional' },
  { pattern: /livechatinc\.com/i, category: 'functional' },
  { pattern: /zendesk\.com/i, category: 'functional' },
];

// ─── Public API ───

/** Install all interception hooks. Call once, as early as possible. */
export function installBlocker(): void {
  if (installed) return;
  installed = true;

  // Merge built-in patterns
  scriptPatterns.push(...BUILTIN_PATTERNS);

  // Install hooks
  installCreateElementOverride();
  installMutationObserver();
  installCookieProxy();
  installStorageProxy();
}

/** Add custom URL-to-category patterns (e.g. from site config allow-list). */
export function addScriptPatterns(patterns: Array<{ pattern: string; category: CategorySlug }>): void {
  for (const p of patterns) {
    try {
      scriptPatterns.push({ pattern: new RegExp(p.pattern, 'i'), category: p.category });
    } catch {
      console.warn(`[ConsentOS] Invalid script pattern: ${p.pattern}`);
    }
  }
}

/**
 * Load initiator mappings from the site config. Each mapping identifies a root
 * script URL that is known to set cookies in a given category via a chain of
 * child scripts. Blocking the root prevents the entire chain from executing.
 */
export function loadInitiatorMappings(mappings: InitiatorMapping[]): void {
  for (const m of mappings) {
    try {
      initiatorMappings.push({ pattern: new RegExp(m.root_script, 'i'), category: m.category });
    } catch {
      console.warn(`[ConsentOS] Invalid initiator pattern: ${m.root_script}`);
    }
  }
}

/**
 * Update the set of accepted categories, release any blocked scripts
 * that now have consent, and sweep any existing cookies / storage
 * items that belong to a category the visitor has **not** consented
 * to. Consented categories are left untouched — those cookies are
 * presumed to be in use by the site.
 */
export function updateAcceptedCategories(categories: CategorySlug[]): void {
  acceptedCategories = new Set(categories);
  releaseBlockedScripts();
  sweepDisallowedState();
}

/**
 * Delete any existing cookies and storage items whose classified
 * category isn't currently consented. Runs on install and every
 * consent-state update so historical trackers from pre-consent, a
 * previous session, or a narrowed consent decision get removed.
 * Unknown / unclassified cookies are left alone since we can't
 * attribute them to a category.
 */
export function sweepDisallowedState(): void {
  sweepDisallowedCookies();
  sweepDisallowedStorage();
}

/** Get the current blocked script count (useful for debugging/reporting). */
export function getBlockedCount(): number {
  return blockedScripts.length;
}

/** Check whether a given category is currently accepted. */
export function isCategoryAllowed(category: CategorySlug): boolean {
  return acceptedCategories.has(category);
}

// ─── Script interception ───

/**
 * Override document.createElement to intercept <script> creation.
 * When a script is created and its src matches a known pattern,
 * we set its type to 'text/blocked' to prevent execution.
 */
function installCreateElementOverride(): void {
  originalCreateElement = document.createElement.bind(document);

  document.createElement = function (
    tagName: string,
    options?: ElementCreationOptions
  ): HTMLElement {
    const element = originalCreateElement(tagName, options);

    if (tagName.toLowerCase() === 'script') {
      const script = element as HTMLScriptElement;
      wrapScriptElement(script);
    }

    return element;
  } as typeof document.createElement;
}

/**
 * Wrap a script element's `src` setter so that when a src is assigned,
 * we can classify and potentially block it.
 */
function wrapScriptElement(script: HTMLScriptElement): void {
  const originalSrcDescriptor = Object.getOwnPropertyDescriptor(
    HTMLScriptElement.prototype,
    'src'
  );
  if (!originalSrcDescriptor) return;

  let pendingSrc = '';

  Object.defineProperty(script, 'src', {
    get() {
      return pendingSrc || originalSrcDescriptor.get?.call(this) || '';
    },
    set(value: string) {
      pendingSrc = value;
      const category = classifyScript(value, script);

      if (category && category !== 'necessary' && !acceptedCategories.has(category)) {
        // Block: change type to prevent execution
        script.type = 'text/blocked';
        script.setAttribute('data-consentos-blocked', 'true');
        script.setAttribute('data-consentos-category', category);
        script.setAttribute('data-consentos-original-src', value);
      }

      originalSrcDescriptor.set?.call(this, value);
    },
    configurable: true,
    enumerable: true,
  });
}

/**
 * MutationObserver watches for script elements being added to the DOM.
 * If a script should be blocked, we remove it and queue it.
 */
function installMutationObserver(): void {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node instanceof HTMLScriptElement) {
          handleInsertedScript(node);
        }
      }
    }
  });

  // Observe as early as possible
  if (document.documentElement) {
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }
}

/** Handle a script element that was just inserted into the DOM. */
function handleInsertedScript(script: HTMLScriptElement): void {
  // Skip if it's our own script or already processed
  if (script.hasAttribute('data-consentos-allowed') || script.hasAttribute('data-consentos-queued')) {
    return;
  }

  // Check explicit data-category attribute first
  const explicitCategory = script.getAttribute('data-category') as CategorySlug | null;
  const src = script.getAttribute('data-consentos-original-src') || script.src || '';
  const category = explicitCategory || classifyScript(src, script);

  // Necessary scripts always pass through
  if (!category || category === 'necessary') {
    return;
  }

  // If already consented, allow through
  if (acceptedCategories.has(category)) {
    return;
  }

  // Block: remove from DOM and queue
  script.setAttribute('data-consentos-queued', 'true');

  // Clone the script for later re-insertion
  const clone = originalCreateElement('script') as HTMLScriptElement;
  // Copy attributes
  for (const attr of Array.from(script.attributes)) {
    if (attr.name !== 'type' && attr.name !== 'data-consentos-blocked' && attr.name !== 'data-consentos-queued') {
      clone.setAttribute(attr.name, attr.value);
    }
  }
  // Copy inline content
  if (script.textContent) {
    clone.textContent = script.textContent;
  }
  // Restore original src if it was rewritten
  const originalSrc = script.getAttribute('data-consentos-original-src');
  if (originalSrc) {
    clone.setAttribute('data-consentos-original-src', originalSrc);
  }

  blockedScripts.push({ element: clone, category });

  // Remove from DOM to prevent execution
  if (script.parentNode) {
    script.parentNode.removeChild(script);
  }
}

// ─── Cookie proxy ───

/**
 * Proxy document.cookie setter to block cookie writes from
 * non-essential categories. We check the cookie name against
 * known patterns and the ConsentOS's own cookie is always allowed.
 */
function installCookieProxy(): void {
  originalCookieDescriptor = Object.getOwnPropertyDescriptor(
    Document.prototype,
    'cookie'
  );
  if (!originalCookieDescriptor) return;

  Object.defineProperty(document, 'cookie', {
    get() {
      return originalCookieDescriptor!.get?.call(document) ?? '';
    },
    set(value: string) {
      // Always allow ConsentOS's own cookies
      if (value.startsWith('_consentos_')) {
        originalCookieDescriptor!.set?.call(document, value);
        return;
      }

      // If consent hasn't been collected yet and we're in opt-in mode,
      // block all non-essential cookie writes
      if (!allNonEssentialConsented()) {
        const cookieName = parseCookieName(value);
        const category = classifyCookie(cookieName);

        if (category && category !== 'necessary' && !acceptedCategories.has(category)) {
          // Silently block
          return;
        }
      }

      originalCookieDescriptor!.set?.call(document, value);
    },
    configurable: true,
  });
}

// ─── Storage proxy ───

/** Proxy localStorage and sessionStorage setItem to block non-essential writes. */
function installStorageProxy(): void {
  if (typeof Storage !== 'undefined') {
    originalLocalStorageSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string): void {
      if (shouldBlockStorageWrite(key)) return;
      originalLocalStorageSetItem.call(this, key, value);
    };
  }
}

/** Check if a storage write should be blocked. */
function shouldBlockStorageWrite(key: string): boolean {
  // Always allow ConsentOS's own storage
  if (key.startsWith('_consentos_')) return false;

  // If all non-essential categories are consented, allow everything
  if (allNonEssentialConsented()) return false;

  // Block known tracking storage keys
  const category = classifyStorageKey(key);
  if (category && category !== 'necessary' && !acceptedCategories.has(category)) {
    return true;
  }

  return false;
}

// ─── Release manager ───

/** Release blocked scripts whose categories are now accepted. */
function releaseBlockedScripts(): void {
  const toRelease: BlockedScript[] = [];
  const remaining: BlockedScript[] = [];

  for (const blocked of blockedScripts) {
    if (acceptedCategories.has(blocked.category)) {
      toRelease.push(blocked);
    } else {
      remaining.push(blocked);
    }
  }

  // Clear and repopulate the queue
  blockedScripts.length = 0;
  blockedScripts.push(...remaining);

  // Re-insert released scripts in order
  for (const { element } of toRelease) {
    const script = originalCreateElement('script') as HTMLScriptElement;

    // Copy all attributes
    for (const attr of Array.from(element.attributes)) {
      if (attr.name !== 'data-consentos-blocked' && attr.name !== 'data-consentos-queued' && attr.name !== 'data-consentos-category') {
        script.setAttribute(attr.name, attr.value);
      }
    }

    // Use original src if stored
    const originalSrc = element.getAttribute('data-consentos-original-src');
    if (originalSrc) {
      script.src = originalSrc;
      script.removeAttribute('data-consentos-original-src');
    }

    // Copy inline script content
    if (element.textContent && !script.src) {
      script.textContent = element.textContent;
    }

    // Mark as allowed so the observer doesn't re-block it
    script.setAttribute('data-consentos-allowed', 'true');

    // Insert into head
    (document.head || document.documentElement).appendChild(script);
  }
}

// ─── Classification helpers ───

/** Classify a script by its URL against known patterns and initiator mappings. */
function classifyScript(src: string, script: HTMLScriptElement): CategorySlug | null {
  if (!src) return null;

  // Explicit data-category always wins
  const explicit = script.getAttribute('data-category') as CategorySlug | null;
  if (explicit) return explicit;

  // Match against URL patterns
  for (const { pattern, category } of scriptPatterns) {
    if (pattern.test(src)) return category;
  }

  // Check initiator mappings — block root scripts that are known to set
  // cookies in non-consented categories via downstream child scripts
  for (const { pattern, category } of initiatorMappings) {
    if (pattern.test(src)) return category;
  }

  return null;
}

/** Well-known cookie name patterns mapped to categories. */
const COOKIE_PATTERNS: Array<{ pattern: RegExp; category: CategorySlug }> = [
  // Analytics
  { pattern: /^_ga/i, category: 'analytics' },
  { pattern: /^_gid$/i, category: 'analytics' },
  { pattern: /^_gat/i, category: 'analytics' },
  { pattern: /^_hjSession/i, category: 'analytics' },
  { pattern: /^_hj/i, category: 'analytics' },
  { pattern: /^_pk_/i, category: 'analytics' },
  { pattern: /^_clck$/i, category: 'analytics' },
  { pattern: /^_clsk$/i, category: 'analytics' },

  // Marketing
  { pattern: /^_fbp$/i, category: 'marketing' },
  { pattern: /^_fbc$/i, category: 'marketing' },
  { pattern: /^_gcl_/i, category: 'marketing' },
  { pattern: /^IDE$/i, category: 'marketing' },
  { pattern: /^NID$/i, category: 'marketing' },
  { pattern: /^test_cookie$/i, category: 'marketing' },
  { pattern: /^_uetsid/i, category: 'marketing' },
  { pattern: /^_uetvid/i, category: 'marketing' },

  // Functional
  { pattern: /^intercom-/i, category: 'functional' },
  { pattern: /^crisp-/i, category: 'functional' },
];

/** Classify a cookie by its name. */
function classifyCookie(name: string): CategorySlug | null {
  for (const { pattern, category } of COOKIE_PATTERNS) {
    if (pattern.test(name)) return category;
  }
  return null;
}

/** Well-known storage key patterns. */
const STORAGE_PATTERNS: Array<{ pattern: RegExp; category: CategorySlug }> = [
  { pattern: /^_ga/i, category: 'analytics' },
  { pattern: /^_hj/i, category: 'analytics' },
  { pattern: /^intercom\./i, category: 'functional' },
  { pattern: /^crisp-/i, category: 'functional' },
  { pattern: /^fb_/i, category: 'marketing' },
];

/** Classify a storage key by known patterns. */
function classifyStorageKey(key: string): CategorySlug | null {
  for (const { pattern, category } of STORAGE_PATTERNS) {
    if (pattern.test(key)) return category;
  }
  return null;
}

/** Parse the cookie name from a Set-Cookie string. */
function parseCookieName(cookieString: string): string {
  const eqIndex = cookieString.indexOf('=');
  if (eqIndex === -1) return cookieString.trim();
  return cookieString.substring(0, eqIndex).trim();
}

/** Check if all non-essential categories have been consented to. */
function allNonEssentialConsented(): boolean {
  return (
    acceptedCategories.has('functional') &&
    acceptedCategories.has('analytics') &&
    acceptedCategories.has('marketing') &&
    acceptedCategories.has('personalisation')
  );
}

// ─── Sweep existing state ──────────────────────────────────────────────

/** Delete classified cookies that aren't in a consented category. */
function sweepDisallowedCookies(): void {
  if (typeof document === 'undefined') return;
  if (!originalCookieDescriptor?.set) return;

  const cookieHeader = document.cookie || '';
  if (!cookieHeader) return;

  const nativeSet = originalCookieDescriptor.set.bind(document);
  const seen = new Set<string>();

  for (const entry of cookieHeader.split(';')) {
    const name = parseCookieName(entry);
    if (!name || seen.has(name)) continue;
    seen.add(name);

    // Never touch ConsentOS's own cookies.
    if (name.startsWith('_consentos_')) continue;

    const category = classifyCookie(name);
    // Unknown / unclassified cookies get left alone — we can't
    // attribute them so we can't safely delete them.
    if (!category || category === 'necessary') continue;
    if (acceptedCategories.has(category)) continue;

    // Expire the cookie. We don't know the domain / path the cookie
    // was set on, so we fire deletes for every plausible combination:
    // the current hostname bare, the leading-dot form, and every
    // parent domain walked up from the left. This catches the common
    // case of analytics cookies set on ``.example.com`` from a
    // subdomain page without over-deleting.
    const expired = 'expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    try {
      nativeSet(`${name}=; ${expired}`);
      for (const domain of domainVariants()) {
        nativeSet(`${name}=; ${expired}; domain=${domain}`);
      }
    } catch {
      // Writing a cookie can throw in exotic sandboxed contexts;
      // best-effort, don't crash the loader.
    }
  }
}

/** Derived list of plausible cookie domains for the current hostname. */
function domainVariants(): string[] {
  if (typeof location === 'undefined' || !location.hostname) return [];

  const hostname = location.hostname;
  // IP addresses and ``localhost`` have no "parent domain" concept.
  if (/^\d+\.\d+\.\d+\.\d+$/.test(hostname) || hostname === 'localhost') {
    return [hostname];
  }

  const parts = hostname.split('.');
  const variants: string[] = [];
  for (let i = 0; i < parts.length - 1; i++) {
    const parent = parts.slice(i).join('.');
    if (parent) {
      variants.push(parent, `.${parent}`);
    }
  }
  return Array.from(new Set(variants));
}

/** Delete classified localStorage / sessionStorage keys that aren't consented. */
function sweepDisallowedStorage(): void {
  if (typeof Storage === 'undefined') return;

  for (const storage of [safeStorage('local'), safeStorage('session')]) {
    if (!storage) continue;

    const toRemove: string[] = [];
    try {
      for (let i = 0; i < storage.length; i++) {
        const key = storage.key(i);
        if (!key || key.startsWith('_consentos_')) continue;
        const category = classifyStorageKey(key);
        if (!category || category === 'necessary') continue;
        if (acceptedCategories.has(category)) continue;
        toRemove.push(key);
      }
    } catch {
      continue;
    }

    for (const key of toRemove) {
      try {
        storage.removeItem(key);
      } catch {
        // Ignore quota / security errors — best-effort.
      }
    }
  }
}

/** Return the requested Storage instance, or null if inaccessible. */
function safeStorage(kind: 'local' | 'session'): Storage | null {
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage;
  } catch {
    // Access can throw on cross-origin / sandboxed iframes.
    return null;
  }
}

// ─── Teardown (for testing) ───

/** Remove all interception hooks. Used in tests. */
export function uninstallBlocker(): void {
  if (!installed) return;

  // Restore document.createElement
  if (originalCreateElement) {
    document.createElement = originalCreateElement;
  }

  // Restore document.cookie
  if (originalCookieDescriptor) {
    Object.defineProperty(document, 'cookie', originalCookieDescriptor);
  }

  // Restore storage
  if (originalLocalStorageSetItem) {
    Storage.prototype.setItem = originalLocalStorageSetItem;
  }

  // Clear state
  blockedScripts.length = 0;
  scriptPatterns.length = 0;
  initiatorMappings.length = 0;
  acceptedCategories = new Set(['necessary']);
  installed = false;
}
