/**
 * Multi-select vendor picker backed by the locally-cached IAB GVL.
 *
 * Operators set ``site_config.disclosed_vendor_ids`` here. The
 * resulting list is what the banner emits in the TCF v2.3
 * DisclosedVendors segment, so it directly drives compliance
 * substance — empty list → empty segment → spec-valid but
 * operationally meaningless. Without this picker, the field can
 * only be hand-edited as JSONB.
 *
 * Strategy: type-ahead search with debounced server-side filtering
 * (1,000+ vendors makes client-side filtering wasteful), with the
 * already-selected IDs rendered as removable badges below.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { listVendors } from '../api/iab-gvl';
import { Badge } from './ui/badge';
import { Input } from './ui/input';

interface Props {
  value: number[];
  onChange: (ids: number[]) => void;
  /** Cap on the number of results shown per search; 50 is plenty for picking. */
  pageSize?: number;
  /** Optional disabled state — used when TCF is off so the picker is greyed out. */
  disabled?: boolean;
}

/** Debounce a value by ``ms`` milliseconds. Trailing-edge only. */
function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(handle);
  }, [value, ms]);
  return debounced;
}

export default function IabVendorPicker({ value, onChange, pageSize = 50, disabled }: Props) {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounced(query.trim(), 200);
  const selected = useMemo(() => new Set(value), [value]);

  const searchQuery = useQuery({
    queryKey: ['iab', 'vendors', debouncedQuery, pageSize],
    queryFn: () =>
      listVendors({
        q: debouncedQuery || undefined,
        limit: pageSize,
      }),
    enabled: !disabled,
    staleTime: 60_000,
  });

  // We need names for already-selected vendor IDs that aren't in the
  // current search results. Fetch them lazily — the selection list
  // can be huge, so we fetch in chunks and cache by ID.
  const selectedDetails = useSelectedVendorDetails(value, disabled);

  const toggle = (id: number) => {
    if (disabled) return;
    if (selected.has(id)) {
      onChange(value.filter((v) => v !== id));
    } else {
      onChange([...value, id]);
    }
  };

  const clearAll = () => {
    if (!disabled) onChange([]);
  };

  return (
    <div className="space-y-3">
      <div>
        <Input
          type="search"
          placeholder="Search vendors by name..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
          aria-label="Search IAB vendors"
        />
      </div>

      {/* Search results */}
      {searchQuery.isLoading && (
        <p className="text-xs text-text-secondary">Loading vendors…</p>
      )}
      {searchQuery.isError && (
        <p className="text-xs text-error">
          Failed to load vendors. The GVL may not be synced yet.
        </p>
      )}
      {searchQuery.data && (
        <div className="max-h-60 overflow-y-auto rounded-lg border border-border bg-surface">
          {searchQuery.data.items.length === 0 ? (
            <p className="p-3 text-xs text-text-secondary">
              {debouncedQuery
                ? `No vendors match "${debouncedQuery}".`
                : 'No vendors available.'}
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {searchQuery.data.items.map((vendor) => (
                <li key={vendor.id}>
                  <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-background">
                    <input
                      type="checkbox"
                      checked={selected.has(vendor.id)}
                      onChange={() => toggle(vendor.id)}
                      disabled={disabled}
                      className="h-4 w-4 rounded border-border text-primary"
                    />
                    <span className="font-mono text-xs text-text-secondary">#{vendor.id}</span>
                    <span className="flex-1 text-sm">{vendor.name}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {searchQuery.data.total > searchQuery.data.items.length && (
            <p className="border-t border-border px-3 py-2 text-xs text-text-secondary">
              Showing {searchQuery.data.items.length} of {searchQuery.data.total} matches —
              refine the search to narrow.
            </p>
          )}
        </div>
      )}

      {/* Selected pills */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-text-secondary">
            Disclosed vendors ({value.length})
          </span>
          {value.length > 0 && !disabled && (
            <button
              type="button"
              onClick={clearAll}
              className="text-xs text-text-secondary hover:text-error"
            >
              Clear all
            </button>
          )}
        </div>
        {value.length === 0 ? (
          <p className="text-xs text-text-secondary">
            No vendors selected. The TCF v2.3 DisclosedVendors segment will be empty.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {value.map((id) => {
              const name = selectedDetails.get(id);
              return (
                <Badge key={id} variant="neutral" className="gap-1">
                  <span className="font-mono">#{id}</span>
                  {name && <span>{name}</span>}
                  {!disabled && (
                    <button
                      type="button"
                      onClick={() => toggle(id)}
                      aria-label={`Remove vendor ${id}`}
                      className="ml-1 text-text-secondary hover:text-error"
                    >
                      ×
                    </button>
                  )}
                </Badge>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Resolve names for already-selected vendor IDs.
 *
 * The search result only carries vendors matching the current query;
 * selections from prior queries (or saved configs) need their names
 * fetched separately. We hit ``listVendors`` with no filter and walk
 * pages until we've covered every selected ID — typically two pages
 * at the default ``limit=500`` is enough to cover the whole GVL.
 *
 * Falls back to ``undefined`` for any ID that isn't in the GVL
 * (e.g. operator typed in a vendor that's been deleted upstream);
 * the picker still shows the badge with just the ID.
 */
function useSelectedVendorDetails(ids: number[], disabled?: boolean): Map<number, string> {
  const idsKey = useMemo(() => [...ids].sort((a, b) => a - b).join(','), [ids]);
  const cacheRef = useRef<Map<number, string>>(new Map());

  const query = useQuery({
    queryKey: ['iab', 'vendors', 'name-cache', idsKey],
    queryFn: async () => {
      const missing = ids.filter((id) => !cacheRef.current.has(id));
      if (missing.length === 0) return cacheRef.current;

      // Walk pages of the full vendor list until every missing ID is
      // resolved or we've exhausted the catalogue.
      let offset = 0;
      const limit = 500;
      while (missing.some((id) => !cacheRef.current.has(id))) {
        const page = await listVendors({ limit, offset, include_deleted: true });
        for (const v of page.items) cacheRef.current.set(v.id, v.name);
        if (offset + page.items.length >= page.total) break;
        offset += page.items.length;
      }
      return cacheRef.current;
    },
    enabled: !disabled && ids.length > 0,
    staleTime: 5 * 60_000,
  });

  return query.data ?? cacheRef.current;
}
