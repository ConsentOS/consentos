import type { CategorySlug, ConsentState } from './types';

const COOKIE_NAME = '_consentos_consent';
/**
 * IAB-standard TCF v2 consent cookie name. Vendors that participate
 * in the Transparency & Consent Framework read this cookie directly
 * (in addition to the ``__tcfapi`` postMessage path) so we mirror
 * the encoded TC string into it whenever TCF is enabled on the site.
 */
const TCF_COOKIE_NAME = 'euconsent-v2';
const BANNER_VERSION = '0.1.0';

/** Generate a simple visitor ID (UUID v4-like). */
export function generateVisitorId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** Read the consent cookie and parse the stored state. */
export function readConsent(): ConsentState | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${COOKIE_NAME}=`));
  if (!match) return null;

  try {
    const value = decodeURIComponent(match.split('=')[1]);
    return JSON.parse(value) as ConsentState;
  } catch {
    return null;
  }
}

/** Write consent state to a first-party cookie. */
export function writeConsent(
  state: ConsentState,
  expiryDays: number = 365
): void {
  if (typeof document === 'undefined') return;
  const value = encodeURIComponent(JSON.stringify(state));
  const expires = new Date(Date.now() + expiryDays * 86400000).toUTCString();
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${COOKIE_NAME}=${value}; path=/; expires=${expires}; SameSite=Lax${secure}`;
}

/** Build a ConsentState for a given action. */
export function buildConsentState(
  accepted: CategorySlug[],
  rejected: CategorySlug[],
  existingVisitorId?: string,
  tcString?: string,
  gcmState?: Record<string, 'granted' | 'denied'>,
  configVersion?: string,
  gppString?: string,
  gpcDetected?: boolean,
  gpcHonoured?: boolean,
): ConsentState {
  return {
    visitorId: existingVisitorId ?? generateVisitorId(),
    accepted,
    rejected,
    consentedAt: new Date().toISOString(),
    bannerVersion: BANNER_VERSION,
    tcString,
    gppString,
    gcmState,
    configVersion,
    gpcDetected,
    gpcHonoured,
  };
}

/** Clear the consent cookie. */
export function clearConsent(): void {
  if (typeof document === 'undefined') return;
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax${secure}`;
  document.cookie = `${TCF_COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax${secure}`;
}

/**
 * Write the TCF v2 ``euconsent-v2`` cookie containing the encoded
 * TC string. Vendors that participate in TCF read this directly.
 * No-op when ``tcString`` is empty.
 */
export function writeTcfCookie(tcString: string, expiryDays: number = 365): void {
  if (typeof document === 'undefined' || !tcString) return;
  const expires = new Date(Date.now() + expiryDays * 86400000).toUTCString();
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${TCF_COOKIE_NAME}=${tcString}; path=/; expires=${expires}; SameSite=Lax${secure}`;
}

/** Check whether consent has been given (any state exists). */
export function hasConsent(): boolean {
  return readConsent() !== null;
}

/** Check whether a specific category has been accepted. */
export function isCategoryAccepted(category: CategorySlug): boolean {
  const state = readConsent();
  if (!state) return category === 'necessary'; // Necessary always allowed
  return state.accepted.includes(category);
}
