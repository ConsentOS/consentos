/**
 * Global Privacy Control (GPC) signal detection and jurisdiction-aware
 * auto-opt-out.
 *
 * GPC is a browser-level signal (`navigator.globalPrivacyControl === true`)
 * that communicates a user's intent to opt out of the sale/sharing of their
 * personal data. Several US state laws legally require businesses to honour
 * this signal: California (CCPA/CPRA), Colorado (CPA), Connecticut (CTDPA),
 * Texas (TDPSA), and Montana (MTCDPA).
 *
 * @see https://globalprivacycontrol.github.io/gpc-spec/
 */

import type { CategorySlug } from './types';

// ── Types ────────────────────────────────────────────────────────────

declare global {
  interface Navigator {
    globalPrivacyControl?: boolean;
  }
}

/** Result of GPC detection and evaluation. */
export interface GpcResult {
  /** Whether the browser is sending the GPC signal. */
  detected: boolean;
  /** Whether GPC was honoured (auto-opt-out applied). */
  honoured: boolean;
  /** The visitor's detected region code (e.g. 'US-CA'), if available. */
  region: string | null;
}

/** GPC-related site configuration fields. */
export interface GpcConfig {
  /** Whether to detect GPC at all. */
  gpc_enabled: boolean;
  /** Region codes where GPC is legally required. */
  gpc_jurisdictions: string[];
  /** If true, honour GPC regardless of jurisdiction. */
  gpc_global_honour: boolean;
}

/** Default jurisdictions where GPC must be legally honoured. */
export const DEFAULT_GPC_JURISDICTIONS: string[] = [
  'US-CA', // California — CCPA/CPRA
  'US-CO', // Colorado — CPA
  'US-CT', // Connecticut — CTDPA
  'US-TX', // Texas — TDPSA
  'US-MT', // Montana — MTCDPA
];

// ── Detection ────────────────────────────────────────────────────────

/** Check whether the browser is sending the GPC signal. */
export function isGpcEnabled(): boolean {
  if (typeof navigator === 'undefined') return false;
  return navigator.globalPrivacyControl === true;
}

// ── Region detection ─────────────────────────────────────────────────

/**
 * Read a visitor region set on the page's ConsentOS context.
 *
 * A fallback for when the API resolved no region: an integrator can set
 * ``window.__consentos.visitorRegion`` before the banner runs.
 */
export function getVisitorRegion(): string | null {
  if (typeof window === 'undefined') return null;
  return (window as { __consentos?: { visitorRegion?: string } }).__consentos?.visitorRegion ?? null;
}

// ── Jurisdiction check ───────────────────────────────────────────────

/**
 * Determine whether GPC should be honoured for the given region.
 *
 * @param region The visitor's region code (e.g. 'US-CA').
 * @param config GPC configuration from the site config.
 * @returns true if GPC should be honoured.
 */
export function shouldHonourGpc(
  region: string | null,
  config: GpcConfig,
): boolean {
  if (!config.gpc_enabled) return false;

  // Global honour overrides jurisdiction check
  if (config.gpc_global_honour) return true;

  if (!region) return false;

  const jurisdictions = config.gpc_jurisdictions.length > 0
    ? config.gpc_jurisdictions
    : DEFAULT_GPC_JURISDICTIONS;

  return jurisdictions.includes(region);
}

// ── Auto-opt-out categories ──────────────────────────────────────────

/**
 * Categories that should be rejected when GPC is honoured.
 * GPC specifically relates to sale/sharing/targeted advertising,
 * which maps to the 'marketing' and 'personalisation' categories.
 * Analytics may also be affected depending on interpretation.
 */
export const GPC_OPTOUT_CATEGORIES: CategorySlug[] = [
  'marketing',
  'personalisation',
];

/**
 * Categories that remain accepted when GPC auto-opt-out is applied.
 * 'necessary' is always accepted; 'functional' and 'analytics' are
 * not directly related to sale/sharing.
 */
export const GPC_ACCEPTED_CATEGORIES: CategorySlug[] = [
  'necessary',
  'functional',
  'analytics',
];

// ── Full evaluation ──────────────────────────────────────────────────

/**
 * Evaluate GPC signal and determine whether to apply auto-opt-out.
 *
 * @param config GPC configuration from the site config.
 * @param region The visitor's region code, or null if unknown.
 * @returns GpcResult with detection and honouring status.
 */
export function evaluateGpc(
  config: GpcConfig,
  region: string | null = null,
): GpcResult {
  const detected = isGpcEnabled();

  if (!detected || !config.gpc_enabled) {
    return { detected, honoured: false, region };
  }

  const honoured = shouldHonourGpc(region, config);

  return { detected, honoured, region };
}
