import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { getCookieSummary, listCategories, listCookies, updateCookie } from '../api/cookies';
import type { Cookie, CookieCategory } from '../types/api';
import AddCookieModal from './AddCookieModal';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { EmptyState } from './ui/empty-state';
import { LoadingState } from './ui/loading-state';
import { MetricCard } from './ui/metric-card';
import { Select } from './ui/select';

interface Props {
  siteId: string;
}

export default function SiteCookiesTab({ siteId }: Props) {
  const queryClient = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);

  const { data: cookies, isLoading } = useQuery({
    queryKey: ['cookies', siteId],
    queryFn: () => listCookies(siteId),
  });

  const { data: categories } = useQuery({
    queryKey: ['cookie-categories'],
    queryFn: listCategories,
  });

  const { data: summary } = useQuery({
    queryKey: ['cookies', siteId, 'summary'],
    queryFn: () => getCookieSummary(siteId),
  });

  const updateMutation = useMutation({
    mutationFn: ({ cookieId, body }: { cookieId: string; body: Partial<Cookie> }) =>
      updateCookie(siteId, cookieId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cookies', siteId] });
      queryClient.invalidateQueries({ queryKey: ['cookies', siteId, 'summary'] });
    },
  });

  if (isLoading) {
    return <LoadingState message="Loading cookies..." />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg font-semibold text-foreground">Cookies</h2>
        <Button onClick={() => setShowAddModal(true)}>Add cookie</Button>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricCard label="Total" value={summary.total} />
          <MetricCard label="Pending review" value={summary.by_status?.pending ?? 0} />
          <MetricCard label="Approved" value={summary.by_status?.approved ?? 0} />
          <MetricCard label="Uncategorised" value={summary.uncategorised} />
        </div>
      )}

      {/* Cookies table */}
      {cookies && cookies.length > 0 ? (
        <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-background text-left text-xs font-medium uppercase tracking-wide text-text-secondary">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Domain</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {cookies.map((cookie: Cookie) => (
                <tr key={cookie.id} className="transition hover:bg-mist">
                  <td className="px-4 py-3 text-sm font-mono text-foreground">{cookie.name}</td>
                  <td className="px-4 py-3 text-sm text-text-secondary">{cookie.domain}</td>
                  <td className="px-4 py-3">
                    <Select
                      value={cookie.category_id ?? ''}
                      onChange={(e) =>
                        updateMutation.mutate({
                          cookieId: cookie.id,
                          body: { category_id: e.target.value || null },
                        })
                      }
                      className="h-auto w-auto px-2 py-1 text-xs"
                    >
                      <option value="">Uncategorised</option>
                      {(categories ?? []).map((cat: CookieCategory) => (
                        <option key={cat.id} value={cat.id}>
                          {cat.name}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      variant={
                        cookie.review_status === 'approved'
                          ? 'success'
                          : cookie.review_status === 'rejected'
                            ? 'error'
                            : cookie.review_status === 'pending'
                              ? 'warning'
                              : 'neutral'
                      }
                    >
                      {cookie.review_status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {cookie.review_status !== 'approved' && (
                        <button
                          onClick={() =>
                            updateMutation.mutate({
                              cookieId: cookie.id,
                              body: { review_status: 'approved' },
                            })
                          }
                          className="rounded bg-status-success-bg px-2 py-1 text-xs font-medium text-status-success-fg hover:opacity-80"
                        >
                          Approve
                        </button>
                      )}
                      {cookie.review_status !== 'rejected' && (
                        <button
                          onClick={() =>
                            updateMutation.mutate({
                              cookieId: cookie.id,
                              body: { review_status: 'rejected' },
                            })
                          }
                          className="rounded bg-status-error-bg px-2 py-1 text-xs font-medium text-status-error-fg hover:opacity-80"
                        >
                          Reject
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState message="No cookies yet. Add one manually, run a scan, or wait for client-side reporting." />
      )}

      {showAddModal && (
        <AddCookieModal siteId={siteId} onClose={() => setShowAddModal(false)} />
      )}
    </div>
  );
}
