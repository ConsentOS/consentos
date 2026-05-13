/**
 * Helpers for branching banner behaviour on the resolved
 * ``blocking_mode``.
 *
 *  - ``opt_in`` (GDPR): explicit consent required, banner shown,
 *    GCM defaults to denied, blocker stays active until acceptance.
 *  - ``opt_out`` (CCPA): tracking on by default, opt-out via the
 *    preferences page / footer link. GCM defaults to granted.
 *  - ``informational``: tracking on by default, notice-only. GCM
 *    defaults to granted.
 */

export type BlockingMode = 'opt_in' | 'opt_out' | 'informational';

/**
 * Return true when the resolved mode allows tracking by default and
 * treats banner dismissal as implicit acceptance. Unknown values
 * return false so the safe (opt-in) path wins.
 */
export function isImplicitConsentMode(
  blockingMode: string | null | undefined,
): boolean {
  return blockingMode === 'opt_out' || blockingMode === 'informational';
}
