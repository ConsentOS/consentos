import type { ReconsentReason } from '../types/api';

const REASON_LABELS: Record<ReconsentReason, string> = {
  categories: 'cookie categories',
  purposes: 'TCF purposes',
  vendors: 'disclosed vendors',
};

/** "cookie categories and disclosed vendors" for the given reasons. */
export function describeReconsentReasons(reasons: ReconsentReason[]): string {
  const labels = reasons.map((reason) => REASON_LABELS[reason]);
  if (labels.length <= 1) return labels.join('');
  return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`;
}
