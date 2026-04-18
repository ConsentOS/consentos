import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { listConsentRecords } from '../api/consent';
import type { ConsentRecord } from '../types/api';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { LoadingState } from './ui/loading-state';

interface Props {
  siteId: string;
}

function actionVariant(action: string): 'success' | 'error' | 'warning' | 'neutral' {
  const map: Record<string, 'success' | 'error' | 'warning'> = {
    accept_all: 'success',
    reject_all: 'error',
    custom: 'warning',
    withdraw: 'error',
  };
  return map[action] ?? 'neutral';
}

function actionLabel(action: string): string {
  const map: Record<string, string> = {
    accept_all: 'Accept all',
    reject_all: 'Reject all',
    custom: 'Custom',
    withdraw: 'Withdrawn',
  };
  return map[action] ?? action;
}

function RecordDetail({ record }: { record: ConsentRecord }) {
  return (
    <tr>
      <td colSpan={5} className="bg-mist px-4 py-3">
        <div className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <span className="font-medium text-text-secondary">Visitor ID</span>
            <p className="mt-0.5 break-all font-mono">{record.visitor_id}</p>
          </div>
          <div>
            <span className="font-medium text-text-secondary">Page URL</span>
            <p className="mt-0.5 break-all">{record.page_url ?? '—'}</p>
          </div>
          <div>
            <span className="font-medium text-text-secondary">Accepted</span>
            <p className="mt-0.5">{record.categories_accepted.join(', ') || '—'}</p>
          </div>
          <div>
            <span className="font-medium text-text-secondary">Rejected</span>
            <p className="mt-0.5">{record.categories_rejected?.join(', ') || '—'}</p>
          </div>
          {record.country_code && (
            <div>
              <span className="font-medium text-text-secondary">Location</span>
              <p className="mt-0.5">{record.region_code ? `${record.country_code}-${record.region_code}` : record.country_code}</p>
            </div>
          )}
          {record.tc_string && (
            <div>
              <span className="font-medium text-text-secondary">TC String</span>
              <p className="mt-0.5 break-all font-mono text-[11px]">{record.tc_string}</p>
            </div>
          )}
          {record.gpc_detected != null && (
            <div>
              <span className="font-medium text-text-secondary">GPC</span>
              <p className="mt-0.5">
                Detected: {record.gpc_detected ? 'Yes' : 'No'}
                {record.gpc_honoured != null && ` · Honoured: ${record.gpc_honoured ? 'Yes' : 'No'}`}
              </p>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function SiteConsentTab({ siteId }: Props) {
  const [search, setSearch] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const pageSize = 25;

  const { data, isLoading } = useQuery({
    queryKey: ['consent', siteId, activeSearch, page],
    queryFn: () =>
      listConsentRecords(siteId, {
        visitor_id: activeSearch || undefined,
        page,
        page_size: pageSize,
      }),
  });

  const handleSearch = () => {
    setActiveSearch(search.trim());
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  return (
    <div>
      {/* Search */}
      <Card className="mb-6 p-5">
        <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">
          Search Consent Records
        </h3>
        <div className="flex flex-wrap gap-3">
          <input
            type="text"
            className="min-w-[280px] flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-text-tertiary focus:border-copper focus:outline-none"
            placeholder="Search by visitor ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <Button onClick={handleSearch}>Search</Button>
          {activeSearch && (
            <Button
              variant="secondary"
              onClick={() => {
                setSearch('');
                setActiveSearch('');
                setPage(1);
              }}
            >
              Clear
            </Button>
          )}
        </div>
        {activeSearch && (
          <p className="mt-2 text-xs text-text-secondary">
            Showing results for visitor: <code className="rounded bg-mist px-1.5 py-0.5 font-mono">{activeSearch}</code>
          </p>
        )}
      </Card>

      {/* Results */}
      {isLoading ? (
        <LoadingState message="Loading consent records..." />
      ) : !data || data.items.length === 0 ? (
        <div className="py-8 text-center text-sm text-text-secondary">
          {activeSearch
            ? 'No consent records found for this visitor.'
            : 'No consent records yet.'}
        </div>
      ) : (
        <>
          <div className="mb-3 flex items-center justify-between text-xs text-text-secondary">
            <span>{data.total} record{data.total !== 1 ? 's' : ''}</span>
            <span>Page {page} of {totalPages}</span>
          </div>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="min-w-full divide-y divide-border text-sm">
              <thead className="bg-background">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-text-secondary">Visitor</th>
                  <th className="px-4 py-3 text-left font-medium text-text-secondary">Action</th>
                  <th className="px-4 py-3 text-left font-medium text-text-secondary">Categories</th>
                  <th className="px-4 py-3 text-left font-medium text-text-secondary">Date</th>
                  <th className="px-4 py-3 text-left font-medium text-text-secondary" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.items.map((record) => (
                  <>
                    <tr
                      key={record.id}
                      className="cursor-pointer hover:bg-mist"
                      onClick={() => setExpandedId(expandedId === record.id ? null : record.id)}
                    >
                      <td className="px-4 py-3 font-mono text-xs">
                        {record.visitor_id.length > 16
                          ? record.visitor_id.slice(0, 8) + '…' + record.visitor_id.slice(-8)
                          : record.visitor_id}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={actionVariant(record.action)}>
                          {actionLabel(record.action)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {record.categories_accepted.join(', ')}
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {new Date(record.consented_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-text-tertiary">
                        {expandedId === record.id ? '▲' : '▼'}
                      </td>
                    </tr>
                    {expandedId === record.id && (
                      <RecordDetail key={`${record.id}-detail`} record={record} />
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-xs text-text-secondary">
                {page} / {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
