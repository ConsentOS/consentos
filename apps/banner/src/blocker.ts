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

/** Native document.createElement, captured before page scripts can replace it. */
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

  originalCreateElement = document.createElement.bind(document);
  installScriptPropertyHooks();
  installInsertionHooks();
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

const XHTML_NS = 'http://www.w3.org/1999/xhtml';
const INERT_TYPES = new Set(['text/plain', 'text/blocked']);

let nativeSetAttribute: typeof Element.prototype.setAttribute;
let nativeSrcDescriptor: PropertyDescriptor | undefined;
let nativeTypeDescriptor: PropertyDescriptor | undefined;

/** Callbacks that put back every prototype patched by ``installBlocker``. */
const restorers: Array<() => void> = [];

function isScriptElement(node: unknown): node is HTMLScriptElement {
  const el = node as Element | null;
  return !!el && el.nodeType === 1 && el.localName === 'script' && el.namespaceURI === XHTML_NS;
}

/** Category the script should be held under, or null when it may run now. */
function categoryToBlock(script: HTMLScriptElement, src: string): CategorySlug | null {
  if (script.hasAttribute('data-consentos-allowed')) return null;
  const category = (script.getAttribute('data-category') as CategorySlug | null) || classifyScript(src, script);
  if (!category || category === 'necessary' || acceptedCategories.has(category)) return null;
  return category;
}

/** Make a script inert, keeping its original type for later activation. */
function neutraliseScript(script: HTMLScriptElement, category: CategorySlug): void {
  if (!script.hasAttribute('data-consentos-blocked')) {
    const type = script.getAttribute('type');
    if (type && !INERT_TYPES.has(type.trim().toLowerCase())) {
      nativeSetAttribute.call(script, 'data-consentos-original-type', type);
    }
    nativeSetAttribute.call(script, 'type', 'text/plain');
    nativeSetAttribute.call(script, 'data-consentos-blocked', 'true');
  }
  nativeSetAttribute.call(script, 'data-consentos-category', category);
}

/** Returns true when the assignment was captured instead of applied. */
function interceptSrc(script: HTMLScriptElement, value: string): boolean {
  const category = categoryToBlock(script, value);
  if (!category) return false;
  neutraliseScript(script, category);
  nativeSetAttribute.call(script, 'data-consentos-original-src', value);
  return true;
}

/** Returns true when a type change on a held script was captured. */
function interceptType(script: HTMLScriptElement, value: string): boolean {
  if (!script.hasAttribute('data-consentos-blocked')) return false;
  nativeSetAttribute.call(script, 'data-consentos-original-type', value);
  return true;
}

/**
 * Patch the script ``src`` / ``type`` setters and ``setAttribute`` on the
 * prototypes, so every script instance is covered however it was created.
 */
function installScriptPropertyHooks(): void {
  const proto = HTMLScriptElement.prototype;
  nativeSetAttribute = Element.prototype.setAttribute;
  nativeSrcDescriptor = Object.getOwnPropertyDescriptor(proto, 'src');
  nativeTypeDescriptor = Object.getOwnPropertyDescriptor(proto, 'type');
  const srcDesc = nativeSrcDescriptor;
  const typeDesc = nativeTypeDescriptor;

  if (srcDesc?.get && srcDesc.set) {
    Object.defineProperty(proto, 'src', {
      configurable: true,
      enumerable: srcDesc.enumerable,
      get(this: HTMLScriptElement) {
        const held = this.getAttribute('data-consentos-original-src');
        return held !== null && this.hasAttribute('data-consentos-blocked') ? held : srcDesc.get!.call(this);
      },
      set(this: HTMLScriptElement, value: string) {
        if (!interceptSrc(this, String(value))) srcDesc.set!.call(this, value);
      },
    });
    restorers.push(() => Object.defineProperty(proto, 'src', srcDesc));
  }

  if (typeDesc?.get && typeDesc.set) {
    Object.defineProperty(proto, 'type', {
      configurable: true,
      enumerable: typeDesc.enumerable,
      get: typeDesc.get,
      set(this: HTMLScriptElement, value: string) {
        if (!interceptType(this, String(value))) typeDesc.set!.call(this, value);
      },
    });
    restorers.push(() => Object.defineProperty(proto, 'type', typeDesc));
  }

  const originalSetAttribute = nativeSetAttribute;
  Element.prototype.setAttribute = function (this: Element, name: string, value: string): void {
    if (isScriptElement(this)) {
      const attr = String(name).toLowerCase();
      if (attr === 'src' && interceptSrc(this, String(value))) return;
      if (attr === 'type' && interceptType(this, String(value))) return;
    }
    originalSetAttribute.call(this, name, value);
  };
  restorers.push(() => {
    Element.prototype.setAttribute = originalSetAttribute;
  });
}

/**
 * Inspect a node about to be inserted. Non-script nodes without element
 * children return straight away, so ordinary DOM work stays cheap.
 */
function inspectBeforeInsertion(node: unknown): void {
  if (!node || typeof node !== 'object') return;
  const n = node as Node;
  if (isScriptElement(n)) {
    holdScript(n, false);
    return;
  }
  if ((n.nodeType !== 1 && n.nodeType !== 11) || !(n as ParentNode).firstElementChild) return;
  const scripts = (n as ParentNode).querySelectorAll('script');
  for (let i = 0; i < scripts.length; i++) {
    holdScript(scripts[i], false);
  }
}

