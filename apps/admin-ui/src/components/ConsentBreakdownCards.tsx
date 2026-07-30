import { CONSENT_COLOURS } from '../lib/consent';
import type { ActionBreakdown } from '../types/api';

function pct(value: number, total: number): string {
  if (total === 0) return '0%';
  return `${Math.round((value / total) * 100)}%`;
}

/** Headline "bento" card for a single decision bucket. */
function StatCard({
  label,
  count,
  share,
  colour,
}: {
  label: string;
  count: number;
  share: string;
  colour: string;
}) {
  return (
    <div className="group rounded-xl border border-border bg-card p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colour }} />
        <span className="text-sm font-medium text-text-secondary">{label}</span>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="font-heading text-3xl font-semibold tracking-tight text-foreground">
          {count.toLocaleString()}
        </span>
        <span className="text-sm font-semibold" style={{ color: colour }}>
          {share}
        </span>
      </div>
      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-mist">
        <div className="h-full rounded-full" style={{ width: share, backgroundColor: colour }} />
      </div>
    </div>
  );
}

interface Props {
  breakdown: ActionBreakdown;
  /** Sublabel shown on the Total card, e.g. "Last 30 days". */
  rangeLabel: string;
}

/** Accept / partial / decline "bento" grid — shared by Overview and Dashboard. */
export default function ConsentBreakdownCards({ breakdown, rangeLabel }: Props) {
  // Decisions exclude withdrawals — a withdrawal is not an accept/decline choice.
  const decisions = breakdown.accept_all + breakdown.custom + breakdown.reject_all;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="flex flex-col justify-between rounded-xl border border-border bg-gradient-to-br from-card to-mist p-5 shadow-sm">
        <span className="text-sm font-medium text-text-secondary">Total decisions</span>
        <div>
          <div className="font-heading mt-3 text-3xl font-semibold tracking-tight text-foreground">
            {decisions.toLocaleString()}
          </div>
          <div className="mt-1 text-xs text-text-tertiary">{rangeLabel}</div>
        </div>
      </div>
      <StatCard
        label="Accept"
        count={breakdown.accept_all}
        share={pct(breakdown.accept_all, decisions)}
        colour={CONSENT_COLOURS.accept}
      />
      <StatCard
        label="Partial"
        count={breakdown.custom}
        share={pct(breakdown.custom, decisions)}
        colour={CONSENT_COLOURS.partial}
      />
      <StatCard
        label="Decline"
        count={breakdown.reject_all}
        share={pct(breakdown.reject_all, decisions)}
        colour={CONSENT_COLOURS.decline}
      />
    </div>
  );
}
