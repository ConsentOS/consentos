import { useState } from 'react';

import { Select } from './ui/select';

const COMMON_REGIONS: { code: string; label: string }[] = [
  { code: 'DEFAULT', label: 'Default (fallback for unmatched regions)' },
  { code: 'EU', label: 'EU/EEA bloc' },
  { code: 'GB', label: 'United Kingdom' },
  { code: 'US-CA', label: 'California, US (CCPA/CPRA)' },
  { code: 'US-CO', label: 'Colorado, US (CPA)' },
  { code: 'US-CT', label: 'Connecticut, US (CTDPA)' },
  { code: 'US-VA', label: 'Virginia, US (VCDPA)' },
  { code: 'US-TX', label: 'Texas, US (TDPSA)' },
  { code: 'BR', label: 'Brazil (LGPD)' },
  { code: 'CH', label: 'Switzerland (revFADP)' },
];

const MODES: { value: string; label: string }[] = [
  { value: 'opt_in', label: 'Opt-in (GDPR)' },
  { value: 'opt_out', label: 'Opt-out (CCPA)' },
  { value: 'informational', label: 'Informational only' },
];

interface Row {
  id: string;
  code: string;
  mode: string;
}

interface Props {
  value: Record<string, string> | null;
  onChange: (next: Record<string, string> | null) => void;
}

function makeId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function rowsToValue(rows: Row[]): Record<string, string> | null {
  const valid = rows.filter((r) => r.code.trim());
  if (valid.length === 0) return null;
  return Object.fromEntries(valid.map((r) => [r.code.trim(), r.mode]));
}

/**
 * Edit a site's regional_modes cascade as a list of region/mode rows.
 * Emits null when no rows have a code set, so the config falls back to
 * the inherited blocking mode rather than persisting an empty object.
 */
export default function RegionalModesEditor({ value, onChange }: Props) {
  const [rows, setRows] = useState<Row[]>(() =>
    Object.entries(value ?? {}).map(([code, mode]) => ({
      id: makeId(),
      code,
      mode,
    })),
  );

  function emit(next: Row[]) {
    setRows(next);
    onChange(rowsToValue(next));
  }

  function updateRow(id: string, patch: Partial<Row>) {
    emit(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  function addRow() {
    emit([...rows, { id: makeId(), code: '', mode: 'opt_in' }]);
  }

  function removeRow(id: string) {
    emit(rows.filter((r) => r.id !== id));
  }

  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const r of rows) {
    const code = r.code.trim();
    if (!code) continue;
    if (seen.has(code)) duplicates.add(code);
    seen.add(code);
  }

  return (
    <div className="space-y-3">
      <datalist id="regional-modes-suggestions">
        {COMMON_REGIONS.map((r) => (
          <option key={r.code} value={r.code}>
            {r.label}
          </option>
        ))}
      </datalist>

      {rows.length === 0 && (
        <p className="text-sm text-text-secondary">
          No regional overrides. Visitors everywhere see the site-level
          blocking mode. Add a row to set a different mode for a country,
          a US state, or the EU bloc.
        </p>
      )}

      {rows.map((row) => {
        const isDuplicate = duplicates.has(row.code.trim());
        return (
          <div
            key={row.id}
            className="flex flex-col gap-2 sm:flex-row sm:items-center"
          >
            <input
              type="text"
              list="regional-modes-suggestions"
              value={row.code}
              onChange={(e) => updateRow(row.id, { code: e.target.value })}
              placeholder="DEFAULT, EU, GB, US-CA..."
              aria-label="Region code"
              className={`block w-full rounded-md border bg-background px-3 py-2 text-sm focus:border-copper focus:outline-none sm:w-56 ${
                isDuplicate ? 'border-status-error-fg' : 'border-border'
              }`}
            />
            <Select
              value={row.mode}
              onChange={(e) => updateRow(row.id, { mode: e.target.value })}
              aria-label="Blocking mode"
              className="sm:w-64"
            >
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
            <button
              type="button"
              onClick={() => removeRow(row.id)}
              aria-label={`Remove ${row.code || 'row'}`}
              className="rounded-md border border-border px-3 py-2 text-sm text-text-secondary hover:border-status-error-fg hover:text-status-error-fg"
            >
              Remove
            </button>
          </div>
        );
      })}

      {duplicates.size > 0 && (
        <p className="text-xs text-status-error-fg">
          Duplicate region code{duplicates.size > 1 ? 's' : ''}:{' '}
          {[...duplicates].join(', ')}. Only the last value is saved.
        </p>
      )}

      <button
        type="button"
        onClick={addRow}
        className="rounded-md border border-dashed border-border px-3 py-2 text-sm text-text-secondary hover:border-copper hover:text-copper"
      >
        + Add region
      </button>
    </div>
  );
}