/** Wrap a DOM insertion method so its node arguments are inspected first. */
function hookInsertion(proto: object, name: string, firstArgOnly: boolean): void {
  const target = proto as Record<string, unknown>;
  const original = target[name];
  if (typeof original !== 'function') return;
  target[name] = function (this: unknown, ...args: unknown[]) {
    if (firstArgOnly) {
      inspectBeforeInsertion(args[0]);
    } else {
      for (const arg of args) inspectBeforeInsertion(arg);
    }
    return (original as (...a: unknown[]) => unknown).apply(this, args);
  };
  restorers.push(() => {
    target[name] = original;
  });
}

/** Intercept dynamically inserted scripts before they reach the document. */
function installInsertionHooks(): void {
  hookInsertion(Node.prototype, 'appendChild', true);
  hookInsertion(Node.prototype, 'insertBefore', true);
  hookInsertion(Node.prototype, 'replaceChild', true);
  for (const name of ['append', 'prepend', 'before', 'after', 'replaceWith', 'replaceChildren']) {
    hookInsertion(Element.prototype, name, false);
  }
  hookInsertion(Element.prototype, 'insertAdjacentElement', false);
  for (const proto of [DocumentFragment.prototype, Document.prototype]) {
    for (const name of ['append', 'prepend', 'replaceChildren']) {
      hookInsertion(proto, name, false);
    }
  }
}

/**
 * MutationObserver catches scripts added by the HTML parser, including
 * those nested inside added elements.
 */
function installMutationObserver(): void {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (isScriptElement(node)) {
          holdScript(node, true);
        } else if (node.nodeType === 1 && (node as Element).firstElementChild) {
          const scripts = (node as Element).querySelectorAll('script');
          for (let i = 0; i < scripts.length; i++) {
            holdScript(scripts[i], true);
          }
        }
      }
    }
  });

  if (document.documentElement) {
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }
  restorers.push(() => observer.disconnect());
}

/**
 * Queue a script whose category lacks consent. ``connected`` is true when
 * the script is already in the document (observer path), in which case it
 * is also removed. Scripts tagged ``type="text/plain" data-category`` whose
 * category is ``necessary`` or already accepted are activated instead.
 */
function holdScript(script: HTMLScriptElement, connected: boolean): void {
  if (script.hasAttribute('data-consentos-allowed')) return;

  if (script.hasAttribute('data-consentos-queued')) {
    if (connected) script.parentNode?.removeChild(script);
    return;
  }

  const explicitCategory = script.getAttribute('data-category') as CategorySlug | null;
  const src = script.getAttribute('data-consentos-original-src') || script.getAttribute('src') || '';
  const category = explicitCategory || classifyScript(src, script);

  if (!category) return;

  if (category === 'necessary' || acceptedCategories.has(category)) {
    const tagged = explicitCategory || script.hasAttribute('data-consentos-blocked');
    if (connected && tagged && isInert(script)) activateInPlace(script);
    return;
  }

  neutraliseScript(script, category);
  nativeSetAttribute.call(script, 'data-consentos-queued', 'true');
  blockedScripts.push({ element: script, category });

  if (connected) script.parentNode?.removeChild(script);
}

function isInert(script: HTMLScriptElement): boolean {
  const type = script.getAttribute('type');
  return !!type && INERT_TYPES.has(type.trim().toLowerCase());
}

/** Swap an inert, consented script for a live copy at the same position. */
function activateInPlace(script: HTMLScriptElement): void {
  const live = createActiveScript(script);
  nativeSetAttribute.call(script, 'data-consentos-allowed', 'true');
  const parent = script.parentNode;
  if (parent) {
    parent.replaceChild(live, script);
  } else {
    (document.head || document.documentElement).appendChild(live);
  }
}

/**
 * Build a fresh, executable copy of a held script. A new element is needed
 * because browsers will not run a script element that was already prepared.
 */
function createActiveScript(source: HTMLScriptElement): HTMLScriptElement {
  const script = originalCreateElement('script') as HTMLScriptElement;
  // Set first so the hooks above let the copy through untouched.
  nativeSetAttribute.call(script, 'data-consentos-allowed', 'true');

  for (const attr of Array.from(source.attributes)) {
    if (attr.name === 'type' || attr.name === 'src' || attr.name.startsWith('data-consentos-')) continue;
    nativeSetAttribute.call(script, attr.name, attr.value);
  }

  const originalType = source.getAttribute('data-consentos-original-type');
  if (originalType) nativeSetAttribute.call(script, 'type', originalType);

  const src = source.getAttribute('data-consentos-original-src') || source.getAttribute('src');
  if (src) {
    nativeSetAttribute.call(script, 'src', src);
  } else if (source.textContent) {
    script.textContent = source.textContent;
  }
  return script;
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

  for (const { element } of toRelease) {
    (document.head || document.documentElement).appendChild(createActiveScript(element));
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

  while (restorers.length) restorers.pop()!();

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
