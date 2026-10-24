import type { ScanJob } from '../types/api';

interface Props {
  scan: ScanJob;
}

/** Progress of a pending or running scan. */
export default function ScanProgress({ scan }: Props) {
  const total = scan.status === 'running' && scan.pages_scanned > 0 ? scan.pages_total : null;
  const percent = total ? Math.min(100, Math.round((scan.pages_scanned / total) * 100)) : null;

  let detail: string;
  if (scan.status === 'pending') {
    detail = 'Waiting for the scanner to start…';
  } else if (total) {
    detail = `${scan.pages_scanned} of ${total} pages scanned, ${scan.cookies_found} ${
      scan.cookies_found === 1 ? 'cookie' : 'cookies'
    } found so far`;
  } else {
    detail = 'Finding pages to scan…';
  }

  return (
    <div role="status" aria-live="polite">
      <p className="text-sm text-foreground">{detail}</p>
      <div
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-mist"
        role="progressbar"
        aria-label="Scan progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
      >
        <div
          className={`h-full rounded-full bg-copper ${percent === null ? 'w-1/3 animate-pulse' : ''}`}
          style={percent === null ? undefined : { width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
