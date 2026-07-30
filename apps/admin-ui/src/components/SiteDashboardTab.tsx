import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { getConsentRates, getConsentTrends } from '../api/analytics';
import { CONSENT_COLOURS as COLOURS } from '../lib/consent';
import ConsentBreakdownCards from './ConsentBreakdownCards';
import { Card } from './ui/card';
import { LoadingState } from './ui/loading-state';
import { TabGroup } from './ui/tab-group';

interface Props {
  siteId: string;
}

type DateRange = '7d' | '30d' | '90d' | '12m';

const RANGE_OPTIONS: { value: DateRange; label: string; days: number }[] = [
  { value: '7d', label: '7 days', days: 7 },
  { value: '30d', label: '30 days', days: 30 },
  { value: '90d', label: '90 days', days: 90 },
  { value: '12m', label: '12 months', days: 365 },
];

const EMPTY_BREAKDOWN = { accept_all: 0, reject_all: 0, custom: 0, withdraw: 0 };

function granularityFor(days: number): 'day' | 'week' | 'month' {
  if (days <= 31) return 'day';
  if (days <= 120) return 'week';
  return 'month';
}

export default function SiteDashboardTab({ siteId }: Props) {
  const [range, setRange] = useState<DateRange>('30d');
  const days = RANGE_OPTIONS.find((o) => o.value === range)?.days ?? 30;
  const granularity = granularityFor(days);

  const { data: rates, isLoading: ratesLoading } = useQuery({
    queryKey: ['consent-rates', siteId, days],
    queryFn: () => getConsentRates(siteId, { days }),
  });

  const { data: trends, isLoading: trendsLoading } = useQuery({
    queryKey: ['consent-trends', siteId, days, granularity],
    queryFn: () => getConsentTrends(siteId, { days, granularity }),
  });

  if (ratesLoading || trendsLoading) {
    return <LoadingState message="Loading consent analytics..." />;
  }

  const breakdown = rates?.action_breakdown;
  // Decisions exclude withdrawals — a withdrawal is not an accept/decline choice.
  const decisions = breakdown
    ? breakdown.accept_all + breakdown.custom + breakdown.reject_all
    : 0;

  const pieData = breakdown
    ? [
        { name: 'Accept', value: breakdown.accept_all, fill: COLOURS.accept },
        { name: 'Partial', value: breakdown.custom, fill: COLOURS.partial },
        { name: 'Decline', value: breakdown.reject_all, fill: COLOURS.decline },
      ]
    : [];

  const trendData =
    trends?.data.map((p) => ({
      period: p.period,
      Accept: p.accept_all,
      Partial: p.custom,
      Decline: p.reject_all,
    })) ?? [];

  return (
    <div>
      {/* Range selector */}
      <div className="mb-6 flex items-center justify-between gap-3">
        <h2 className="font-heading text-lg font-semibold text-foreground">Consent breakdown</h2>
        <TabGroup
          options={RANGE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          value={range}
          onChange={(v) => setRange(v as DateRange)}
        />
      </div>

      {decisions === 0 ? (
        <div className="py-12 text-center text-sm text-text-secondary">
          No consent decisions recorded in this period.
        </div>
      ) : (
        <>
          {/* Headline metrics — bento grid */}
          <div className="mb-6">
            <ConsentBreakdownCards
              breakdown={breakdown ?? EMPTY_BREAKDOWN}
              rangeLabel={`Last ${RANGE_OPTIONS.find((o) => o.value === range)?.label}`}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Breakdown donut */}
            <Card className="p-5">
              <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">
                Decision split
              </h3>
              <ResponsiveContainer width="99%" height={280}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    isAnimationActive={false}
                  >
                    {pieData.map((entry) => (
                      <Cell key={entry.name} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => Number(value).toLocaleString()} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </Card>

            {/* Trend over time */}
            <Card className="p-5">
              <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">
                Over time ({granularity})
              </h3>
              <ResponsiveContainer width="99%" height={280}>
                <BarChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Accept" stackId="a" fill={COLOURS.accept} isAnimationActive={false} />
                  <Bar dataKey="Partial" stackId="a" fill={COLOURS.partial} isAnimationActive={false} />
                  <Bar dataKey="Decline" stackId="a" fill={COLOURS.decline} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          {/* Per-category rates */}
          {rates && rates.category_rates.length > 0 && (
            <Card className="mt-6 p-5">
              <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">
                Acceptance by category
              </h3>
              <div className="overflow-hidden rounded-lg border border-border">
                <table className="min-w-full divide-y divide-border text-sm">
                  <thead className="bg-background">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium text-text-secondary">Category</th>
                      <th className="px-4 py-2 text-right font-medium text-text-secondary">Accepted</th>
                      <th className="px-4 py-2 text-right font-medium text-text-secondary">Rejected</th>
                      <th className="px-4 py-2 text-right font-medium text-text-secondary">Rate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {rates.category_rates.map((c) => (
                      <tr key={c.category}>
                        <td className="px-4 py-2 capitalize text-foreground">{c.category}</td>
                        <td className="px-4 py-2 text-right text-text-secondary">
                          {c.accepted.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-right text-text-secondary">
                          {c.rejected.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-right font-medium text-foreground">
                          {Math.round(c.rate * 100)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {breakdown && breakdown.withdraw > 0 && (
            <p className="mt-4 text-xs text-text-tertiary">
              {breakdown.withdraw.toLocaleString()} withdrawal
              {breakdown.withdraw !== 1 ? 's' : ''} in this period (excluded from decision rates).
            </p>
          )}
        </>
      )}
    </div>
  );
}
