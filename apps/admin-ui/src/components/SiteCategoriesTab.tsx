import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';

import { updateSiteConfig } from '../api/sites';
import { trackConfigChange } from '../services/analytics';
import type { CategorySlug, SiteConfig } from '../types/api';
import { ALL_COOKIE_CATEGORIES } from '../types/api';
import { Alert } from './ui/alert';
import { Button } from './ui/button';
import { Card } from './ui/card';

interface Props {
  siteId: string;
  config: SiteConfig | null;
}

/**
 * Per-site control over which cookie categories the banner displays.
 *
 * ``necessary`` is always on and can't be disabled. A category that's
 * unchecked here is hidden from the banner AND treated as permanently
 * unconsented, so any cookie in that category stays blocked. That's
 * the correct semantics for a site that genuinely doesn't use e.g.
 * marketing cookies: the operator declares it, the visitor never
 * sees the toggle, and the auto-blocker enforces it.
 *
 * ``null`` on the site config means "inherit from the cascade"
 * (group → org → system default of all five). The save button
 * always writes an explicit list; the "Reset to inherited" button
 * clears the override by sending ``null``.
 */
export default function SiteCategoriesTab({ siteId, config }: Props) {
  const queryClient = useQueryClient();

  const initiallyEnabled = useMemo<Set<CategorySlug>>(() => {
    const raw = config?.enabled_categories;
    if (!raw || raw.length === 0) {
      return new Set(ALL_COOKIE_CATEGORIES.map((c) => c.slug));
    }
    const known = new Set<CategorySlug>(ALL_COOKIE_CATEGORIES.map((c) => c.slug));
    const picked = new Set<CategorySlug>(raw.filter((s): s is CategorySlug => known.has(s)));
    picked.add('necessary');
    return picked;
  }, [config?.enabled_categories]);

  const [enabled, setEnabled] = useState<Set<CategorySlug>>(initiallyEnabled);
  const [saved, setSaved] = useState(false);

  const isInherited = config?.enabled_categories == null;

  const mutation = useMutation({
    mutationFn: (body: Partial<SiteConfig>) => updateSiteConfig(siteId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'config'] });
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'inheritance'] });
      trackConfigChange('site_categories', { site_id: siteId });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const toggle = (slug: CategorySlug, locked: boolean) => {
    if (locked) return;
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) {
        next.delete(slug);
      } else {
        next.add(slug);
      }
      next.add('necessary');
      return next;
    });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const payload = ALL_COOKIE_CATEGORIES.map((c) => c.slug).filter((slug) => enabled.has(slug));
    mutation.mutate({ enabled_categories: payload });
  };

  const handleResetToInherited = () => {
    mutation.mutate({ enabled_categories: null });
  };

  const allActive = ALL_COOKIE_CATEGORIES.every((c) => enabled.has(c.slug));
  const dirty =
    !isInherited &&
    (config?.enabled_categories ?? []).slice().sort().join(',') !==
      Array.from(enabled).sort().join(',');

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="rounded-xl border border-dashed border-border bg-surface p-4">
        <p className="text-xs text-text-secondary">
          <strong>Cookie categories.</strong> Untick any category this site doesn&rsquo;t use — it
          will be hidden from the banner and permanently unconsented, so any cookie that falls
          into it stays blocked. <em>Necessary</em> is always on and can&rsquo;t be disabled.
          {isInherited && (
            <> This site is currently <strong>inheriting</strong> its category list from the
            cascade (group &rarr; organisation &rarr; system default).</>
          )}
        </p>
      </div>

      <Card className="p-6">
        <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">
          Categories shown in the banner
        </h3>

        <div className="space-y-3">
          {ALL_COOKIE_CATEGORIES.map((cat) => {
            const active = enabled.has(cat.slug);
            return (
              <label
                key={cat.slug}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors ${
                  active
                    ? 'border-copper bg-copper/5'
                    : 'border-border bg-transparent hover:bg-surface'
                } ${cat.locked ? 'cursor-not-allowed opacity-80' : ''}`}
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={active}
                  disabled={cat.locked}
                  onChange={() => toggle(cat.slug, cat.locked)}
                  aria-labelledby={`cat-${cat.slug}-label`}
                  aria-describedby={`cat-${cat.slug}-desc`}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      id={`cat-${cat.slug}-label`}
                      className="font-heading text-sm font-medium text-foreground"
                    >
                      {cat.label}
                    </span>
                    {cat.locked && (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">
                        Always on
                      </span>
                    )}
                  </div>
                  <p id={`cat-${cat.slug}-desc`} className="mt-1 text-xs text-text-secondary">
                    {cat.description}
                  </p>
                </div>
              </label>
            );
          })}
        </div>
      </Card>

      {saved && <Alert variant="success">Categories saved.</Alert>}
      {mutation.isError && (
        <Alert variant="error">
          Couldn&rsquo;t save: {(mutation.error as Error)?.message ?? 'unknown error'}
        </Alert>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={mutation.isPending || (!dirty && !isInherited)}>
          {mutation.isPending ? 'Saving…' : 'Save categories'}
        </Button>
        {!isInherited && (
          <Button
            type="button"
            variant="secondary"
            onClick={handleResetToInherited}
            disabled={mutation.isPending}
          >
            Reset to inherited
          </Button>
        )}
        {allActive && !isInherited && (
          <span className="text-xs text-text-secondary">
            All five categories enabled — same as the system default.
          </span>
        )}
      </div>
    </form>
  );
}
